/*
 * Hauptnavigation: Untermenüs (.nav-sub, z. B. „Mediathek“) öffnen per
 * Klick/Tippen – auf Touch-Geräten gibt es kein Hover. Ohne JavaScript führt
 * der Menüpunkt einfach zu seiner ersten Seite (href).
 */
(function () {
  "use strict";

  var subs = document.querySelectorAll(".nav-sub");
  if (!subs.length) return;

  function setOpen(sub, open) {
    sub.classList.toggle("is-open", open);
    sub.querySelector(".nav-sub-toggle").setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAll(except) {
    Array.prototype.forEach.call(subs, function (sub) {
      if (sub !== except) setOpen(sub, false);
    });
  }

  Array.prototype.forEach.call(subs, function (sub) {
    var toggle = sub.querySelector(".nav-sub-toggle");
    if (!toggle) return;
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-haspopup", "true");
    toggle.addEventListener("click", function (e) {
      e.preventDefault();
      var open = !sub.classList.contains("is-open");
      closeAll(sub);
      setOpen(sub, open);
    });
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".nav-sub")) closeAll(null);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var open = document.querySelector(".nav-sub.is-open");
    if (!open) return;
    setOpen(open, false);
    open.querySelector(".nav-sub-toggle").focus();
  });
})();
