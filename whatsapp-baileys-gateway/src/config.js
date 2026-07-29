function required(name) {
  const value = (process.env[name] ?? "").trim();
  if (!value) throw new Error(`${name} é obrigatório.`);
  return value;
}

function integerSetting(name, fallback, { min, max }) {
  const raw = String(process.env[name] ?? fallback);
  if (!/^\d+$/.test(raw)) {
    throw new Error(`${name} deve ser um número inteiro.`);
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new Error(`${name} está fora do intervalo permitido.`);
  }
  return value;
}

function databaseUrl() {
  const configured = (process.env.DATABASE_URL ?? "").trim();
  if (configured) return configured;
  const host = required("POSTGRES_HOST");
  if (!/^[a-zA-Z0-9_.-]+$/.test(host)) {
    throw new Error("POSTGRES_HOST é inválido.");
  }
  const port = integerSetting("POSTGRES_PORT", "5432", {
    min: 1,
    max: 65535
  });
  const database = encodeURIComponent(required("POSTGRES_DB"));
  const user = encodeURIComponent(required("POSTGRES_USER"));
  const password = encodeURIComponent(required("POSTGRES_PASSWORD"));
  return `postgresql://${user}:${password}@${host}:${port}/${database}`;
}

export function loadConfig() {
  const encryptionKey = Buffer.from(
    required("WHATSAPP_AUTH_ENCRYPTION_KEY"),
    "base64"
  );
  if (encryptionKey.length !== 32) {
    throw new Error("WHATSAPP_AUTH_ENCRYPTION_KEY deve representar 32 bytes em base64.");
  }
  const sessionId = (process.env.WHATSAPP_SESSION_ID ?? "clinic-primary").trim();
  if (!sessionId) {
    throw new Error("WHATSAPP_SESSION_ID é obrigatório.");
  }
  return {
    port: integerSetting("PORT", "3030", { min: 1, max: 65535 }),
    databaseUrl: databaseUrl(),
    bearerToken: required("WHATSAPP_GATEWAY_TOKEN"),
    encryptionKey,
    sessionId,
    minSendIntervalMs: integerSetting(
      "WHATSAPP_MIN_SEND_INTERVAL_MS",
      "1100",
      { min: 0, max: 60000 }
    )
  };
}
