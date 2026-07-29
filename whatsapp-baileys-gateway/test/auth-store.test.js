import assert from "node:assert/strict";
import test from "node:test";
import { randomBytes } from "node:crypto";

import { decryptJson, encryptJson } from "../src/auth-store.js";

test("encrypts authentication state with AES-256-GCM", () => {
  const key = randomBytes(32);
  const secret = { noiseKey: "sensitive-signal-material", nested: { value: 42 } };

  const encrypted = encryptJson(secret, key);
  const serialized = Buffer.concat([
    encrypted.ciphertext,
    encrypted.iv,
    encrypted.authTag
  ]).toString("utf8");

  assert.equal(serialized.includes("sensitive-signal-material"), false);
  assert.deepEqual(decryptJson(encrypted, key), secret);
});

test("rejects decryption with another key", () => {
  const encrypted = encryptJson({ secret: true }, randomBytes(32));

  assert.throws(() => decryptJson(encrypted, randomBytes(32)));
});
