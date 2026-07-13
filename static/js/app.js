(() => {
  const storagePrefix = "lume:filters:";

  document.querySelectorAll("form[data-persist-filters]").forEach((form) => {
    const key = storagePrefix + (form.dataset.persistFilters || window.location.pathname);
    const hasUrlFilters = window.location.search.length > 1;

    if (!hasUrlFilters) {
      try {
        const values = JSON.parse(window.sessionStorage.getItem(key) || "{}");
        Object.entries(values).forEach(([name, value]) => {
          const field = form.elements.namedItem(name);
          if (field && field.type !== "submit") field.value = value;
        });
      } catch (_) {
        window.sessionStorage.removeItem(key);
      }
    }

    form.addEventListener("submit", () => {
      const values = {};
      Array.from(form.elements).forEach((field) => {
        if (!field.name || field.disabled || ["submit", "button", "hidden"].includes(field.type)) return;
        values[field.name] = field.value;
      });
      window.sessionStorage.setItem(key, JSON.stringify(values));
    });

    form.querySelectorAll("[data-clear-filters]").forEach((control) => {
      control.addEventListener("click", () => window.sessionStorage.removeItem(key));
    });
  });

  document.querySelectorAll("form:not([method='get'])").forEach((form) => {
    form.addEventListener("submit", () => {
      if (form.dataset.submitting) return;
      form.dataset.submitting = "true";
      form.classList.add("is-submitting");
      form.querySelectorAll("button[type='submit']").forEach((button) => {
        button.disabled = true;
        button.dataset.label = button.textContent;
        button.setAttribute("aria-busy", "true");
        button.textContent = button.dataset.submittingLabel || "Salvando...";
      });
    });
  });

  document.querySelectorAll(".message").forEach((message) => {
    const close = document.createElement("button");
    close.type = "button";
    close.className = "message-close";
    close.setAttribute("aria-label", "Fechar aviso");
    close.textContent = "×";
    close.addEventListener("click", () => message.remove());
    message.appendChild(close);
  });

  let installPrompt = null;
  const installButtons = document.querySelectorAll("[data-pwa-install]");

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons.forEach((button) => {
      button.hidden = false;
    });
  });

  installButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      if (!installPrompt) return;
      await installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      installButtons.forEach((item) => {
        item.hidden = true;
      });
    });
  });

  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    installButtons.forEach((button) => {
      button.hidden = true;
    });
  });
})();
