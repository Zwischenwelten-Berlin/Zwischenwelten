/*
 * ZWISCHENWELTEN Cookie-Consent (selbst gehostet, ohne Drittanbieter)
 *
 * Kategorien: necessary (immer aktiv), media, statistics
 * Speicherung: localStorage "zw-consent" = {v, ts, media, statistics}
 * Einwilligung läuft nach 12 Monaten ab oder wenn CONSENT_VERSION erhöht wird.
 *
 * Inhalte erst nach Einwilligung laden:
 *   <script type="text/plain" data-consent="statistics" data-src="..."></script>
 *   <script type="text/plain" data-consent="statistics">inline code</script>
 *   <iframe data-consent-src="https://..." data-consent="media"></iframe>
 *   <img data-consent-src="https://..." data-consent="media">
 *
 * API: window.zwConsent.open() / .get() / .has("media")
 */
(function () {
  "use strict";

  var CONSENT_VERSION = 2; // 2: Google Tag Manager / Analytics in „Statistik“
  var STORAGE_KEY = "zw-consent";
  var MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000; // 12 Monate

  var CATEGORIES = [
    {
      id: "necessary",
      label: "Notwendig",
      locked: true,
      desc: "Erforderlich für die Grundfunktionen der Website und zum Speichern Ihrer Cookie-Auswahl. Es werden keine Daten an Dritte übertragen."
    },
    {
      id: "media",
      label: "Externe Medien",
      locked: false,
      desc: "Inhalte von Videoplattformen (z. B. YouTube) werden erst nach Ihrer Einwilligung geladen. Dabei können personenbezogene Daten (z. B. Ihre IP-Adresse) an die Anbieter übertragen werden."
    },
    {
      id: "statistics",
      label: "Statistik",
      locked: false,
      desc: "Google Tag Manager und Google Analytics helfen uns zu verstehen, wie die Website genutzt wird. Dabei werden Cookies gesetzt und Nutzungsdaten (z. B. Ihre IP-Adresse) an Google übertragen, auch in die USA. Werbefunktionen sind deaktiviert."
    }
  ];

  /* ---------- Speicherung ---------- */

  function readConsent() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || data.v !== CONSENT_VERSION) return null;
      if (!data.ts || Date.now() - data.ts > MAX_AGE_MS) return null;
      return data;
    } catch (e) {
      return null;
    }
  }

  function writeConsent(choices) {
    var data = {
      v: CONSENT_VERSION,
      ts: Date.now(),
      media: !!choices.media,
      statistics: !!choices.statistics
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      /* z. B. Privatmodus – Banner erscheint dann erneut */
    }
    return data;
  }

  /* ---------- Inhalte freischalten ---------- */

  function activateGated(consent) {
    var granted = function (cat) {
      return cat === "necessary" || !!(consent && consent[cat]);
    };

    // <script type="text/plain" data-consent="...">
    var scripts = document.querySelectorAll('script[type="text/plain"][data-consent]');
    Array.prototype.forEach.call(scripts, function (el) {
      if (!granted(el.getAttribute("data-consent"))) return;
      var s = document.createElement("script");
      if (el.getAttribute("data-src")) s.src = el.getAttribute("data-src");
      else s.textContent = el.textContent;
      Array.prototype.forEach.call(el.attributes, function (attr) {
        if (["type", "data-consent", "data-src"].indexOf(attr.name) === -1) {
          s.setAttribute(attr.name, attr.value);
        }
      });
      el.parentNode.replaceChild(s, el);
    });

    // <iframe|img data-consent-src="..." data-consent="...">
    var embeds = document.querySelectorAll("[data-consent-src][data-consent]");
    Array.prototype.forEach.call(embeds, function (el) {
      if (!granted(el.getAttribute("data-consent"))) return;
      el.setAttribute("src", el.getAttribute("data-consent-src"));
      el.removeAttribute("data-consent-src");
      el.removeAttribute("data-consent");
    });
  }

  /* ---------- UI ---------- */

  var els = { backdrop: null, banner: null, modal: null };
  var lastFocus = null;

  function removeUI() {
    ["backdrop", "banner", "modal"].forEach(function (k) {
      if (els[k] && els[k].parentNode) els[k].parentNode.removeChild(els[k]);
      els[k] = null;
    });
    document.removeEventListener("keydown", onKeydown);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }

  function onKeydown(e) {
    if (e.key === "Escape" && els.modal && readConsent()) {
      // Schließen ohne Änderung nur möglich, wenn schon eine Auswahl existiert
      removeUI();
    }
    if (e.key === "Tab" && (els.modal || els.banner)) {
      var root = els.modal || els.banner;
      var focusables = root.querySelectorAll("button, input, a[href]");
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // Google-Analytics-Cookies (_ga, _ga_*, _gid, _gat*) beim Widerruf entfernen
  function removeAnalyticsCookies() {
    var host = location.hostname;
    var domains = ["", host, "." + host, "." + host.split(".").slice(-2).join(".")];
    document.cookie.split(";").forEach(function (c) {
      var name = c.split("=")[0].trim();
      if (!/^(_ga|_gid|_gat)/.test(name)) return;
      domains.forEach(function (d) {
        document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/" +
          (d ? "; domain=" + d : "");
      });
    });
  }

  function decide(choices) {
    var before = readConsent();
    var after = writeConsent(choices);
    removeUI();
    // Wurde eine zuvor erteilte Einwilligung entzogen, Seite neu laden,
    // damit bereits geladene Inhalte entfernt werden.
    if (before && ((before.media && !after.media) || (before.statistics && !after.statistics))) {
      if (before.statistics && !after.statistics) removeAnalyticsCookies();
      location.reload();
      return;
    }
    activateGated(after);
    document.dispatchEvent(new CustomEvent("zw:consent", { detail: after }));
  }

  function showBackdrop() {
    if (els.backdrop) return;
    var d = document.createElement("div");
    d.className = "zw-consent-backdrop";
    document.body.appendChild(d);
    els.backdrop = d;
  }

  function showBanner() {
    removeUI();
    lastFocus = document.activeElement;
    showBackdrop();

    var b = document.createElement("div");
    b.className = "zw-consent-banner";
    b.setAttribute("role", "dialog");
    b.setAttribute("aria-modal", "true");
    b.setAttribute("aria-labelledby", "zw-consent-title");
    b.innerHTML =
      '<h2 id="zw-consent-title">Ihre Privatsphäre</h2>' +
      '<p>Wir verwenden neben technisch notwendigen Speicherfunktionen optional externe Medien ' +
      '(z. B. YouTube) sowie Statistik-Dienste (Google Tag Manager, Google Analytics). ' +
      'Diese werden erst geladen, wenn Sie einwilligen. ' +
      'Ihre Auswahl können Sie jederzeit über „Cookie-Einstellungen“ im Fußbereich ändern. ' +
      'Mehr dazu in unserer <a href="/datenschutz">Datenschutzerklärung</a>.</p>' +
      '<div class="zw-consent-actions">' +
      '<button type="button" class="zw-btn zw-btn-accent" data-action="accept-all">Alle akzeptieren</button>' +
      '<button type="button" class="zw-btn zw-btn-ghost" data-action="necessary-only">Nur notwendige</button>' +
      '<button type="button" class="zw-btn zw-btn-link" data-action="settings">Einstellungen</button>' +
      "</div>";

    b.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-action]");
      if (!btn) return;
      var action = btn.getAttribute("data-action");
      if (action === "accept-all") decide({ media: true, statistics: true });
      if (action === "necessary-only") decide({ media: false, statistics: false });
      if (action === "settings") showModal();
    });

    document.body.appendChild(b);
    document.addEventListener("keydown", onKeydown);
    els.banner = b;
    b.querySelector("button").focus();
  }

  function showModal() {
    removeUI();
    lastFocus = document.activeElement;
    showBackdrop();

    var current = readConsent() || {};
    var m = document.createElement("div");
    m.className = "zw-consent-modal";
    m.setAttribute("role", "dialog");
    m.setAttribute("aria-modal", "true");
    m.setAttribute("aria-labelledby", "zw-modal-title");

    var catsHtml = CATEGORIES.map(function (cat) {
      var control = cat.locked
        ? '<span class="zw-cat-status">Immer aktiv</span>'
        : '<label class="zw-switch">' +
          '<input type="checkbox" data-cat="' + cat.id + '"' +
          (current[cat.id] ? " checked" : "") +
          ' aria-label="' + cat.label + '">' +
          '<span class="zw-switch-track"></span>' +
          "</label>";
      return (
        '<div class="zw-cat">' +
        '<div class="zw-cat-head"><strong>' + cat.label + "</strong>" + control + "</div>" +
        "<p>" + cat.desc + "</p>" +
        "</div>"
      );
    }).join("");

    m.innerHTML =
      '<h2 id="zw-modal-title">Cookie-Einstellungen</h2>' +
      "<p>Hier können Sie festlegen, welche Kategorien Sie zulassen möchten. " +
      'Details finden Sie in unserer <a href="/datenschutz">Datenschutzerklärung</a>.</p>' +
      '<div class="zw-consent-cats">' + catsHtml + "</div>" +
      '<div class="zw-consent-actions">' +
      '<button type="button" class="zw-btn zw-btn-accent" data-action="save">Auswahl speichern</button>' +
      '<button type="button" class="zw-btn zw-btn-ghost" data-action="accept-all">Alle akzeptieren</button>' +
      '<button type="button" class="zw-btn zw-btn-link" data-action="reject-all">Alle ablehnen</button>' +
      "</div>";

    m.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-action]");
      if (!btn) return;
      var action = btn.getAttribute("data-action");
      if (action === "save") {
        var choices = {};
        Array.prototype.forEach.call(m.querySelectorAll("input[data-cat]"), function (input) {
          choices[input.getAttribute("data-cat")] = input.checked;
        });
        decide(choices);
      }
      if (action === "accept-all") decide({ media: true, statistics: true });
      if (action === "reject-all") decide({ media: false, statistics: false });
    });

    document.body.appendChild(m);
    document.addEventListener("keydown", onKeydown);
    els.modal = m;
    m.querySelector("button, input").focus();
  }

  /* ---------- Footer-Link ---------- */

  function injectFooterLink() {
    var footerLinks = document.querySelector(".footer-links");
    if (!footerLinks || footerLinks.querySelector("[data-zw-consent-link]")) return;
    var a = document.createElement("a");
    a.href = "#";
    a.textContent = "Cookie-Einstellungen";
    a.setAttribute("data-zw-consent-link", "");
    a.addEventListener("click", function (e) {
      e.preventDefault();
      showModal();
    });
    footerLinks.appendChild(a);
  }

  /* ---------- Öffentliche API ---------- */

  window.zwConsent = {
    open: showModal,
    get: readConsent,
    has: function (cat) {
      if (cat === "necessary") return true;
      var c = readConsent();
      return !!(c && c[cat]);
    }
  };

  /* ---------- Start ---------- */

  function init() {
    injectFooterLink();
    var consent = readConsent();
    if (consent) {
      activateGated(consent);
    } else {
      showBanner();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
