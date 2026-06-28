(function () {
  var faqDataElement = document.getElementById("website-faq-data");
  var faqData = {};
  if (faqDataElement) {
    try {
      faqData = JSON.parse(faqDataElement.textContent);
    } catch (_error) {
      faqData = {};
    }
  }

  var widget = document.querySelector("[data-assistant]");
  if (!widget) {
    return;
  }

  var toggle = widget.querySelector("[data-assistant-toggle]");
  var panel = widget.querySelector("[data-assistant-panel]");
  var answer = widget.querySelector("[data-assistant-answer]");
  var questionButtons = widget.querySelectorAll("[data-assistant-question]");

  if (toggle && panel) {
    toggle.addEventListener("click", function () {
      var isHidden = panel.hasAttribute("hidden");
      if (isHidden) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
    });
  }

  questionButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var question = button.getAttribute("data-assistant-question");
      answer.textContent = faqData[question] || "Posso te ajudar melhor no WhatsApp. Clique abaixo para falar com a equipe.";
    });
  });
})();
