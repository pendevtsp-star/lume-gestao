(() => {
  const destinationTime = document.querySelector("[data-reschedule-destination-time]");
  const destinationCapacity = document.querySelector("[data-reschedule-destination-capacity]");

  document.querySelectorAll("[data-reschedule-slot]").forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) return;
      if (destinationTime) destinationTime.textContent = input.dataset.slotLabel || "Horario selecionado";
      if (destinationCapacity) destinationCapacity.textContent = input.dataset.slotCapacity || "Vaga confirmada";
    });
  });

  document.querySelectorAll("[data-open-appointment]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const dialog = document.getElementById(trigger.dataset.openAppointment);
      if (!dialog || typeof dialog.showModal !== "function") return;
      dialog.showModal();
      dialog.querySelector("[data-close-dialog]")?.focus();
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog")?.close());
  });

  document.querySelectorAll(".agenda-action-modal").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
})();
