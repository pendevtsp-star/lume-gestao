import assert from "node:assert/strict";
import test from "node:test";

import { ProviderError, errorPayload } from "../src/errors.js";

test("serializes retryable pre-send errors", () => {
  const payload = errorPayload(
    new ProviderError("A sessão ainda não está pronta.", {
      code: "SESSION_NOT_READY",
      retryable: true,
      deliveryUncertain: false,
      httpStatus: 503
    })
  );

  assert.deepEqual(payload, {
    ok: false,
    code: "SESSION_NOT_READY",
    retryable: true,
    deliveryUncertain: false,
    error: "A sessão ainda não está pronta."
  });
});

test("serializes uncertain errors as non-retryable", () => {
  const payload = errorPayload(
    new ProviderError("Resultado desconhecido.", {
      code: "DELIVERY_RESULT_UNKNOWN",
      deliveryUncertain: true
    })
  );

  assert.equal(payload.retryable, false);
  assert.equal(payload.deliveryUncertain, true);
});
