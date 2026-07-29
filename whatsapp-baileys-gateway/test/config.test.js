import assert from "node:assert/strict";
import test from "node:test";

import { loadConfig } from "../src/config.js";

const REQUIRED_ENV = {
  DATABASE_URL: "postgresql://lume:lume@db:5432/lume",
  WHATSAPP_GATEWAY_TOKEN: "synthetic-token",
  WHATSAPP_AUTH_ENCRYPTION_KEY: Buffer.alloc(32, 7).toString("base64")
};

async function withEnvironment(overrides, callback) {
  const previous = { ...process.env };
  Object.assign(process.env, REQUIRED_ENV, overrides);
  try {
    await callback();
  } finally {
    for (const key of Object.keys(process.env)) {
      if (!(key in previous)) delete process.env[key];
    }
    Object.assign(process.env, previous);
  }
}

test("rejects partial or out-of-range numeric settings", async () => {
  await withEnvironment({ PORT: "3030abc" }, () => {
    assert.throws(() => loadConfig(), /PORT/);
  });
  await withEnvironment({ PORT: "70000" }, () => {
    assert.throws(() => loadConfig(), /PORT/);
  });
  await withEnvironment({ WHATSAPP_MIN_SEND_INTERVAL_MS: "-1" }, () => {
    assert.throws(() => loadConfig(), /WHATSAPP_MIN_SEND_INTERVAL_MS/);
  });
});

test("rejects a blank logical session id", async () => {
  await withEnvironment({ WHATSAPP_SESSION_ID: "   " }, () => {
    assert.throws(() => loadConfig(), /WHATSAPP_SESSION_ID/);
  });
});

test("builds a safe database URL from discrete PostgreSQL settings", async () => {
  await withEnvironment({
    DATABASE_URL: "",
    POSTGRES_HOST: "db",
    POSTGRES_PORT: "5432",
    POSTGRES_DB: "lume",
    POSTGRES_USER: "lume@clinic",
    POSTGRES_PASSWORD: "safe/password"
  }, () => {
    const config = loadConfig();

    assert.equal(
      config.databaseUrl,
      "postgresql://lume%40clinic:safe%2Fpassword@db:5432/lume"
    );
  });
});
