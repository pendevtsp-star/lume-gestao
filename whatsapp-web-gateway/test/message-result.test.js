import assert from "node:assert/strict";
import test from "node:test";

import { messageIdFromSendResult } from "../src/message-result.js";

test("returns the serialized provider message id", () => {
  assert.equal(
    messageIdFromSendResult({ id: { _serialized: "message-123" } }),
    "message-123"
  );
});

test("accepts a successful send without result metadata", () => {
  assert.equal(messageIdFromSendResult(undefined), "");
});

test("accepts a result without an id", () => {
  assert.equal(messageIdFromSendResult({}), "");
});
