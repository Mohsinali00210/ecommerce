/* =====================================================================
   SHAN ZEE — THEME ENGINE  (theme.js)   — load in <head>, before first paint
   • Light / Dark / Auto mode
   • Any brand colour: presets + free colour picker (+ optional highlight colour)
   • Every derived colour (soft tint, gradient, glow, readable text colour,
     button text colour…) is computed from the chosen colour, so buttons and
     text always stay readable — on light colours too (yellow gets dark text).
   Saved per visitor in localStorage:  shanzee-theme (mode)  shanzee-accent (colours)
   Public API:  SZTheme.setMode('light'|'dark'|'auto')  SZTheme.setColors(main, highlight?)
                SZTheme.reset()   SZTheme.state()   SZTheme.presets
   ===================================================================== */
(function () {
  "use strict";
  var root = document.documentElement;
  var MODE_KEY = "shanzee-theme", COLOR_KEY = "shanzee-accent";
  var DEFAULT = { a: "#198754", b: "#f59e0b" };

  var PRESETS = [
    { n: "Emerald",  a: "#198754", b: "#f59e0b" },
    { n: "Ocean",    a: "#0b72d9", b: "#14b8a6" },
    { n: "Indigo",   a: "#4f46e5", b: "#ec4899" },
    { n: "Violet",   a: "#7c3aed", b: "#f97316" },
    { n: "Rose",     a: "#e11d48", b: "#f59e0b" },
    { n: "Pink",     a: "#db2777", b: "#06b6d4" },
    { n: "Sunset",   a: "#ea580c", b: "#7c3aed" },
    { n: "Sunshine", a: "#f5b800", b: "#0f766e" },
    { n: "Lime",     a: "#65a30d", b: "#0ea5e9" },
    { n: "Teal",     a: "#0d9488", b: "#6366f1" },
    { n: "Sky",      a: "#0ea5e9", b: "#f43f5e" },
    { n: "Slate",    a: "#334155", b: "#22c55e" }
  ];

  /* ------------------------------ colour maths ------------------------------ */
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function hexOk(h) { return /^#[0-9a-f]{6}$/i.test(h || ""); }
  function hex2rgb(h) { return [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
  function rgb2hex(r, g, b) { return "#" + [r, g, b].map(function (v) { return ("0" + Math.round(clamp(v, 0, 255)).toString(16)).slice(-2); }).join(""); }
  function rgb2hsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), h = 0, s = 0, l = (mx + mn) / 2, d = mx - mn;
    if (d) {
      s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return [h, s * 100, l * 100];
  }
  function hsl2hex(h, s, l) {
    h = ((h % 360) + 360) % 360; s = clamp(s, 0, 100) / 100; l = clamp(l, 0, 100) / 100;
    var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2, r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
    else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
    return rgb2hex((r + m) * 255, (g + m) * 255, (b + m) * 255);
  }
  function lum(hex) {
    var c = hex2rgb(hex).map(function (v) { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); });
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2];
  }
  function contrast(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); }
  function readableOn(bg) { return contrast(bg, "#ffffff") >= contrast(bg, "#111827") ? "#ffffff" : "#111827"; }
  /* nudge lightness until `hex` reads at >= ratio on `bg` */
  function ensure(hex, bg, ratio) {
    var hsl = rgb2hsl.apply(null, hex2rgb(hex)), l = hsl[2], dir = lum(bg) > .4 ? -1 : 1, n = 0;
    var out = hex;
    while (contrast(out, bg) < ratio && n++ < 60) { l = clamp(l + dir * 2, 2, 98); out = hsl2hex(hsl[0], hsl[1], l); }
    return out;
  }
  function rgba(hex, a) { var c = hex2rgb(hex); return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")"; }

  /* --------------------------- derive every token --------------------------- */
  function derive(a, b, mode) {
    var dark = mode === "dark";
    var hsl = rgb2hsl.apply(null, hex2rgb(a)), h = hsl[0], s = hsl[1], l = hsl[2];
    var light = hsl2hex(h, s, clamp(l + 11, 0, 88));
    var deepG = hsl2hex(h, s, clamp(l - 13, 6, 60));
    var surface = dark ? "#121a16" : "#ffffff";
    var text = ensure(a, surface, 4.5);                      // accent used AS TEXT must stay readable
    var hb = rgb2hsl.apply(null, hex2rgb(b));
    var v = {
      "--accent": a,
      "--accent-light": light,
      "--accent-dark": hsl2hex(h, clamp(s, 20, 80), dark ? 14 : 17),
      "--accent-deep": text,
      "--accent-ink": dark ? hsl2hex(h, clamp(s, 20, 70), 86) : hsl2hex(h, clamp(s, 20, 80), 17),
      "--accent-soft": dark ? rgba(a, .18) : hsl2hex(h, clamp(s, 25, 75), 95),
      "--accent-line": dark ? hsl2hex(h, clamp(s * .6, 10, 50), 25) : hsl2hex(h, clamp(s, 20, 70), 86),
      "--accent-rgb": hex2rgb(a).join(", "),
      "--accent-grad": "linear-gradient(135deg," + light + " 0%," + a + " 50%," + deepG + " 100%)",
      "--accent-glow": "0 10px 30px -8px " + rgba(a, .45),
      "--on-accent": readableOn(a),
      "--accent-2": b,
      "--accent-2-deep": hsl2hex(hb[0], hb[1], clamp(hb[2] - 14, 6, 60)),
      "--accent-2-rgb": hex2rgb(b).join(", "),
      "--accent-2-grad": "linear-gradient(135deg," + hsl2hex(hb[0], hb[1], clamp(hb[2] + 8, 0, 88)) + "," + b + " 55%," + hsl2hex(hb[0], hb[1], clamp(hb[2] - 14, 6, 60)) + ")",
      "--on-accent-2": readableOn(b)
    };
    // legacy / alias names used around the stylesheet and old templates
    v["--sz-brand"] = a; v["--sz-brand-deep"] = v["--accent-deep"]; v["--sz-brand-dark"] = v["--accent-ink"];
    v["--sz-brand-soft"] = v["--accent-soft"]; v["--sz-brand-line"] = v["--accent-line"];
    v["--sz-green-deep"] = v["--accent-dark"]; v["--sz-green-light"] = a; v["--sz-gold"] = b; v["--sz-gold-light"] = light;
    v["--brass"] = a; v["--brass-deep"] = v["--accent-deep"]; v["--pine"] = v["--accent-dark"]; v["--pine-soft"] = v["--accent-soft"];
    return v;
  }

  /* --------------------------------- state --------------------------------- */
  function read(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function write(k, v) { try { v == null ? window.localStorage.removeItem(k) : window.localStorage.setItem(k, v); } catch (e) {} }
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var st = { mode: read(MODE_KEY), a: DEFAULT.a, b: DEFAULT.b, bAuto: true };
  try {
    var saved = JSON.parse(read(COLOR_KEY) || "null");
    if (saved && hexOk(saved.a)) { st.a = saved.a; if (hexOk(saved.b)) { st.b = saved.b; st.bAuto = !!saved.auto; } else st.b = autoB(saved.a); }
  } catch (e) {}
  if (st.mode !== "light" && st.mode !== "dark") st.mode = null;      // null = follow the system

  function effective() { return st.mode || (mq && mq.matches ? "dark" : "light"); }
  function autoB(a) { var h = rgb2hsl.apply(null, hex2rgb(a)); return hsl2hex(h[0] + 150, clamp(h[1], 55, 90), 52); }

  var KEYS = [];
  function apply(animate) {
    var mode = effective();
    if (animate) { root.classList.add("sz-theme-anim"); clearTimeout(apply._t); apply._t = setTimeout(function () { root.classList.remove("sz-theme-anim"); }, 650); }
    root.setAttribute("data-theme", mode);
    root.setAttribute("data-bs-theme", mode);
    var vars = derive(st.a, st.b, mode);
    for (var k in vars) { root.style.setProperty(k, vars[k]); if (KEYS.indexOf(k) < 0) KEYS.push(k); }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", mode === "dark" ? "#0b110e" : st.a);
    syncUI();
  }
  function save() {
    write(MODE_KEY, st.mode);
    write(COLOR_KEY, (st.a === DEFAULT.a && st.b === DEFAULT.b) ? null : JSON.stringify({ a: st.a, b: st.b, auto: st.bAuto }));
  }

  var API = (window.SZTheme = {
    presets: PRESETS, defaults: DEFAULT,
    state: function () { return { mode: st.mode || "auto", effective: effective(), main: st.a, highlight: st.b }; },
    setMode: function (m) { st.mode = (m === "light" || m === "dark") ? m : null; save(); apply(true); },
    toggle: function () { API.setMode(effective() === "dark" ? "light" : "dark"); },
    setColors: function (a, b) {
      if (!hexOk(a)) return;
      st.a = a.toLowerCase();
      if (b && hexOk(b)) { st.b = b.toLowerCase(); st.bAuto = false; } else { st.b = autoB(st.a); st.bAuto = true; }
      save(); apply(true);
    },
    reset: function () { st.a = DEFAULT.a; st.b = DEFAULT.b; st.bAuto = false; st.mode = null; save(); apply(true); }
  });
  apply(false);                                   // before first paint
  if (mq) {
    var onSys = function () { if (!st.mode) apply(true); };
    mq.addEventListener ? mq.addEventListener("change", onSys) : mq.addListener && mq.addListener(onSys);
  }

  /* ----------------------------------- UI ----------------------------------- */
  var panel, built = false;
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }

  function build() {
    if (built) return; built = true;
    panel = el("div", "sz-picker");
    panel.id = "szPicker";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Customize theme colours");
    panel.hidden = true;
    var sw = PRESETS.map(function (p) {
      return '<button type="button" class="sz-swatch" data-a="' + p.a + '" data-b="' + p.b + '" title="' + p.n + '" aria-label="' + p.n + ' theme">' +
        '<span class="sz-swatch-dot" style="background:linear-gradient(135deg,' + p.a + ' 0 58%,' + p.b + ' 58% 100%)"></span>' +
        '<i class="bi bi-check-lg"></i><em>' + p.n + "</em></button>";
    }).join("");
    panel.innerHTML =
      '<div class="sz-picker-head"><span class="sz-picker-ico"><i class="bi bi-palette2"></i></span>' +
      '<div><strong>Make it yours</strong><small>Pick a colour — the whole site follows</small></div>' +
      '<button type="button" class="sz-picker-x" aria-label="Close"><i class="bi bi-x-lg"></i></button></div>' +
      '<div class="sz-picker-sec"><span class="sz-picker-lbl"><i class="bi bi-circle-half"></i> Mode</span>' +
      '<div class="sz-seg" role="group" aria-label="Mode">' +
      '<button type="button" data-mode="light"><i class="bi bi-sun-fill"></i> Light</button>' +
      '<button type="button" data-mode="dark"><i class="bi bi-moon-stars-fill"></i> Dark</button>' +
      '<button type="button" data-mode="auto"><i class="bi bi-magic"></i> Auto</button></div></div>' +
      '<div class="sz-picker-sec"><span class="sz-picker-lbl"><i class="bi bi-droplet-half"></i> Colour themes</span>' +
      '<div class="sz-swatches">' + sw + "</div></div>" +
      '<div class="sz-picker-sec"><span class="sz-picker-lbl"><i class="bi bi-eyedropper"></i> Your own colours</span>' +
      '<div class="sz-custom">' +
      '<label class="sz-colorfield"><input type="color" id="szMain" aria-label="Main colour"><span class="sz-cf-chip"></span><span><b>Main</b><small id="szMainHex"></small></span></label>' +
      '<label class="sz-colorfield"><input type="color" id="szHi" aria-label="Highlight colour"><span class="sz-cf-chip"></span><span><b>Highlight</b><small id="szHiHex"></small></span></label>' +
      "</div></div>" +
      '<div class="sz-picker-sec sz-preview" aria-hidden="true"><span class="sz-picker-lbl"><i class="bi bi-eye"></i> Preview</span>' +
      '<div class="sz-prev-row"><span class="sz-prev-btn"><i class="bi bi-bag-check"></i> Buy now</span><span class="sz-prev-btn alt">Highlight</span>' +
      '<span class="sz-prev-link">Text link</span><span class="sz-prev-badge">New</span></div></div>' +
      '<div class="sz-picker-foot"><button type="button" class="sz-reset"><i class="bi bi-arrow-counterclockwise"></i> Reset</button>' +
      '<small>Saved on this device.</small></div>';
    document.body.appendChild(panel);

    panel.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest(".sz-picker-x")) return close();
      var m = t.closest("[data-mode]"); if (m) return API.setMode(m.getAttribute("data-mode"));
      var s = t.closest(".sz-swatch"); if (s) { API.setColors(s.getAttribute("data-a"), s.getAttribute("data-b")); st.bAuto = false; save(); return; }
      if (t.closest(".sz-reset")) API.reset();
    });
    var main = panel.querySelector("#szMain"), hi = panel.querySelector("#szHi"), raf = 0;
    main.addEventListener("input", function () { cancelAnimationFrame(raf); raf = requestAnimationFrame(function () { API.setColors(main.value); }); });
    hi.addEventListener("input", function () { cancelAnimationFrame(raf); raf = requestAnimationFrame(function () { API.setColors(st.a, hi.value); }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });
    document.addEventListener("click", function (e) {
      if (!panel.hidden && !e.target.closest("#szPicker, .sz-palette-btn")) close();
    });
    syncUI();
  }
  function open(btn) {
    build(); panel.hidden = false; requestAnimationFrame(function () { panel.classList.add("open"); });
    document.querySelectorAll(".sz-palette-btn").forEach(function (b) { b.setAttribute("aria-expanded", "true"); });
    var f = panel.querySelector(".sz-swatch.active") || panel.querySelector(".sz-swatch"); f && f.focus({ preventScroll: true });
  }
  function close() {
    if (!panel) return; panel.classList.remove("open");
    document.querySelectorAll(".sz-palette-btn").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    setTimeout(function () { if (!panel.classList.contains("open")) panel.hidden = true; }, 260);
  }
  function syncUI() {
    document.querySelectorAll(".theme-toggle").forEach(function (b) {
      var d = effective() === "dark";
      b.setAttribute("aria-checked", String(d)); b.setAttribute("title", d ? "Switch to light mode" : "Switch to dark mode");
    });
    if (!panel) return;
    var cur = st.mode || "auto";
    panel.querySelectorAll("[data-mode]").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-mode") === cur); });
    panel.querySelectorAll(".sz-swatch").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-a") === st.a && (b.getAttribute("data-b") === st.b || st.bAuto)); });
    var main = panel.querySelector("#szMain"), hi = panel.querySelector("#szHi");
    if (main && document.activeElement !== main) main.value = st.a;
    if (hi && document.activeElement !== hi) hi.value = st.b;
    panel.querySelector("#szMainHex").textContent = st.a.toUpperCase();
    panel.querySelector("#szHiHex").textContent = st.b.toUpperCase() + (st.bAuto ? " · auto" : "");
    panel.querySelectorAll(".sz-cf-chip")[0].style.background = st.a;
    panel.querySelectorAll(".sz-cf-chip")[1].style.background = st.b;
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".theme-toggle");
    if (t) { API.toggle(); if (window.SZ) SZ.toast(effective() === "dark" ? "Dark mode is on." : "Light mode is on.", "info", { title: effective() === "dark" ? "Dark mode" : "Light mode", icon: effective() === "dark" ? "bi-moon-stars-fill" : "bi-sun-fill", duration: 1800 }); return; }
    var p = e.target.closest && e.target.closest(".sz-palette-btn");
    if (p) { build(); if (!panel.hidden && panel.classList.contains("open")) close(); else open(p); }
  });
})();
