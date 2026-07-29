import assert from "node:assert/strict";
import test from "node:test";

import {
  ConnectionManager,
  connectionCloseDecision,
  normalizeConnectionUpdate
} from "../src/connection.js";

test("maps qr and open events to the public state contract", () => {
  assert.deepEqual(normalizeConnectionUpdate({ qr: "secret-qr" }), {
    state: "qr_ready",
    ready: false,
    hasQr: true
  });
  assert.deepEqual(normalizeConnectionUpdate({ connection: "open" }), {
    state: "ready",
    ready: true,
    hasQr: false
  });
});

test("maps close events to reconnecting without exposing raw errors", () => {
  assert.deepEqual(normalizeConnectionUpdate({ connection: "close" }), {
    state: "reconnecting",
    ready: false,
    hasQr: false
  });
});

test("uses a dedicated silent logger for Baileys protocol metadata", async () => {
  const silentLogger = { level: "silent" };
  let socketOptions;
  const manager = new ConnectionManager({
    makeWASocket: (options) => {
      socketOptions = options;
      return {
        ev: { on() {} }
      };
    },
    authStore: {
      loadState: async () => ({
        state: {},
        saveCreds: async () => {}
      })
    },
    outboundCoordinator: {},
    baileys: {
      initAuthCreds() {},
      BufferJSON: {},
      proto: {}
    },
    qrCode: {},
    logger: {
      info() {},
      warn() {}
    },
    baileysLogger: silentLogger
  });

  await manager.start();

  assert.equal(socketOptions.logger, silentLogger);
});

test("classifies reconnectable and terminal disconnect reasons", () => {
  const reasons = {
    loggedOut: 401,
    connectionReplaced: 440,
    restartRequired: 515
  };

  assert.deepEqual(
    connectionCloseDecision({
      lastDisconnect: { error: { output: { statusCode: 515 } } }
    }, reasons),
    {
      reconnect: true,
      state: "reconnecting",
      lastErrorCode: "DISCONNECTED_515"
    }
  );
  assert.deepEqual(
    connectionCloseDecision({
      lastDisconnect: { error: { output: { statusCode: 401 } } }
    }, reasons),
    {
      reconnect: false,
      state: "logged_out",
      lastErrorCode: "DISCONNECTED_401"
    }
  );
  assert.deepEqual(
    connectionCloseDecision({
      lastDisconnect: { error: { output: { statusCode: 440 } } }
    }, reasons),
    {
      reconnect: false,
      state: "error",
      lastErrorCode: "DISCONNECTED_440"
    }
  );
});

test("schedules only one reconnect for repeated close events", async () => {
  let connectionUpdate;
  let scheduled = 0;
  const socket = {
    ev: {
      on(event, callback) {
        if (event === "connection.update") connectionUpdate = callback;
      },
      removeAllListeners() {}
    }
  };
  const manager = new ConnectionManager({
    makeWASocket: () => socket,
    authStore: {
      sessionId: "clinic-primary",
      loadState: async () => ({
        state: {},
        saveCreds: async () => {}
      })
    },
    outboundCoordinator: {},
    baileys: {
      initAuthCreds() {},
      BufferJSON: {},
      proto: {},
      DisconnectReason: {
        loggedOut: 401,
        connectionReplaced: 440,
        badSession: 500,
        multideviceMismatch: 411,
        forbidden: 403
      }
    },
    qrCode: {},
    logger: {
      info() {},
      warn() {},
      error() {}
    },
    baileysLogger: { level: "silent" },
    schedule: () => {
      scheduled += 1;
      return scheduled;
    }
  });
  await manager.start();
  const closeUpdate = {
    connection: "close",
    lastDisconnect: { error: { output: { statusCode: 408 } } }
  };

  await connectionUpdate(closeUpdate);
  await connectionUpdate(closeUpdate);

  assert.equal(scheduled, 1);
  assert.equal(manager.publicStatus().lastErrorCode, "DISCONNECTED_408");
});

test("logout clears only the selected session and prepares a fresh QR socket", async () => {
  let socketsCreated = 0;
  let logoutCalls = 0;
  let clearSessionCalls = 0;
  const manager = new ConnectionManager({
    makeWASocket: () => {
      socketsCreated += 1;
      return {
        ev: {
          on() {},
          removeAllListeners() {}
        },
        logout: async () => {
          logoutCalls += 1;
        }
      };
    },
    authStore: {
      sessionId: "clinic-primary",
      loadState: async () => ({
        state: {},
        saveCreds: async () => {}
      }),
      clearSession: async () => {
        clearSessionCalls += 1;
      }
    },
    outboundCoordinator: {},
    baileys: {
      initAuthCreds() {},
      BufferJSON: {},
      proto: {},
      DisconnectReason: {}
    },
    qrCode: {},
    logger: {
      info() {},
      warn() {},
      error() {}
    },
    baileysLogger: { level: "silent" }
  });
  await manager.start();

  const status = await manager.logout();

  assert.equal(logoutCalls, 1);
  assert.equal(clearSessionCalls, 1);
  assert.equal(socketsCreated, 2);
  assert.equal(status.state, "connecting");
  assert.equal(status.ready, false);
});
