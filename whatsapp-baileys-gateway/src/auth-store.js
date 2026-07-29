import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

const AUTH_TABLE = "whatsapp_gateway_auth";

function validateKey(key) {
  if (!Buffer.isBuffer(key) || key.length !== 32) {
    throw new Error("A chave de autenticação deve conter exatamente 32 bytes.");
  }
}

export function encryptJson(value, key, replacer) {
  validateKey(key);
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(value, replacer), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return { ciphertext, iv, authTag: cipher.getAuthTag() };
}

export function decryptJson(encrypted, key, reviver) {
  validateKey(key);
  const decipher = createDecipheriv("aes-256-gcm", key, encrypted.iv);
  decipher.setAuthTag(encrypted.authTag);
  const plaintext = Buffer.concat([
    decipher.update(encrypted.ciphertext),
    decipher.final()
  ]).toString("utf8");
  return JSON.parse(plaintext, reviver);
}

export class PostgreSQLAuthStateStore {
  constructor(pool, encryptionKey, sessionId) {
    this.pool = pool;
    this.encryptionKey = encryptionKey;
    this.sessionId = sessionId;
  }

  async ensureSchema() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS ${AUTH_TABLE} (
        session_id TEXT NOT NULL,
        key_type TEXT NOT NULL,
        key_id TEXT NOT NULL,
        ciphertext BYTEA NOT NULL,
        iv BYTEA NOT NULL,
        auth_tag BYTEA NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (session_id, key_type, key_id)
      )
    `);
  }

  async put(keyType, keyId, value, replacer) {
    const encrypted = encryptJson(value, this.encryptionKey, replacer);
    await this.pool.query(
      `INSERT INTO ${AUTH_TABLE}
        (session_id, key_type, key_id, ciphertext, iv, auth_tag, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, NOW())
       ON CONFLICT (session_id, key_type, key_id) DO UPDATE SET
        ciphertext = EXCLUDED.ciphertext,
        iv = EXCLUDED.iv,
        auth_tag = EXCLUDED.auth_tag,
        updated_at = NOW()`,
      [
        this.sessionId,
        keyType,
        keyId,
        encrypted.ciphertext,
        encrypted.iv,
        encrypted.authTag
      ]
    );
  }

  async get(keyType, keyId, reviver) {
    const result = await this.pool.query(
      `SELECT ciphertext, iv, auth_tag
         FROM ${AUTH_TABLE}
        WHERE session_id = $1 AND key_type = $2 AND key_id = $3`,
      [this.sessionId, keyType, keyId]
    );
    if (!result.rowCount) return null;
    const row = result.rows[0];
    return decryptJson(
      { ciphertext: row.ciphertext, iv: row.iv, authTag: row.auth_tag },
      this.encryptionKey,
      reviver
    );
  }

  async remove(keyType, keyId) {
    await this.pool.query(
      `DELETE FROM ${AUTH_TABLE}
        WHERE session_id = $1 AND key_type = $2 AND key_id = $3`,
      [this.sessionId, keyType, keyId]
    );
  }

  async clearSession() {
    await this.pool.query(
      `DELETE FROM ${AUTH_TABLE} WHERE session_id = $1`,
      [this.sessionId]
    );
  }

  async loadState({ initAuthCreds, BufferJSON, proto }) {
    const replacer = BufferJSON.replacer;
    const reviver = BufferJSON.reviver;
    const creds = await this.get("creds", "primary", reviver) ?? initAuthCreds();
    return {
      state: {
        creds,
        keys: {
          get: async (type, ids) => {
            const values = {};
            await Promise.all(ids.map(async (id) => {
              let value = await this.get(type, id, reviver);
              if (type === "app-state-sync-key" && value) {
                value = proto.Message.AppStateSyncKeyData.fromObject(value);
              }
              if (value) values[id] = value;
            }));
            return values;
          },
          set: async (data) => {
            for (const [type, entries] of Object.entries(data)) {
              for (const [id, value] of Object.entries(entries)) {
                if (value) await this.put(type, id, value, replacer);
                else await this.remove(type, id);
              }
            }
          }
        }
      },
      saveCreds: () => this.put("creds", "primary", creds, replacer)
    };
  }
}
