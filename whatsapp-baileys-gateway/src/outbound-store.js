import { createHash } from "node:crypto";

import { ProviderError } from "./errors.js";

const OUTBOUND_TABLE = "whatsapp_gateway_outbound";

function hashPayload(recipient, message) {
  return createHash("sha256").update(`${recipient}\n${message}`).digest("hex");
}

export class MemoryOutboundStore {
  constructor() {
    this.records = new Map();
  }

  async get(requestId) {
    return this.records.get(requestId) ?? null;
  }

  async insertPending(record) {
    if (this.records.has(record.requestId)) return false;
    this.records.set(record.requestId, { ...record, status: "pending" });
    return true;
  }

  async markSent(requestId, result) {
    this.records.set(requestId, {
      ...this.records.get(requestId),
      status: "sent",
      result
    });
  }

  async markFailed(requestId, errorCode) {
    this.records.set(requestId, {
      ...this.records.get(requestId),
      status: "failed",
      errorCode
    });
  }

  async markUncertain(requestId, errorCode) {
    this.records.set(requestId, {
      ...this.records.get(requestId),
      status: "uncertain",
      errorCode
    });
  }

  async retryFailed(requestId) {
    const existing = this.records.get(requestId);
    if (!existing || existing.status !== "failed") return false;
    this.records.set(requestId, {
      ...existing,
      status: "pending",
      errorCode: ""
    });
    return true;
  }
}

export class PostgreSQLOutboundStore {
  constructor(pool, sessionId) {
    this.pool = pool;
    this.sessionId = sessionId;
  }

  async ensureSchema() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS ${OUTBOUND_TABLE} (
        session_id TEXT NOT NULL,
        request_id UUID NOT NULL,
        recipient TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'uncertain')),
        result JSONB,
        error_code TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (session_id, request_id)
      )
    `);
  }

  async get(requestId) {
    const result = await this.pool.query(
      `SELECT request_id AS "requestId", recipient,
              payload_hash AS "payloadHash", status, result,
              error_code AS "errorCode"
         FROM ${OUTBOUND_TABLE}
        WHERE session_id = $1 AND request_id = $2`,
      [this.sessionId, requestId]
    );
    return result.rows[0] ?? null;
  }

  async insertPending(record) {
    const result = await this.pool.query(
      `INSERT INTO ${OUTBOUND_TABLE}
        (session_id, request_id, recipient, payload_hash, status)
       VALUES ($1, $2, $3, $4, 'pending')
       ON CONFLICT (session_id, request_id) DO NOTHING`,
      [this.sessionId, record.requestId, record.recipient, record.payloadHash]
    );
    return result.rowCount === 1;
  }

  async markSent(requestId, result) {
    await this.#update(requestId, "sent", result, "");
  }

  async markFailed(requestId, errorCode) {
    await this.#update(requestId, "failed", null, errorCode);
  }

  async markUncertain(requestId, errorCode) {
    await this.#update(requestId, "uncertain", null, errorCode);
  }

  async retryFailed(requestId) {
    const result = await this.pool.query(
      `UPDATE ${OUTBOUND_TABLE}
          SET status = 'pending', error_code = '', updated_at = NOW()
        WHERE session_id = $1 AND request_id = $2 AND status = 'failed'`,
      [this.sessionId, requestId]
    );
    return result.rowCount === 1;
  }

  async #update(requestId, status, result, errorCode) {
    await this.pool.query(
      `UPDATE ${OUTBOUND_TABLE}
          SET status = $3, result = $4, error_code = $5, updated_at = NOW()
        WHERE session_id = $1 AND request_id = $2`,
      [this.sessionId, requestId, status, result, errorCode]
    );
  }
}

export class OutboundCoordinator {
  constructor(store) {
    this.store = store;
  }

  async send({ requestId, recipient, message, payloadHash, deliver }) {
    const expectedHash = payloadHash ?? hashPayload(recipient, message);
    let existing = await this.store.get(requestId);
    if (!existing) {
      const inserted = await this.store.insertPending({
        requestId,
        recipient,
        payloadHash: expectedHash
      });
      if (!inserted) existing = await this.store.get(requestId);
    }

    if (existing) {
      if (existing.payloadHash !== expectedHash || existing.recipient !== recipient) {
        throw new ProviderError("A chave de idempotência já foi usada com outro conteúdo.", {
          code: "IDEMPOTENCY_CONFLICT",
          httpStatus: 409
        });
      }
      if (existing.status === "sent") {
        return { ...existing.result, replayed: true };
      }
      if (existing.status === "failed") {
        const retryClaimed = await this.store.retryFailed(requestId);
        if (retryClaimed) {
          existing = null;
        } else {
          existing = await this.store.get(requestId);
          if (existing?.status === "sent") {
            return { ...existing.result, replayed: true };
          }
        }
      }
    }
    if (existing) {
      throw new ProviderError("O resultado desta tentativa não pode ser confirmado.", {
        code: "DELIVERY_RESULT_UNKNOWN",
        deliveryUncertain: true,
        httpStatus: 409
      });
    }

    try {
      const result = await deliver();
      await this.store.markSent(requestId, result);
      return { ...result, replayed: false };
    } catch (error) {
      if (error instanceof ProviderError && !error.deliveryUncertain) {
        await this.store.markFailed(requestId, error.code);
        throw error;
      }
      await this.store.markUncertain(requestId, "DELIVERY_RESULT_UNKNOWN");
      throw new ProviderError("O provedor não confirmou o resultado do envio.", {
        code: "DELIVERY_RESULT_UNKNOWN",
        deliveryUncertain: true,
        httpStatus: 502
      });
    }
  }
}
