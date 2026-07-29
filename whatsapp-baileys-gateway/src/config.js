function required(name) {
  const value = (process.env[name] ?? "").trim();
  if (!value) throw new Error(`${name} é obrigatório.`);
  return value;
}

export function loadConfig() {
  const encryptionKey = Buffer.from(
    required("WHATSAPP_AUTH_ENCRYPTION_KEY"),
    "base64"
  );
  if (encryptionKey.length !== 32) {
    throw new Error("WHATSAPP_AUTH_ENCRYPTION_KEY deve representar 32 bytes em base64.");
  }
  return {
    port: Number.parseInt(process.env.PORT ?? "3030", 10),
    databaseUrl: required("DATABASE_URL"),
    bearerToken: required("WHATSAPP_GATEWAY_TOKEN"),
    encryptionKey,
    sessionId: (process.env.WHATSAPP_SESSION_ID ?? "clinic-primary").trim(),
    minSendIntervalMs: Number.parseInt(
      process.env.WHATSAPP_MIN_SEND_INTERVAL_MS ?? "1100",
      10
    )
  };
}
