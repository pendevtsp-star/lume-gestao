import assert from "node:assert/strict";
import test from "node:test";

import {
  MemoryOutboundStore,
  OutboundCoordinator
} from "../src/outbound-store.js";
import { ProviderError } from "../src/errors.js";

test("returns the saved result for a duplicate sent request", async () => {
  const store = new MemoryOutboundStore();
  const coordinator = new OutboundCoordinator(store);
  let sends = 0;
  const deliver = async () => {
    sends += 1;
    return { messageId: "message-1" };
  };

  const first = await coordinator.send({
    requestId: "7caefec8-51bd-4aaa-aa52-958eb32477d0",
    recipient: "5511999990000",
    message: "Olá",
    deliver
  });
  const duplicate = await coordinator.send({
    requestId: "7caefec8-51bd-4aaa-aa52-958eb32477d0",
    recipient: "5511999990000",
    message: "Olá",
    deliver
  });

  assert.equal(sends, 1);
  assert.equal(first.messageId, "message-1");
  assert.equal(duplicate.messageId, "message-1");
  assert.equal(duplicate.replayed, true);
});

test("a request left pending after crash becomes uncertain and is never resent", async () => {
  const store = new MemoryOutboundStore();
  await store.insertPending({
    requestId: "7caefec8-51bd-4aaa-aa52-958eb32477d1",
    recipient: "5511999990000",
    payloadHash: "existing-hash"
  });
  const coordinator = new OutboundCoordinator(store);
  let sends = 0;

  await assert.rejects(
    coordinator.send({
      requestId: "7caefec8-51bd-4aaa-aa52-958eb32477d1",
      recipient: "5511999990000",
      message: "Olá",
      payloadHash: "existing-hash",
      deliver: async () => {
        sends += 1;
        return { messageId: "must-not-send" };
      }
    }),
    (error) => error.code === "DELIVERY_RESULT_UNKNOWN"
  );

  assert.equal(sends, 0);
});

test("a confirmed pre-send failure can be retried with the same request id", async () => {
  const store = new MemoryOutboundStore();
  const coordinator = new OutboundCoordinator(store);
  let attempts = 0;
  const request = {
    requestId: "7caefec8-51bd-4aaa-aa52-958eb32477d2",
    recipient: "5511999990000",
    message: "Olá"
  };

  await assert.rejects(
    coordinator.send({
      ...request,
      deliver: async () => {
        attempts += 1;
        throw new ProviderError("Sessão ainda não está pronta.", {
          code: "SESSION_NOT_READY",
          retryable: true,
          httpStatus: 503
        });
      }
    }),
    (error) => error.code === "SESSION_NOT_READY"
  );

  const retry = await coordinator.send({
    ...request,
    deliver: async () => {
      attempts += 1;
      return { messageId: "message-after-safe-retry" };
    }
  });

  assert.equal(attempts, 2);
  assert.equal(retry.messageId, "message-after-safe-retry");
});
