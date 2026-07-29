import { ProviderError } from "./errors.js";

export function normalizeConnectionUpdate(update) {
  if (update.qr) return { state: "qr_ready", ready: false, hasQr: true };
  if (update.connection === "open") {
    return { state: "ready", ready: true, hasQr: false };
  }
  if (update.connection === "close") {
    return { state: "reconnecting", ready: false, hasQr: false };
  }
  return null;
}

function disconnectStatusCode(update) {
  const rawCode = update?.lastDisconnect?.error?.output?.statusCode
    ?? update?.lastDisconnect?.error?.statusCode;
  const code = Number(rawCode);
  return Number.isInteger(code) ? code : 0;
}

export function connectionCloseDecision(update, disconnectReason = {}) {
  const code = disconnectStatusCode(update);
  const lastErrorCode = `DISCONNECTED_${code || "UNKNOWN"}`;
  if (code === disconnectReason.loggedOut) {
    return { reconnect: false, state: "logged_out", lastErrorCode };
  }
  if ([
    disconnectReason.connectionReplaced,
    disconnectReason.badSession,
    disconnectReason.multideviceMismatch,
    disconnectReason.forbidden
  ].includes(code)) {
    return { reconnect: false, state: "error", lastErrorCode };
  }
  return { reconnect: true, state: "reconnecting", lastErrorCode };
}

function connectedNumber(socket) {
  const jid = socket?.user?.id ?? "";
  return jid.split(":")[0].split("@")[0].replace(/\D/g, "");
}

export class ConnectionManager {
  constructor({
    makeWASocket,
    authStore,
    outboundCoordinator,
    baileys,
    qrCode,
    logger,
    baileysLogger,
    schedule = setTimeout,
    clearSchedule = clearTimeout,
    minSendIntervalMs = 1100
  }) {
    this.makeWASocket = makeWASocket;
    this.authStore = authStore;
    this.outboundCoordinator = outboundCoordinator;
    this.baileys = baileys;
    this.qrCode = qrCode;
    this.logger = logger;
    this.baileysLogger = baileysLogger;
    this.schedule = schedule;
    this.clearSchedule = clearSchedule;
    this.minSendIntervalMs = minSendIntervalMs;
    this.socket = null;
    this.qrDataUrl = null;
    this.status = { state: "starting", ready: false, hasQr: false };
    this.nextSendAt = 0;
    this.sendChain = Promise.resolve();
    this.reconnectTimer = null;
    this.startPromise = null;
    this.connectionGeneration = 0;
  }

  publicStatus() {
    return {
      ok: true,
      ...this.status,
      connectedNumber: this.status.ready ? connectedNumber(this.socket) : ""
    };
  }

  async start() {
    if (this.startPromise) return this.startPromise;
    this.startPromise = this.#startSocket();
    try {
      await this.startPromise;
    } finally {
      this.startPromise = null;
    }
  }

  async #startSocket() {
    this.#cancelReconnect();
    this.#detachSocket();
    const { initAuthCreds, BufferJSON, proto } = this.baileys;
    const { state, saveCreds } = await this.authStore.loadState({
      initAuthCreds,
      BufferJSON,
      proto
    });
    this.status = { state: "connecting", ready: false, hasQr: false };
    this.connectionGeneration += 1;
    this.socket = this.makeWASocket({
      auth: state,
      logger: this.baileysLogger,
      markOnlineOnConnect: false,
      syncFullHistory: false,
      shouldSyncHistoryMessage: () => false,
      emitOwnEvents: false,
      generateHighQualityLinkPreview: false
    });
    this.socket.ev.on("creds.update", saveCreds);
    this.socket.ev.on("connection.update", (update) => {
      void this.#handleConnectionUpdate(update).catch(() => {
        this.qrDataUrl = null;
        this.status = {
          state: "error",
          ready: false,
          hasQr: false,
          lastErrorCode: "CONNECTION_UPDATE_FAILED",
          lastError: ""
        };
        this.logger.error(
          { event: "whatsapp_connection_update_failed" },
          "Falha ao processar atualização da conexão WhatsApp."
        );
      });
    });
  }

  async #handleConnectionUpdate(update) {
    const normalized = normalizeConnectionUpdate(update);
    if (update.connection !== "close" && normalized) {
      this.status = {
        ...normalized,
        lastErrorCode: "",
        lastError: ""
      };
    }
    if (update.qr) {
      this.qrDataUrl = await this.qrCode.toDataURL(update.qr, {
        errorCorrectionLevel: "M",
        margin: 1
      });
      this.logger.info({ event: "whatsapp_qr_ready" }, "QR disponível.");
    }
    if (update.connection === "open") {
      this.qrDataUrl = null;
      this.logger.info(
        { event: "whatsapp_connected", session: this.authStore.sessionId },
        "Sessão WhatsApp conectada."
      );
    }
    if (update.connection === "close") {
      this.qrDataUrl = null;
      const decision = connectionCloseDecision(
        update,
        this.baileys.DisconnectReason
      );
      this.status = {
        state: decision.state,
        ready: false,
        hasQr: false,
        lastErrorCode: decision.lastErrorCode,
        lastError: ""
      };
      this.#detachSocket();
      if (decision.reconnect) {
        this.logger.warn(
          {
            event: "whatsapp_reconnecting",
            session: this.authStore.sessionId,
            reasonCode: decision.lastErrorCode
          },
          "Conexão WhatsApp encerrada; reconexão agendada."
        );
        this.#scheduleReconnect();
      } else {
        this.logger.warn(
          {
            event: "whatsapp_connection_stopped",
            session: this.authStore.sessionId,
            reasonCode: decision.lastErrorCode
          },
          "Conexão WhatsApp encerrada e requer intervenção."
        );
      }
    }
  }

  #detachSocket() {
    if (this.socket?.ev) {
      this.socket.ev.removeAllListeners("connection.update");
      this.socket.ev.removeAllListeners("creds.update");
    }
  }

  #cancelReconnect() {
    if (this.reconnectTimer !== null) {
      this.clearSchedule(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  #scheduleReconnect() {
    if (this.reconnectTimer !== null) return;
    this.reconnectTimer = this.schedule(() => {
      this.reconnectTimer = null;
      void this.start().catch(() => {
        this.status = {
          state: "error",
          ready: false,
          hasQr: false,
          lastErrorCode: "RECONNECT_FAILED",
          lastError: ""
        };
        this.logger.error(
          { event: "whatsapp_reconnect_failed" },
          "Falha ao reconstruir a conexão WhatsApp."
        );
      });
    }, 1500);
  }

  qrStatus() {
    return { ...this.publicStatus(), qrDataUrl: this.qrDataUrl };
  }

  async restart() {
    this.#cancelReconnect();
    this.status = { state: "connecting", ready: false, hasQr: false };
    this.#detachSocket();
    if (this.socket?.ws) this.socket.ws.close();
    this.socket = null;
    await this.start();
    return this.publicStatus();
  }

  async logout() {
    this.status = { state: "logged_out", ready: false, hasQr: false };
    try {
      this.#cancelReconnect();
      this.#detachSocket();
      if (this.socket) await this.socket.logout();
    } catch (_error) {
      this.logger.warn(
        { event: "whatsapp_logout_session_already_closed" },
        "A sessão já estava encerrada; as credenciais locais serão limpas."
      );
    }
    await this.authStore.clearSession();
    this.socket = null;
    this.qrDataUrl = null;
    this.status = { state: "logged_out", ready: false, hasQr: false };
    await this.start();
    return this.publicStatus();
  }

  async sendText({ requestId, recipient, message }) {
    this.#assertReady();
    return this.#serializeSend(() => {
      this.#assertReady();
      const socket = this.socket;
      const generation = this.connectionGeneration;
      return this.outboundCoordinator.send({
        requestId,
        recipient,
        message,
        deliver: async () => {
          if (
            generation !== this.connectionGeneration
            || socket !== this.socket
            || !this.status.ready
          ) {
            throw new ProviderError("A sessão ainda não está pronta.", {
              code: "SESSION_NOT_READY",
              retryable: true,
              httpStatus: 503
            });
          }
          const response = await socket.sendMessage(
            `${recipient}@s.whatsapp.net`,
            { text: message }
          );
          const messageId = response?.key?.id;
          if (!messageId) {
            throw new ProviderError("O provedor não retornou a confirmação do envio.", {
              code: "DELIVERY_RESULT_UNKNOWN",
              deliveryUncertain: true,
              httpStatus: 502
            });
          }
          return { messageId };
        }
      });
    });
  }

  #assertReady() {
    if (!this.status.ready || !this.socket) {
      throw new ProviderError("A sessão ainda não está pronta.", {
        code: "SESSION_NOT_READY",
        retryable: true,
        httpStatus: 503
      });
    }
  }

  #serializeSend(operation) {
    const pending = this.sendChain.then(async () => {
      const waitMs = Math.max(0, this.nextSendAt - Date.now());
      if (waitMs) await new Promise((resolve) => setTimeout(resolve, waitMs));
      this.nextSendAt = Date.now() + this.minSendIntervalMs;
      return operation();
    });
    this.sendChain = pending.catch(() => undefined);
    return pending;
  }
}
