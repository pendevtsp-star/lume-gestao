(function () {
  const poller = document.querySelector("[data-whatsapp-qr-poller]");
  if (!poller) return;

  const qrUrl = poller.dataset.qrUrl;
  const statusUrl = poller.dataset.statusUrl;
  const frame = poller.querySelector("[data-qr-frame]");
  const image = poller.querySelector("[data-qr-image]");
  const placeholder = poller.querySelector("[data-qr-placeholder]");
  const message = poller.querySelector("[data-qr-message]");
  if (!qrUrl || !statusUrl || !frame || !image || !placeholder) return;
  let stopped = false;
  let pollDelay = 2000;
  let pollTimer = null;
  let polling = false;

  function showMessage(text) {
    if (message) message.textContent = text;
  }

  function showQr(dataUrl) {
    if (!dataUrl.startsWith("data:image/png;base64,")) return false;
    image.src = dataUrl;
    frame.hidden = false;
    placeholder.hidden = true;
    return true;
  }

  async function requestJson(url) {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("gateway_unavailable");
    return response.json();
  }

  async function poll() {
    if (stopped || polling || document.hidden) return;
    polling = true;
    try {
      const qrState = await requestJson(qrUrl);
      if (qrState.ready) {
        stopped = true;
        window.location.reload();
        return;
      }
      if (qrState.qrDataUrl) showQr(qrState.qrDataUrl);

      const status = await requestJson(statusUrl);
      if (status.ready) {
        stopped = true;
        window.location.reload();
        return;
      }
      if (!qrState.qrDataUrl) {
        showMessage("A conexão está sendo preparada. O QR Code aparecerá automaticamente.");
      }
    } catch (_error) {
      showMessage("O serviço de conexão ainda não respondeu. Tente preparar a conexão novamente.");
    } finally {
      polling = false;
    }

    pollDelay = Math.min(pollDelay + 100, 5000);
    pollTimer = window.setTimeout(poll, pollDelay);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
      return;
    }
    if (!document.hidden && !stopped) {
      pollDelay = 2000;
      window.clearTimeout(pollTimer);
      pollTimer = null;
      poll();
    }
  });
  poll();
})();
