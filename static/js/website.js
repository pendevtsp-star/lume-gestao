(function () {
  var navToggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var isOpen = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(isOpen));
      navToggle.querySelector(".material-symbols-rounded").textContent = isOpen ? "close" : "menu";
      document.body.classList.toggle("menu-open", isOpen);
    });
    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        nav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
        navToggle.querySelector(".material-symbols-rounded").textContent = "menu";
        document.body.classList.remove("menu-open");
      });
    });
  }

  var gallery = document.querySelector("[data-gallery-track]");
  var previous = document.querySelector("[data-gallery-prev]");
  var next = document.querySelector("[data-gallery-next]");
  function moveGallery(direction) {
    if (!gallery) return;
    gallery.scrollBy({ left: direction * Math.max(320, gallery.clientWidth * 0.72), behavior: "smooth" });
  }
  if (previous) previous.addEventListener("click", function () { moveGallery(-1); });
  if (next) next.addEventListener("click", function () { moveGallery(1); });

  document.querySelectorAll(".site-message").forEach(function (message) {
    window.setTimeout(function () { message.remove(); }, 7000);
  });
})();
