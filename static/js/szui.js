/* =====================================================================
   SHAN ZEE — UI KIT  (szui.js)
   Replaces the browser's alert()/confirm() with branded components and
   powers the "guidance" panels.  No dependencies (Bootstrap is optional,
   used only to switch on tooltips when it is present).

   API
     SZ.toast(message, type?, opts?)   non-blocking message   type: success | danger | warning | info
     SZ.alert(message, opts?)          modal message           -> Promise<void>
     SZ.confirm(message, opts?)        modal yes/no            -> Promise<boolean>
   Compatibility
     window.alert(msg)   -> SZ.toast (so stray alert() calls never show the grey browser box)
     window.showToast()  -> SZ.toast
   Declarative
     <button data-sz-confirm="Delete this?" data-sz-confirm-title="Delete"
             data-sz-confirm-ok="Yes, delete" data-sz-confirm-tone="danger">
     Works on <a>, <button> and <form> (form: put it on the form tag).
   Guidance panels
     <div class="sz-guide" data-guide="unique-id"> … </div>   (see modern.css)
   ===================================================================== */
(function () {
  "use strict";

  var ICONS = {
    success: "bi-check-circle-fill",
    danger: "bi-x-octagon-fill",
    warning: "bi-exclamation-triangle-fill",
    info: "bi-info-circle-fill"
  };
  var TITLES = { success: "Success", danger: "Something went wrong", warning: "Please check", info: "Good to know" };

  function norm(type) {
    type = String(type || "info").toLowerCase();
    if (type === "error" || type === "rust" || type === "red") return "danger";
    if (type === "ok" || type === "brass") return "success";
    return ICONS[type] ? type : "info";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function store(get, key, val) {
    try { return get ? window.localStorage.getItem(key) : window.localStorage.setItem(key, val); } catch (e) { return null; }
  }
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------ TOASTS ------------------------------ */
  var stack;
  function getStack() {
    if (stack && document.body.contains(stack)) return stack;
    stack = document.createElement("div");
    stack.className = "sz-toasts";
    stack.setAttribute("aria-live", "polite");
    stack.setAttribute("aria-atomic", "false");
    document.body.appendChild(stack);
    return stack;
  }

  function toast(message, type, opts) {
    opts = opts || {};
    type = norm(type);
    var el = document.createElement("div");
    var duration = opts.duration == null ? (type === "danger" ? 7000 : type === "warning" ? 6000 : 4200) : opts.duration;
    el.className = "sz-toast sz-" + type;
    el.setAttribute("role", type === "danger" || type === "warning" ? "alert" : "status");
    el.innerHTML =
      '<span class="sz-toast-ico"><i class="bi ' + (opts.icon || ICONS[type]) + '"></i></span>' +
      '<div class="sz-toast-body"><strong>' + esc(opts.title || TITLES[type]) + "</strong>" +
      "<span>" + (opts.html ? message : esc(message)) + "</span></div>" +
      '<button type="button" class="sz-toast-x" aria-label="Dismiss"><i class="bi bi-x-lg"></i></button>' +
      (duration > 0 ? '<i class="sz-toast-bar" style="animation-duration:' + duration + 'ms"></i>' : "");
    var s = getStack();
    s.appendChild(el);
    // keep at most 4 on screen
    while (s.children.length > 4) s.removeChild(s.firstChild);
    requestAnimationFrame(function () { el.classList.add("in"); });

    var timer, remaining = duration, started;
    function close() {
      clearTimeout(timer);
      if (!el.parentNode) return;
      el.classList.remove("in");
      el.classList.add("out");
      setTimeout(function () { el.parentNode && el.parentNode.removeChild(el); }, reduceMotion ? 0 : 320);
    }
    function start() { if (duration > 0) { started = Date.now(); timer = setTimeout(close, remaining); } }
    function pause() { if (duration > 0) { clearTimeout(timer); remaining -= Date.now() - started; el.classList.add("paused"); } }
    function resume() { el.classList.remove("paused"); start(); }
    el.querySelector(".sz-toast-x").addEventListener("click", close);
    el.addEventListener("mouseenter", pause);
    el.addEventListener("mouseleave", resume);
    start();
    return { close: close };
  }

  /* ------------------------------ DIALOGS ----------------------------- */
  var lastFocus = null;
  function dialog(message, opts, isConfirm) {
    opts = opts || {};
    var tone = norm(opts.tone || (isConfirm ? "warning" : "info"));
    return new Promise(function (resolve) {
      lastFocus = document.activeElement;
      var wrap = document.createElement("div");
      wrap.className = "sz-dialog-backdrop";
      var okText = opts.okText || (isConfirm ? "Yes, continue" : "Got it");
      var cancelText = opts.cancelText || "Cancel";
      wrap.innerHTML =
        '<div class="sz-dialog sz-' + tone + '" role="alertdialog" aria-modal="true" aria-labelledby="szDlgT" aria-describedby="szDlgM">' +
        '<div class="sz-dialog-ico"><i class="bi ' + (opts.icon || ICONS[tone]) + '"></i></div>' +
        '<h3 id="szDlgT">' + esc(opts.title || (isConfirm ? "Are you sure?" : TITLES[tone])) + "</h3>" +
        '<p id="szDlgM">' + (opts.html ? message : esc(message)) + "</p>" +
        (opts.note ? '<div class="sz-dialog-note"><i class="bi bi-lightbulb-fill"></i><span>' + esc(opts.note) + "</span></div>" : "") +
        '<div class="sz-dialog-actions">' +
        (isConfirm ? '<button type="button" class="btn btn-outline-ink" data-r="0"><i class="bi bi-arrow-left"></i> ' + esc(cancelText) + "</button>" : "") +
        '<button type="button" class="btn ' + (tone === "danger" ? "btn-danger-sz" : "btn-brass") + '" data-r="1"><i class="bi ' + (isConfirm ? (tone === "danger" ? "bi-trash3" : "bi-check2-circle") : "bi-check2") + '"></i> ' + esc(okText) + "</button>" +
        "</div></div>";
      document.body.appendChild(wrap);
      document.documentElement.classList.add("sz-lock");
      requestAnimationFrame(function () { wrap.classList.add("in"); });
      var okBtn = wrap.querySelector('[data-r="1"]');
      var focusBtn = isConfirm && tone === "danger" ? wrap.querySelector('[data-r="0"]') : okBtn;
      setTimeout(function () { focusBtn && focusBtn.focus(); }, 30);

      function done(v) {
        document.removeEventListener("keydown", onKey, true);
        wrap.classList.remove("in");
        wrap.classList.add("out");
        document.documentElement.classList.remove("sz-lock");
        setTimeout(function () { wrap.parentNode && wrap.parentNode.removeChild(wrap); }, reduceMotion ? 0 : 260);
        try { lastFocus && lastFocus.focus && lastFocus.focus(); } catch (e) {}
        resolve(v);
      }
      function onKey(e) {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
        else if (e.key === "Tab") {           // simple focus trap
          var f = wrap.querySelectorAll("button");
          if (!f.length) return;
          var first = f[0], last = f[f.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
      document.addEventListener("keydown", onKey, true);
      wrap.addEventListener("click", function (e) {
        var b = e.target.closest("[data-r]");
        if (b) return done(b.getAttribute("data-r") === "1");
        if (e.target === wrap) done(false);
      });
    });
  }

  var SZ = (window.SZ = window.SZ || {});
  SZ.toast = toast;
  SZ.alert = function (m, o) { return dialog(m, o, false); };
  SZ.confirm = function (m, o) { return dialog(m, o, true); };

  /* never show the grey browser alert again */
  window.alert = function (m) { toast(m == null ? "" : String(m), "info"); };
  window.showToast = function (m, v) { toast(m, v === "rust" ? "danger" : "success"); };

  /* -------------------- declarative data-sz-confirm ------------------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-sz-confirm]");
    if (!t || t.__szOk) return;
    if (t.tagName === "FORM") return;
    e.preventDefault();
    e.stopPropagation();
    ask(t, function () {
      t.__szOk = true;
      if (typeof t.click === "function") t.click();
      setTimeout(function () { t.__szOk = false; }, 0);
    });
  }, true);
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f || !f.hasAttribute || !f.hasAttribute("data-sz-confirm") || f.__szOk) return;
    e.preventDefault();
    ask(f, function () { f.__szOk = true; (f.requestSubmit ? f.requestSubmit() : f.submit()); });
  }, true);
  function ask(el, go) {
    SZ.confirm(el.getAttribute("data-sz-confirm"), {
      title: el.getAttribute("data-sz-confirm-title") || undefined,
      okText: el.getAttribute("data-sz-confirm-ok") || undefined,
      cancelText: el.getAttribute("data-sz-confirm-cancel") || undefined,
      tone: el.getAttribute("data-sz-confirm-tone") || undefined,
      note: el.getAttribute("data-sz-confirm-note") || undefined
    }).then(function (ok) { if (ok) go(); });
  }

  /* ------------------------ ready-time enhancements ------------------- */
  function ready(fn) { document.readyState !== "loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  ready(function () {
    /* 1. server-side .alert boxes get an icon so they match the toasts */
    document.querySelectorAll(".alert").forEach(function (a) {
      if (a.querySelector(".sz-alert-ico") || a.querySelector(".bi, .fa, .fas")) return;
      var t = /alert-(success|danger|warning|info)/.exec(a.className);
      var i = document.createElement("i");
      i.className = "bi " + ICONS[t ? t[1] : "info"] + " sz-alert-ico";
      a.insertBefore(i, a.firstChild);
      a.classList.add("sz-alert");
    });

    /* 2. guidance panels: collapsible + remembered */
    document.querySelectorAll(".sz-guide[data-guide]").forEach(function (g) {
      var id = "sz-guide:" + g.getAttribute("data-guide");
      var head = g.querySelector(".sz-guide-head");
      if (!head) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sz-guide-toggle";
      btn.setAttribute("aria-expanded", "true");
      btn.innerHTML = '<span>Hide</span><i class="bi bi-chevron-up"></i>';
      head.appendChild(btn);
      function set(collapsed, save) {
        g.classList.toggle("is-collapsed", collapsed);
        btn.setAttribute("aria-expanded", String(!collapsed));
        btn.firstChild.textContent = collapsed ? "Show tips" : "Hide";
        if (save) store(false, id, collapsed ? "1" : "0");
      }
      btn.addEventListener("click", function () { set(!g.classList.contains("is-collapsed"), true); });
      head.addEventListener("click", function (e) {
        if (g.classList.contains("is-collapsed") && !e.target.closest("a, .sz-guide-toggle")) set(false, true);
      });
      if (store(true, id) === "1") set(true, false);
    });

    /* 3. little "?" help bubbles */
    if (window.bootstrap && window.bootstrap.Tooltip) {
      document.querySelectorAll(".sz-help[title], [data-sz-tip]").forEach(function (el) {
        if (el.getAttribute("data-sz-tip")) el.setAttribute("title", el.getAttribute("data-sz-tip"));
        el.setAttribute("tabindex", el.getAttribute("tabindex") || "0");
        new window.bootstrap.Tooltip(el, { trigger: "hover focus", customClass: "sz-tooltip", placement: "top" });
      });
    }

    /* 3b. 3D tilt on product cards (mouse only, skipped for reduced motion) */
    if (!reduceMotion && window.matchMedia && window.matchMedia("(hover: hover)").matches) {
      document.addEventListener("pointermove", function (e) {
        var c = e.target.closest && e.target.closest(".product-card");
        if (!c) return;
        var r = c.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        c.style.setProperty("--ry", (x * 8).toFixed(2) + "deg");
        c.style.setProperty("--rx", (-y * 8).toFixed(2) + "deg");
      }, { passive: true });
      document.addEventListener("pointerout", function (e) {
        var c = e.target.closest && e.target.closest(".product-card");
        if (c && !c.contains(e.relatedTarget)) { c.style.setProperty("--rx", "0deg"); c.style.setProperty("--ry", "0deg"); }
      }, { passive: true });
    }

    /* 3c. stop the palette button wiggling for people who already customised */
    if (store(true, "shanzee-accent") || store(true, "shanzee-theme")) {
      document.querySelectorAll(".sz-palette-btn").forEach(function (b) { b.classList.remove("sz-attn"); });
    }

    /* 4. password / field helper: <input data-sz-count="120"> shows a live counter */
    document.querySelectorAll("[data-sz-count]").forEach(function (inp) {
      var max = parseInt(inp.getAttribute("data-sz-count"), 10) || 0;
      var c = document.createElement("div");
      c.className = "sz-count";
      inp.insertAdjacentElement("afterend", c);
      function upd() { c.textContent = inp.value.length + (max ? " / " + max : "") + " characters"; c.classList.toggle("is-over", max && inp.value.length > max); }
      inp.addEventListener("input", upd); upd();
    });
  });
})();
