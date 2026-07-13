import express from "express";
import { rm } from "node:fs/promises";
import path from "node:path";
import QRCode from "qrcode";
import qrcodeTerminal from "qrcode-terminal";
import pkg from "whatsapp-web.js";

const { Client, LocalAuth } = pkg;

const app = express();
const port = Number(process.env.WHATSAPP_WEB_GATEWAY_PORT || 3020);
const token = process.env.WHATSAPP_WEB_GATEWAY_TOKEN || "";
const sessionDir = process.env.WHATSAPP_WEB_SESSION_DIR || "/data/session";

let latestQr = "";
let ready = false;
let connectedNumber = "";
let lastError = "";
let sendQueue = Promise.resolve();
let lastSentAt = 0;

async function clearStaleChromiumLocks() {
  const profileDir = path.join(sessionDir, "session");
  await Promise.all(
    ["SingletonLock", "SingletonSocket", "SingletonCookie"].map((name) =>
      rm(path.join(profileDir, name), { force: true })
    )
  );
}

app.use(express.json({ limit: "256kb" }));

function requireToken(request, response, next) {
  if (!token) {
    next();
    return;
  }
  const expected = `Bearer ${token}`;
  if (request.get("authorization") !== expected) {
    response.status(401).json({ ok: false, error: "Unauthorized" });
    return;
  }
  next();
}

function onlyDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function queueSend(callback) {
  const next = sendQueue.then(callback, callback);
  // Keep the queue usable even when an individual delivery fails.
  sendQueue = next.catch(() => undefined);
  return next;
}

async function resolveRecipientId(number) {
  const fallback = `${number}@c.us`;

  try {
    const resolved = await client.getNumberId(fallback);
    if (resolved?._serialized) {
      return resolved._serialized;
    }
  } catch (error) {
    console.warn("[whatsapp-web] Nao foi possivel resolver destinatario antes do envio:", error.message || error);
  }

  return fallback;
}

async function deliverMessage(number, message) {
  const recipientId = await resolveRecipientId(number);
  const elapsed = Date.now() - lastSentAt;
  if (elapsed < 1100) {
    await wait(1100 - elapsed);
  }

  try {
    const sent = await client.sendMessage(recipientId, message);
    lastSentAt = Date.now();
    return sent;
  } catch (error) {
    if (!/No LID for user/i.test(error.message || "")) {
      throw error;
    }

    // WhatsApp Web can refresh a contact from a LID to a phone JID between
    // lookup and delivery. Retry once using the canonical phone JID.
    await wait(900);
    const sent = await client.sendMessage(`${number}@c.us`, message);
    lastSentAt = Date.now();
    return sent;
  }
}

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: sessionDir
  }),
  puppeteer: {
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--no-zygote",
      "--disable-gpu"
    ]
  }
});

client.on("qr", (qr) => {
  latestQr = qr;
  ready = false;
  lastError = "";
  console.log("[whatsapp-web] QR recebido. Escaneie pela tela de integracoes do Lume.");
  qrcodeTerminal.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("[whatsapp-web] Sessao autenticada.");
});

client.on("ready", () => {
  ready = true;
  latestQr = "";
  connectedNumber = client.info?.wid?.user || "";
  lastError = "";
  console.log(`[whatsapp-web] Pronto para envio. Numero: ${connectedNumber || "desconhecido"}.`);
});

client.on("auth_failure", (message) => {
  ready = false;
  lastError = message || "Falha de autenticacao.";
  console.error("[whatsapp-web] Falha de autenticacao:", lastError);
});

client.on("disconnected", (reason) => {
  ready = false;
  connectedNumber = "";
  lastError = reason || "Sessao desconectada.";
  console.warn("[whatsapp-web] Sessao desconectada:", lastError);
  setTimeout(() => {
    client.initialize().catch((error) => {
      lastError = error.message || String(error);
      console.error("[whatsapp-web] Falha ao reiniciar cliente:", lastError);
    });
  }, 5000);
});

app.get("/healthz", (_request, response) => {
  response.json({
    ok: true,
    ready,
    hasQr: Boolean(latestQr),
    connectedNumber,
    lastError
  });
});

app.get("/qr", requireToken, async (_request, response) => {
  let qrDataUrl = "";
  if (latestQr) {
    qrDataUrl = await QRCode.toDataURL(latestQr);
  }
  response.json({
    ok: true,
    ready,
    hasQr: Boolean(latestQr),
    qr: latestQr,
    qrDataUrl,
    connectedNumber,
    lastError
  });
});

app.post("/send", requireToken, async (request, response) => {
  if (!ready) {
    response.status(503).json({ ok: false, ready: false, error: "Sessao WhatsApp Web ainda nao conectada." });
    return;
  }

  const to = onlyDigits(request.body?.to);
  const message = String(request.body?.message || "").trim();
  if (!to || !message) {
    response.status(400).json({ ok: false, error: "Informe destinatario e mensagem." });
    return;
  }

  try {
    const sent = await queueSend(() => deliverMessage(to, message));
    lastError = "";
    response.json({
      ok: true,
      provider: "whatsapp_web",
      to,
      messageId: sent.id?._serialized || "",
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    lastError = error.message || String(error);
    response.status(502).json({ ok: false, error: lastError });
  }
});

app.listen(port, () => {
  console.log(`[whatsapp-web] Gateway ouvindo na porta ${port}.`);
});

clearStaleChromiumLocks()
  .then(() => client.initialize())
  .catch((error) => {
    lastError = error.message || String(error);
    console.error("[whatsapp-web] Falha ao iniciar cliente:", lastError);
  });
