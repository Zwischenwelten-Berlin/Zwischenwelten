/*
 * ZWISCHENWELTEN Mediathek (/videos, /podcasts)
 *
 *  - YouTube-Karten: <a class="video-thumb" data-yt="ID"> öffnet den Player in
 *    der Karte (youtube-nocookie.com). Ohne Einwilligung „Externe Medien“
 *    (assets/consent.js) erscheint zuerst ein Hinweis mit „Video laden“.
 *    Ohne JavaScript führt der Link einfach zu YouTube.
 *  - Sprachfilter: .lang-filter[data-filter-target] wie auf /aktuelles.
 *  - Podcast-Player: ein <audio> für die ganze Seite, Steuerung in #player.
 */
(function () {
  "use strict";

  /* ---------- Videos ---------- */

  function hasMediaConsent() {
    return !!(window.zwConsent && window.zwConsent.has("media"));
  }

  function frameFor(thumb) {
    var frame = document.createElement("div");
    frame.className = "video-frame";
    thumb.parentNode.replaceChild(frame, thumb);
    return frame;
  }

  function embed(frame, id, title) {
    var iframe = document.createElement("iframe");
    iframe.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) +
      "?autoplay=1&rel=0&modestbranding=1";
    iframe.title = title ? "YouTube-Video: " + title : "YouTube-Video";
    iframe.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    frame.innerHTML = "";
    frame.appendChild(iframe);
    frame.closest(".video-card").classList.add("is-playing");
    iframe.focus();
  }

  function askConsent(frame, thumb, id, title) {
    var img = thumb.querySelector("img");
    if (img) frame.appendChild(img.cloneNode());
    var box = document.createElement("div");
    box.className = "video-consent";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Externes Video laden");
    box.innerHTML =
      "<p>Dieses Video wird von YouTube abgespielt. Beim Laden werden Daten wie deine " +
      'IP-Adresse an Google übertragen. Mehr in der <a href="/datenschutz">Datenschutzerklärung</a>.</p>' +
      '<div class="actions">' +
      '<button type="button" class="pill-btn" data-load>Video laden</button>' +
      '<a href="https://www.youtube.com/watch?v=' + encodeURIComponent(id) +
      '" target="_blank" rel="noopener">Auf YouTube ansehen ↗</a>' +
      "</div>";
    frame.appendChild(box);
    var btn = box.querySelector("[data-load]");
    btn.addEventListener("click", function () { embed(frame, id, title); });
    btn.focus();
  }

  document.addEventListener("click", function (e) {
    var thumb = e.target.closest && e.target.closest(".video-thumb[data-yt]");
    if (!thumb || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    var id = thumb.getAttribute("data-yt");
    var titleEl = thumb.closest(".video-card").querySelector(".video-title");
    var title = titleEl ? titleEl.textContent : "";
    if (hasMediaConsent()) {
      embed(frameFor(thumb), id, title);
    } else {
      var clone = thumb.cloneNode(true);
      askConsent(frameFor(thumb), clone, id, title);
    }
  });

  document.addEventListener("click", function (e) {
    var opener = e.target.closest && e.target.closest("[data-consent-open]");
    if (!opener || !window.zwConsent) return;
    e.preventDefault();
    window.zwConsent.open();
  });

  /* ---------- Sprachfilter ---------- */

  Array.prototype.forEach.call(document.querySelectorAll(".lang-filter[data-filter-target]"), function (bar) {
    var target = document.querySelector(bar.getAttribute("data-filter-target"));
    var empty = document.querySelector(bar.getAttribute("data-filter-empty"));
    var chips = bar.querySelectorAll(".lang-chip");
    if (!target) return;

    function apply(lang) {
      var visible = 0;
      Array.prototype.forEach.call(chips, function (c) {
        c.setAttribute("aria-pressed", c.getAttribute("data-lang") === lang ? "true" : "false");
      });
      Array.prototype.forEach.call(target.querySelectorAll("[data-lang]"), function (item) {
        var show = lang === "all" || item.getAttribute("data-lang") === lang;
        item.classList.toggle("is-filtered-out", !show);
        if (show) visible++;
      });
      if (empty) empty.classList.toggle("is-visible", visible === 0);
    }

    Array.prototype.forEach.call(chips, function (chip) {
      chip.addEventListener("click", function () { apply(chip.getAttribute("data-lang")); });
    });
  });

  /* ---------- Podcast-Player ---------- */

  var bar = document.getElementById("player");
  if (!bar) return;

  var audio = new Audio();
  audio.preload = "none";
  var toggle = bar.querySelector(".player-toggle");
  var titleEl = bar.querySelector(".player-title");
  var seek = bar.querySelector(".player-seek input");
  var elapsed = bar.querySelector("[data-elapsed]");
  var remaining = bar.querySelector("[data-remaining]");
  var rateBtn = bar.querySelector(".player-rate");
  var RATES = [1, 1.25, 1.5, 2];
  var current = null; // the .episode element being played
  var seeking = false;

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
    var mm = h ? String(m).padStart(2, "0") : String(m);
    return (h ? h + ":" : "") + mm + ":" + String(s).padStart(2, "0");
  }

  function duration() {
    return isFinite(audio.duration) && audio.duration > 0
      ? audio.duration
      : Number(current && current.getAttribute("data-duration")) || 0;
  }

  function render() {
    var d = duration(), t = audio.currentTime;
    if (!seeking) seek.value = d ? Math.round(t / d * 1000) : 0;
    elapsed.textContent = fmt(t);
    remaining.textContent = "−" + fmt(d - t);
    seek.setAttribute("aria-valuetext", fmt(t) + " von " + fmt(d));
  }

  function setPlaying(playing) {
    bar.classList.toggle("is-playing", playing);
    toggle.setAttribute("aria-label", playing ? "Pause" : "Abspielen");
    Array.prototype.forEach.call(document.querySelectorAll(".episode"), function (ep) {
      var isThis = ep === current;
      ep.classList.toggle("is-current", isThis);
      ep.classList.toggle("is-playing", isThis && playing);
      var btn = ep.querySelector(".episode-play");
      var name = ep.getAttribute("data-title");
      btn.setAttribute("aria-label", (isThis && playing ? "Pause: " : "Abspielen: ") + name);
    });
  }

  function load(ep) {
    current = ep;
    audio.src = ep.getAttribute("data-src");
    audio.playbackRate = Number(rateBtn.getAttribute("data-rate")) || 1;
    titleEl.textContent = ep.getAttribute("data-title");
    var lang = ep.getAttribute("lang");
    if (lang) titleEl.setAttribute("lang", lang); else titleEl.removeAttribute("lang");
    titleEl.dir = ep.getAttribute("dir") || "auto";
    bar.hidden = false;
    document.body.classList.add("has-player");
    if ("mediaSession" in navigator && window.MediaMetadata) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: ep.getAttribute("data-title"),
        artist: bar.getAttribute("data-show") || "ZWISCHENWELTEN"
      });
    }
    render();
  }

  function play() {
    var p = audio.play();
    if (p && p.catch) p.catch(function () { setPlaying(false); });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".episode-play");
    if (!btn) return;
    var ep = btn.closest(".episode");
    if (ep === current) {
      if (audio.paused) play(); else audio.pause();
      return;
    }
    load(ep);
    play();
  });

  toggle.addEventListener("click", function () {
    if (!current) return;
    if (audio.paused) play(); else audio.pause();
  });

  Array.prototype.forEach.call(bar.querySelectorAll("[data-skip]"), function (b) {
    b.addEventListener("click", function () {
      var d = duration();
      audio.currentTime = Math.min(Math.max(0, audio.currentTime + Number(b.getAttribute("data-skip"))), d || Infinity);
      render();
    });
  });

  seek.addEventListener("input", function () {
    seeking = true;
    var d = duration();
    elapsed.textContent = fmt(seek.value / 1000 * d);
  });
  seek.addEventListener("change", function () {
    audio.currentTime = seek.value / 1000 * duration();
    seeking = false;
    render();
  });

  rateBtn.addEventListener("click", function () {
    var i = RATES.indexOf(Number(rateBtn.getAttribute("data-rate")) || 1);
    var next = RATES[(i + 1) % RATES.length];
    audio.playbackRate = next;
    rateBtn.setAttribute("data-rate", next);
    rateBtn.textContent = String(next).replace(".", ",") + "×";
    rateBtn.setAttribute("aria-label", "Geschwindigkeit: " + rateBtn.textContent);
  });

  audio.addEventListener("play", function () { setPlaying(true); });
  audio.addEventListener("pause", function () { setPlaying(false); });
  audio.addEventListener("ended", function () { setPlaying(false); });
  audio.addEventListener("timeupdate", render);
  audio.addEventListener("loadedmetadata", render);
})();
