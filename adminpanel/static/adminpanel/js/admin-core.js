/* =========================================================================
   Shan Zee admin core  (loaded in <head>, before page scripts)
   Admin.api()      fetch wrapper: JWT, CSRF, 401 refresh+retry, friendly errors
   Admin.toast()    toast notifications        Admin.confirm()  confirm dialog
   Admin.esc()      HTML escaping              data-confirm="..." on links/forms/buttons
   Session timer, token refresh, sidebar, active menu.
   Legacy helpers kept: showAlert, showValidationAlert, flattenErrors,
   toggleSidebar, refreshToken, authorizedApiCall, syncSessionWithToken.
   ========================================================================= */
(function (w, d) {
  "use strict";
  const cfg = w.SZ_ADMIN || {};
  const TOKEN_KEY = "access_token";
  const store = w.sessionStorage;

  // Remove long-lived tokens older versions kept in localStorage.
  try { w.localStorage.removeItem("refresh_token"); w.localStorage.removeItem("access_token"); } catch (e) {}

  /* ---------------- helpers ---------------- */
  function esc(v) {
    return String(v ?? "").replace(/[&<>"'`]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" }[c]));
  }
  function cookie(name) {
    const m = d.cookie.match(new RegExp("(?:^|; )" + name.replace(/[$()*+./?[\\\]^{|}-]/g, "\\$&") + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  }
  function csrf() { return cookie("csrftoken") || (d.querySelector("[name=csrfmiddlewaretoken]") || {}).value || ""; }
  function money(v) { return "Rs " + Number(v || 0).toLocaleString("en-PK", { maximumFractionDigits: 0 }); }
  function num(v) { return Number(v || 0).toLocaleString("en-PK"); }
  function timeAgo(iso) {
    const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (isNaN(s)) return "";
    if (s < 60) return "just now";
    const m = Math.round(s / 60); if (m < 60) return m + "m ago";
    const h = Math.round(m / 60); if (h < 24) return h + "h ago";
    const dd = Math.round(h / 24); if (dd < 30) return dd + "d ago";
    return new Date(iso).toLocaleDateString();
  }

  /* ---------------- toasts & dialogs ---------------- */
  function toast(message, type = "success", opts = {}) {
    const icon = { danger: "error", error: "error", warning: "warning", info: "info", success: "success" }[type] || "info";
    if (!w.Swal) { (w.console || {}).log(message); return; }
    w.Swal.mixin({
      toast: true, position: "top-end", showConfirmButton: false, showCloseButton: true,
      timer: opts.timer ?? (icon === "error" ? 7000 : 4000), timerProgressBar: true,
      didOpen: (t) => { t.addEventListener("mouseenter", w.Swal.stopTimer); t.addEventListener("mouseleave", w.Swal.resumeTimer); },
    }).fire({ icon, title: String(message) });
  }
  function confirmDialog(opts = {}) {
    if (typeof opts === "string") opts = { text: opts };
    if (!w.Swal) return Promise.resolve(w.confirm(opts.text || "Are you sure?"));
    return w.Swal.fire({
      icon: opts.icon || (opts.danger === false ? "question" : "warning"),
      title: opts.title || "Are you sure?",
      text: opts.text || "",
      showCancelButton: true, focusCancel: opts.danger !== false, reverseButtons: true,
      confirmButtonText: opts.confirmText || (opts.danger === false ? "Confirm" : "Yes, continue"),
      cancelButtonText: opts.cancelText || "Cancel",
      customClass: { confirmButton: opts.danger === false ? "" : "sz-danger" },
    }).then((r) => r.isConfirmed);
  }
  function flattenErrors(errors, prefix = "") {
    let out = [];
    if (!errors) return out;
    if (typeof errors === "string") return [errors];
    if (Array.isArray(errors)) return errors.flatMap((e) => flattenErrors(e, prefix));
    Object.entries(errors).forEach(([k, v]) => {
      if (["detail", "non_field_errors", "message", "error"].includes(k)) { out = out.concat(flattenErrors(v)); return; }
      const label = (prefix ? prefix + " · " : "") + k.replace(/_/g, " ");
      if (typeof v === "string") out.push(`${label}: ${v}`);
      else if (Array.isArray(v) && v.every((x) => typeof x === "string")) v.forEach((x) => out.push(`${label}: ${x}`));
      else out = out.concat(flattenErrors(v, label));
    });
    return out;
  }
  function showValidation(messages, title = "Please check the form") {
    const list = (Array.isArray(messages) ? messages : flattenErrors(messages)).slice(0, 8);
    if (!w.Swal) return toast(list.join("\n"), "warning");
    w.Swal.fire({ icon: "warning", title, html: "<ul class='text-start mb-0'>" + list.map((m) => `<li>${esc(m)}</li>`).join("") + "</ul>" });
  }

  /* ---------------- auth token ---------------- */
  let refreshing = null;
  function getToken() { return store.getItem(TOKEN_KEY) || ""; }
  function setToken(t) { if (t) store.setItem(TOKEN_KEY, t); }
  function refreshToken() {
    if (!refreshing) {
      refreshing = rawFetch(cfg.tokenUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then((r) => {
          if (r.status === 401) { sessionEnded(); return null; }
          return r.ok ? r.json() : null;
        })
        .then((data) => { if (data && data.access) { setToken(data.access); return data.access; } return null; })
        .catch(() => null)
        .finally(() => { setTimeout(() => (refreshing = null), 0); });
    }
    return refreshing;
  }
  function sessionEnded() {
    if (w.__szEnding) return;
    w.__szEnding = true;
    store.removeItem(TOKEN_KEY);
    try { bc && bc.postMessage({ type: "ended" }); } catch (e) {}
    const next = encodeURIComponent(w.location.pathname + w.location.search);
    w.location.href = (cfg.loginUrl || "/api/v1/login/") + "?expired=1&next=" + next;
  }

  /* ---------------- fetch: loader + friendly errors ---------------- */
  const rawFetch = w.fetch.bind(w);
  let active = 0;
  function loader(on) {
    const el = d.getElementById("global-loader");
    active = Math.max(0, active + (on ? 1 : -1));
    if (el) el.classList.toggle("d-none", active === 0);
  }
  w.fetch = async function (input, init) {
    loader(true);
    try {
      let res = await rawFetch(input, init);
      // Transparent token refresh for legacy page code using sessionStorage tokens.
      const hdrs = init && init.headers;
      const hasBearer = hdrs && (hdrs.Authorization || hdrs.authorization || (hdrs.get && hdrs.get("Authorization")));
      if (res.status === 401 && hasBearer && !(init && init.__retried)) {
        const t = await refreshToken();
        if (t) {
          const h = hdrs.set ? hdrs : { ...hdrs };
          if (h.set) h.set("Authorization", "Bearer " + t); else { h.Authorization = "Bearer " + t; delete h.authorization; }
          res = await rawFetch(input, { ...init, headers: h, __retried: true });
        }
      }
      return res;
    } finally { loader(false); }
  };

  async function api(url, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    const headers = { Accept: "application/json", ...(opts.headers || {}) };
    let body = opts.body;
    if (body && !(body instanceof FormData) && typeof body === "object") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    if (method !== "GET") headers["X-CSRFToken"] = csrf();
    if (opts.auth !== false) {
      const t = getToken() || (await refreshToken());
      if (t) headers.Authorization = "Bearer " + t;
    }
    let res;
    try {
      res = await w.fetch(url, { method, headers, body, credentials: "same-origin" });
    } catch (e) {
      if (!opts.silent) toast("Can't reach the server. Check your connection and try again.", "danger");
      return { ok: false, status: 0, data: null, error: "network" };
    }
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (res.status !== 204) {
      try { data = ct.includes("json") ? await res.json() : null; } catch (e) { data = null; }
    }
    const out = { ok: res.ok, status: res.status, data };
    if (res.ok) return out;
    if (res.status === 401 && data && ["session_expired", "not_authenticated"].includes(data.code)) { sessionEnded(); return out; }
    out.messages = data ? flattenErrors(data) : [];
    if (!opts.silent) {
      if (res.status === 400) showValidation(out.messages.length ? out.messages : ["Please check the values you entered."]);
      else if (res.status === 403) toast((data && data.detail) || "You don't have permission to do this.", "warning");
      else if (res.status === 404) toast("That item no longer exists. Refresh the page.", "warning");
      else if (res.status === 429) toast("Too many requests. Please wait a moment.", "warning");
      else toast(((data && data.detail) || "Something went wrong. Please try again.") +
                 (data && data.reference ? ` (ref ${data.reference})` : ""), "danger");
    }
    return out;
  }

  /* ---------------- session timer ---------------- */
  let bc = null;
  try { bc = "BroadcastChannel" in w ? new BroadcastChannel("sz-admin-session") : null; } catch (e) {}
  const S = { remaining: cfg.session ? cfg.session.remaining : 3600, warning: cfg.session ? cfg.session.warning : 120,
              syncedAt: Date.now(), lastInteraction: Date.now(), lastPing: Date.now(), modalOpen: false };

  function left() { return Math.max(0, Math.round(S.remaining - (Date.now() - S.syncedAt) / 1000)); }
  function fmt(s) {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0");
  }
  function applyState(st) {
    if (!st || typeof st.remaining !== "number") return;
    S.remaining = st.remaining; S.syncedAt = Date.now();
    if (st.warning) S.warning = st.warning;
    if (S.modalOpen && left() > S.warning) closeSessionModal();
  }
  async function extend(manual) {
    const fd = new FormData(); if (manual) fd.append("manual", "1");
    try {
      const r = await rawFetch(cfg.extendUrl, { method: "POST", body: fd, credentials: "same-origin", headers: { "X-CSRFToken": csrf(), Accept: "application/json" } });
      if (r.status === 401) return sessionEnded();
      if (r.ok) { applyState(await r.json()); S.lastPing = Date.now(); try { bc && bc.postMessage({ type: "state", state: { remaining: S.remaining, warning: S.warning } }); } catch (e) {} }
    } catch (e) {}
  }
  async function syncStatus() {
    try {
      const r = await rawFetch(cfg.statusUrl, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (r.status === 401) return sessionEnded();
      if (r.ok) applyState(await r.json());
    } catch (e) {}
  }
  function openSessionModal() {
    if (S.modalOpen || !w.Swal) return;
    S.modalOpen = true;
    w.Swal.fire({
      title: "Still there?",
      html: `<div class="sz-session-ring" id="szRing"><span id="szRingText">${fmt(left())}</span></div>
             <div>For your security you'll be signed out soon because of inactivity.</div>`,
      icon: undefined, showCancelButton: true, reverseButtons: true, allowOutsideClick: false,
      confirmButtonText: "Stay signed in", cancelButtonText: "Sign out",
    }).then((r) => {
      S.modalOpen = false;
      if (r.isConfirmed) { extend(true); toast("Session extended.", "success", { timer: 2000 }); }
      else if (r.dismiss === w.Swal.DismissReason.cancel) logoutNow();
    });
  }
  function closeSessionModal() { if (S.modalOpen && w.Swal) { w.Swal.close(); S.modalOpen = false; } }
  function logoutNow() {
    try { bc && bc.postMessage({ type: "ended" }); } catch (e) {}
    store.removeItem(TOKEN_KEY);
    const f = d.getElementById("szLogoutForm");
    if (f) f.submit(); else w.location.href = cfg.logoutUrl || "/api/v1/logout/";
  }
  function tick() {
    const s = left();
    const chip = d.getElementById("szSessionChip");
    if (chip) {
      chip.querySelector("[data-left]").textContent = fmt(s);
      chip.classList.toggle("is-warn", s <= 300 && s > S.warning);
      chip.classList.toggle("is-danger", s <= S.warning);
      chip.setAttribute("aria-label", "Session ends in " + fmt(s));
    }
    if (S.modalOpen) {
      const txt = d.getElementById("szRingText"), ring = d.getElementById("szRing");
      if (txt) txt.textContent = fmt(s);
      if (ring) ring.style.setProperty("--p", Math.round((s / S.warning) * 100) + "%");
    }
    if (s <= 0) return sessionEnded();
    if (s <= S.warning) openSessionModal();
    // Activity ping: user interacted since the last ping -> keep the session alive
    if (S.lastInteraction > S.lastPing && Date.now() - S.lastPing > 60000 && !S.modalOpen) extend(false);
  }
  function startSession() {
    if (!cfg.statusUrl) return;
    let last = 0;
    const mark = () => { const n = Date.now(); if (n - last > 2000) { last = n; S.lastInteraction = n; } };
    ["mousemove", "keydown", "click", "scroll", "touchstart", "wheel"].forEach((ev) => w.addEventListener(ev, mark, { passive: true }));
    setInterval(tick, 1000);
    setInterval(syncStatus, 5 * 60 * 1000);           // other tabs may have extended it
    d.addEventListener("visibilitychange", () => { if (!d.hidden) syncStatus(); });
    // keep the API token fresh while the session lives
    setInterval(() => { if (left() > 0) refreshToken(); }, Math.max(60, ((cfg.jwtMinutes || 15) - 2) * 60) * 1000);
    if (bc) bc.onmessage = (e) => {
      if (!e.data) return;
      if (e.data.type === "ended") sessionEnded();
      if (e.data.type === "state") applyState(e.data.state);
    };
    const chip = d.getElementById("szSessionChip");
    if (chip) chip.addEventListener("click", () => { extend(true); toast("Session extended.", "success", { timer: 2000 }); });
  }

  /* ---------------- confirmations (data-confirm + legacy inline confirm) ---------------- */
  const INLINE_CONFIRM = "[onclick^='return confirm('], [onsubmit^='return confirm(']";
  function upgradeInlineConfirms(root) {
    const found = Array.from(root.querySelectorAll ? root.querySelectorAll(INLINE_CONFIRM) : []);
    if (root.matches && root.matches(INLINE_CONFIRM)) found.push(root);
    found.forEach((el) => {
      const attr = el.hasAttribute("onsubmit") ? "onsubmit" : "onclick";
      const m = el.getAttribute(attr).match(/^return confirm\((['"])(.*)\1\)\s*;?$/);
      if (!m) return;
      el.removeAttribute(attr);
      el.setAttribute("data-confirm", m[2]);
    });
  }
  d.addEventListener("click", (e) => {
    const el = e.target.closest("[data-confirm]:not(form)");
    if (!el || el.dataset.confirmed === "1") return;
    e.preventDefault(); e.stopImmediatePropagation();
    confirmDialog({ text: el.dataset.confirm, title: el.dataset.confirmTitle, confirmText: el.dataset.confirmButton,
                    danger: el.dataset.confirmDanger !== "false" }).then((ok) => {
      if (!ok) return;
      el.dataset.confirmed = "1";
      if (el.tagName === "A" && el.dataset.method === "post") return postTo(el.href);
      el.click();
      setTimeout(() => delete el.dataset.confirmed, 0);
    });
  }, true);
  d.addEventListener("submit", (e) => {
    const f = e.target;
    if (!f.matches("form[data-confirm]") || f.dataset.confirmed === "1") return;
    e.preventDefault();
    confirmDialog({ text: f.dataset.confirm, title: f.dataset.confirmTitle, confirmText: f.dataset.confirmButton,
                    danger: f.dataset.confirmDanger !== "false" }).then((ok) => {
      if (ok) { f.dataset.confirmed = "1"; (e.submitter && f.requestSubmit) ? f.requestSubmit(e.submitter) : f.submit(); }
    });
  }, true);
  function postTo(url) {
    const f = d.createElement("form");
    f.method = "post"; f.action = url; f.style.display = "none";
    f.innerHTML = `<input type="hidden" name="csrfmiddlewaretoken" value="${esc(csrf())}">`;
    d.body.appendChild(f); f.submit();
  }

  /* ---------------- navigation ---------------- */
  function toggleSidebar() {
    if (w.matchMedia("(max-width: 991.98px)").matches) d.body.classList.toggle("sz-nav-open");
    else {
      d.body.classList.toggle("sz-mini");
      try { w.localStorage.setItem("sz-mini", d.body.classList.contains("sz-mini") ? "1" : "0"); } catch (e) {}
    }
  }
  function markActive() {
    const here = w.location.pathname + w.location.search;
    let best = null, bestLen = 0;
    d.querySelectorAll(".sz-nav a[href]").forEach((a) => {
      const href = a.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      const u = new URL(href, w.location.origin);
      const p = u.pathname + u.search;
      if ((here === p || (u.search === "" && here.startsWith(u.pathname))) && p.length > bestLen) { best = a; bestLen = p.length; }
    });
    if (!best) return;
    best.classList.add("active");
    const group = best.closest(".collapse");
    if (group) {
      group.classList.add("show");
      const toggler = d.querySelector(`[href="#${group.id}"]`);
      if (toggler) { toggler.setAttribute("aria-expanded", "true"); toggler.classList.remove("collapsed"); }
    }
  }

  /* ---------------- unseen badges ---------------- */
  async function refreshUnseen() {
    if (!cfg.unseenUrl || d.hidden) return;
    try {
      const r = await rawFetch(cfg.unseenUrl, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!r.ok) return;
      const counts = await r.json();
      d.querySelectorAll("[data-unseen]").forEach((el) => {
        const n = counts[el.dataset.unseen] || 0;
        el.hidden = !n;
        el.textContent = el.textContent.replace(/^\d+/, n);
      });
    } catch (e) {}
  }

  /* ---------------- boot ---------------- */
  d.addEventListener("DOMContentLoaded", () => {
    upgradeInlineConfirms(d);
    markActive();
    startSession();
    setInterval(refreshUnseen, 60000);
    (cfg.messages || []).forEach((m) => toast(m.text, m.level));
    const bd = d.querySelector(".sz-backdrop");
    if (bd) bd.addEventListener("click", () => d.body.classList.remove("sz-nav-open"));
    // Rows rendered later by page scripts (tables, modals) get the same treatment.
    new MutationObserver((muts) => muts.forEach((m) => m.addedNodes.forEach((n) => {
      if (n.nodeType === 1) upgradeInlineConfirms(n);
    }))).observe(d.body, { childList: true, subtree: true });
  });

  /* ---------------- exports ---------------- */
  w.Admin = { api, toast, confirm: confirmDialog, esc, csrf, money, num, timeAgo, getToken, refreshToken,
              flattenErrors, showValidation, postTo, sessionExtend: () => extend(true), logout: logoutNow };
  // legacy globals used by existing pages
  w.showAlert = (message, type = "info") => toast(message, type);
  w.showValidationAlert = (messages, title) => showValidation(messages, title);
  w.flattenErrors = flattenErrors;
  w.toggleSidebar = toggleSidebar;
  w.refreshToken = refreshToken;
  w.syncSessionWithToken = () => refreshToken();
  w.authorizedApiCall = (url, options = {}) => {
    options.headers = { ...(options.headers || {}), Authorization: "Bearer " + getToken() };
    if (options.body && typeof options.body === "string") options.headers["Content-Type"] = options.headers["Content-Type"] || "application/json";
    return w.fetch(url, options);
  };
  if (!w.getCookie) w.getCookie = cookie;
})(window, document);
