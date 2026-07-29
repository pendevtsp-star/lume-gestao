import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

import makeWASocket, * as baileys from "baileys";
import express from "express";
import pg from "pg";
import pino from "pino";
import QRCode from "qrcode";

import { PostgreSQLAuthStateStore } from "./auth-store.js";
import { loadConfig } from "./config.js";
import { ConnectionManager } from "./connection.js";
import { errorPayload, ProviderError } from "./errors.js";
import {
  OutboundCoordinator,
  PostgreSQLOutboundStore
} from "./outbound-store.js";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function safeTokenEquals(actual, expected) {
  const actualBuffer = Buffer.from(actual);
  const expectedBuffer = Buffer.from(expected);
  return actualBuffer.length === expectedBuffer.length
    && crypto.timingSafeEqual(actualBuffer, expectedBuffer);
}

function validateSendBody(body) {
  const requestId = String(body?.requestId ?? "").trim();
  const recipient = String(body?.to ?? body?.recipient ?? "").replace(/\D/g, "");
  const message = String(body?.message ?? "").trim();
  if (!UUID_PATTERN.test(requestId)) {
    throw new ProviderError("requestId inválido.", {
      code: "INVALID_REQUEST",
      httpStatus: 400
    });
  }
  if (recipient.length < 10 || recipient.length > 15) {
    throw new ProviderError("Destinatário inválido.", {
      code: "INVALID_RECIPIENT",
      httpStatus: 400
    });
  }
  if (!message || message.length > 4096) {
    throw new ProviderError("Mensagem inválida.", {
      code: "INVALID_MESSAGE",
      httpStatus: 400
    });
  }
  return { requestId, recipient, message };
}

export async function createGateway() {
  const config = loadConfig();
  const logger = pino({
    level: process.env.LOG_LEVEL ?? "info",
    redact: {
      paths: [
        "req.headers.authorization",
        "*.qr",
        "*.qrDataUrl",
        "*.auth",
        "*.creds",
        "*.message"
      ],
      censor: "[REDACTED]"
    }
  });
  const baileysLogger = pino({ level: "silent" });
  const pool = new pg.Pool({
    connectionString: config.databaseUrl,
    max: 4
  });
  const authStore = new PostgreSQLAuthStateStore(
    pool,
    config.encryptionKey,
    config.sessionId
  );
  const outboundStore = new PostgreSQLOutboundStore(pool, config.sessionId);
  await authStore.ensureSchema();
  await outboundStore.ensureSchema();

  const manager = new ConnectionManager({
    makeWASocket,
    authStore,
    outboundCoordinator: new OutboundCoordinator(outboundStore),
    baileys,
    qrCode: QRCode,
    logger,
    baileysLogger,
    minSendIntervalMs: config.minSendIntervalMs
  });
  await manager.start();

  const app = express();
  app.disable("x-powered-by");
  app.use(express.json({ limit: "32kb" }));
  app.get("/healthz", (_request, response) => {
    response.json(manager.publicStatus());
  });
  app.use((request, response, next) => {
    const token = request.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
    if (!safeTokenEquals(token, config.bearerToken)) {
      response.status(401).json(errorPayload(new ProviderError("Não autorizado.", {
        code: "UNAUTHORIZED",
        httpStatus: 401
      })));
      return;
    }
    next();
  });
  app.get("/qr", (_request, response) => response.json(manager.qrStatus()));
  app.post("/restart", async (_request, response, next) => {
    try {
      response.json(await manager.restart());
    } catch (error) {
      next(error);
    }
  });
  app.post("/logout", async (_request, response, next) => {
    try {
      response.json(await manager.logout());
    } catch (error) {
      next(error);
    }
  });
  app.post("/send", async (request, response, next) => {
    try {
      const result = await manager.sendText(validateSendBody(request.body));
      response.json({
        ok: true,
        requestId: request.body.requestId,
        provider: "baileys",
        ...result
      });
    } catch (error) {
      next(error);
    }
  });
  app.use((error, _request, response, _next) => {
    logger.error({
      event: "gateway_request_failed",
      code: error?.code ?? "INTERNAL_ERROR"
    }, "Requisição do gateway falhou.");
    const providerError = error instanceof ProviderError
      ? error
      : new ProviderError("Falha interna no gateway.");
    response.status(providerError.httpStatus).json(errorPayload(providerError));
  });
  return { app, pool, manager, config, logger };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createGateway().then(({ app, config, logger }) => {
    app.listen(config.port, "0.0.0.0", () => {
      logger.info(
        { event: "gateway_started", port: config.port },
        "Gateway Baileys iniciado."
      );
    });
  }).catch((error) => {
    process.stderr.write(`Falha ao iniciar gateway: ${error.message}\n`);
    process.exitCode = 1;
  });
}
