/* =====================================================================
   Shan Zee — modern.js
   Motion + UX layer. Safe to load on every page (after cart.js / app.js).
   Every feature feature-detects its markup, so pages that lack a piece of
   markup simply skip it.
   Public API:  window.Toast.show(msg, type?, ms?)   window.MiniCart.open(item?)
   ===================================================================== */
(function () {
  "use strict";

  var doc = document, root = doc.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var FREE_SHIP = 3500; // PKR — matches the "Free Shipping on orders over PKR 3,500" promise
  function $(s, c) { return (c || doc).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || doc).querySelectorAll(s)); }
  function money(n) { return "RS " + Number(n || 0).toLocaleString("en-PK", { minimumFractionDigits: 0, maximumFractionDigits: 2 }); }
  function num(txt) { var m = String(txt || "").replace(/,/g, "").match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : 0; }
  function raf(fn) { return window.requestAnimationFrame(fn); }

  doc.body.classList.add("sz-modern");

  /* ------------------------------------------------------------------ *
   * 1. Scroll progress, sticky header state, back-to-top
   * ------------------------------------------------------------------ */
  var bar = doc.createElement("div");
  bar.className = "m-progress";
  bar.innerHTML = "<i></i>";
  doc.body.appendChild(bar);
  var barFill = bar.firstChild;

  var top = doc.createElement("button");
  top.className = "m-top";
  top.type = "button";
  top.setAttribute("aria-label", "Back to top");
  top.innerHTML =
    '<svg viewBox="0 0 46 46"><circle class="bg" cx="23" cy="23" r="21"/><circle class="fg" cx="23" cy="23" r="21" stroke-dasharray="131.9" stroke-dashoffset="131.9"/></svg><i class="bi bi-arrow-up"></i>';
  doc.body.appendChild(top);
  var topFg = $(".fg", top);
  top.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); });

  var header = $("body > .site-header");
  var lastY = window.scrollY, ticking = false;

  function onScroll() {
    var y = window.scrollY;
    var h = root.scrollHeight - window.innerHeight;
    var p = h > 0 ? Math.min(1, y / h) : 0;
    barFill.style.transform = "scaleX(" + p + ")";
    topFg.style.strokeDashoffset = String(131.9 * (1 - p));
    top.classList.toggle("show", y > 600);
    if (header) {
      header.classList.toggle("is-scrolled", y > 24);
      // hide the secondary nav strip when scrolling down, restore on scroll up
      header.classList.toggle("is-hidden-nav", y > 160 && y > lastY + 2);
      if (y < lastY - 2) header.classList.remove("is-hidden-nav");
    }
    lastY = y;
    ticking = false;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; raf(onScroll); } }, { passive: true });
  onScroll();

  /* ------------------------------------------------------------------ *
   * 2. Reveal on scroll (IntersectionObserver) with automatic staggering
   * ------------------------------------------------------------------ */
  function autoTag() {
    $$(".section-head, .trust-row, .newsletter-band, .promo-card, .blog-card, .cat-card, .order-card, .address-card, .checkout-panel, .perk-card")
      .forEach(function (el) { if (!el.classList.contains("reveal") && !el.hasAttribute("data-reveal")) el.setAttribute("data-reveal", ""); });
    $$(".trust-item, .perk-card, .category-item").forEach(function (el, i) {
      if (!el.hasAttribute("data-reveal")) el.setAttribute("data-reveal", "");
      el.style.setProperty("--d", (i % 8) * 70 + "ms");
    });
    // product cards stagger within each grid row
    $$(".row").forEach(function (row) {
      $$(":scope > [class*='col-'] > .product-card", row).forEach(function (card, i) {
        card.classList.remove("in");              // template ships them pre-"in"; let the observer run
        card.classList.add("reveal");
        card.style.setProperty("--d", (i % 6) * 60 + "ms");
      });
    });
  }
  autoTag();

  var io = null;
  if ("IntersectionObserver" in window && !reduce) {
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
  }
  function observeReveals(scope) {
    $$(".reveal:not(.in), [data-reveal]:not(.in)", scope).forEach(function (el) {
      if (io) io.observe(el); else el.classList.add("in");
    });
  }
  observeReveals();
  // hidden tab panes / lazily injected content (quick view, filters, infinite scroll)
  if ("MutationObserver" in window) {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) observeReveals(n.parentNode || doc); }); });
    }).observe(doc.body, { childList: true, subtree: true });
  }
  // safety net: never leave content invisible if something goes wrong
  setTimeout(function () { $$(".reveal:not(.in), [data-reveal]:not(.in)").forEach(function (el) {
    var r = el.getBoundingClientRect(); if (r.top < window.innerHeight) el.classList.add("in");
  }); }, 1800);

  /* ------------------------------------------------------------------ *
   * 3. Button ripple + magnetic hover on primary CTAs
   * ------------------------------------------------------------------ */
  doc.addEventListener("pointerdown", function (e) {
    var b = e.target.closest && e.target.closest(".btn");
    if (!b || reduce || b.disabled) return;
    var r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2;
    var s = doc.createElement("span");
    s.className = "m-ripple";
    s.style.cssText = "width:" + d + "px;height:" + d + "px;left:" + (e.clientX - r.left - d / 2) + "px;top:" + (e.clientY - r.top - d / 2) + "px";
    b.appendChild(s);
    setTimeout(function () { s.remove(); }, 700);
  }, { passive: true });

  /* ------------------------------------------------------------------ *
   * 4. Count-up numbers  (<b data-count="1200">0</b>)
   * ------------------------------------------------------------------ */
  var counters = $$("[data-count]");
  if (counters.length && "IntersectionObserver" in window) {
    var co = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        co.unobserve(e.target);
        var el = e.target, to = parseFloat(el.dataset.count), t0 = performance.now(), dur = 1400;
        (function step(t) {
          var k = Math.min(1, (t - t0) / dur), v = to * (1 - Math.pow(1 - k, 3));
          el.textContent = Math.round(v).toLocaleString();
          if (k < 1) raf(step);
        })(t0);
      });
    }, { threshold: 0.5 });
    counters.forEach(function (c) { co.observe(c); });
  }

  /* ------------------------------------------------------------------ *
   * 5. Soft page transitions between same-site pages
   * ------------------------------------------------------------------ */
  doc.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || reduce || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    if (a.target === "_blank" || a.hasAttribute("download") || a.hasAttribute("data-bs-toggle")) return;
    var href = a.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#" || /^(mailto:|tel:|javascript:)/i.test(href)) return;
    var u; try { u = new URL(a.href, location.href); } catch (_) { return; }
    if (u.origin !== location.origin || (u.pathname === location.pathname && u.search === location.search)) return;
    doc.body.classList.add("m-leaving");
    setTimeout(function () { doc.body.classList.remove("m-leaving"); }, 2500); // never get stuck (e.g. on download responses)
  });
  window.addEventListener("pageshow", function () { doc.body.classList.remove("m-leaving"); });

  /* ------------------------------------------------------------------ *
   * 6. Toasts  (also replaces the older showToast / showAlert helpers)
   * ------------------------------------------------------------------ */
  var stack = doc.createElement("div");
  stack.className = "m-toasts";
  stack.setAttribute("aria-live", "polite");
  doc.body.appendChild(stack);
  var ICONS = { success: "bi-check-circle-fill", error: "bi-x-octagon-fill", info: "bi-info-circle-fill", warning: "bi-exclamation-triangle-fill" };

  function normType(t) {
    t = String(t || "info").toLowerCase();
    if (t === "danger" || t === "error") return "error";
    if (t === "warning" || t === "warn") return "warning";
    if (t === "success" || t === "ok") return "success";
    return "info";
  }
  var Toast = {
    show: function (msg, type, ms) {
      type = normType(type); ms = ms || 3600;
      var t = doc.createElement("div");
      t.className = "m-toast " + type;
      t.style.setProperty("--life", ms + "ms");
      t.innerHTML = '<i class="t-ic bi ' + ICONS[type] + '"></i><div class="t-body"></div><button class="t-x" aria-label="Dismiss"><i class="bi bi-x"></i></button>';
      $(".t-body", t).textContent = msg == null ? "" : String(msg);
      stack.appendChild(t);
      while (stack.children.length > 4) stack.firstChild.remove();
      function close() { t.classList.add("out"); setTimeout(function () { t.remove(); }, 350); }
      $(".t-x", t).addEventListener("click", close);
      setTimeout(close, ms);
      return t;
    }
  };
  window.Toast = Toast;
  window.showToast = function (m, t) { return Toast.show(m, t); };
  window.showAlert = function (m, t) { return Toast.show(m, t); };

  /* ------------------------------------------------------------------ *
   * 7. Mini-cart drawer ("Added to cart" confirmation)  +  fly-to-cart
   * ------------------------------------------------------------------ */
  var drawer = $("#miniCart"), backdrop = $("#miniCartBackdrop");
  var MiniCart = {
    open: function (item) {
      if (!drawer) return;
      if (item) {
        $("#mcImg", drawer).src = item.image || "";
        $("#mcImg", drawer).style.display = item.image ? "" : "none";
        $("#mcName", drawer).textContent = item.name || "Item added to your cart";
        $("#mcPrice", drawer).textContent = item.price ? money(item.price) : "";
        $("#mcQty", drawer).textContent = "Qty: " + (item.qty || 1);
      }
      // free-shipping meter: uses the cart total if the header-counts API supplies one, otherwise this item's value
      var total = (window.HeaderCounts && window.HeaderCounts.total) || (item && item.price ? item.price * (item.qty || 1) : 0);
      var box = $("#mcShip", drawer), fill = $(".bar > i", box), msg = $("#mcShipMsg", drawer);
      var pct = Math.min(100, Math.round((total / FREE_SHIP) * 100));
      box.classList.toggle("done", total >= FREE_SHIP);
      msg.innerHTML = total >= FREE_SHIP
        ? '<i class="bi bi-gift-fill"></i> You\'ve unlocked <b>free shipping</b>!'
        : (total > 0 ? 'Add <b>' + money(FREE_SHIP - total) + '</b> more for <b>free shipping</b>' : 'Free shipping on orders over <b>' + money(FREE_SHIP) + '</b>');
      fill.style.width = "0";
      drawer.classList.add("show"); backdrop.classList.add("show");
      drawer.setAttribute("aria-hidden", "false");
      doc.body.style.overflow = "hidden"; doc.body.classList.add("m-drawer-open");
      setTimeout(function () { fill.style.width = pct + "%"; }, 80);
      var focusBtn = $(".btn-brass", drawer); if (focusBtn) focusBtn.focus({ preventScroll: true });
    },
    close: function () {
      if (!drawer) return;
      drawer.classList.remove("show"); backdrop.classList.remove("show");
      drawer.setAttribute("aria-hidden", "true");
      doc.body.style.overflow = ""; doc.body.classList.remove("m-drawer-open");
    }
  };
  window.MiniCart = MiniCart;
  if (drawer) {
    backdrop.addEventListener("click", MiniCart.close);
    $$("[data-minicart-close]", drawer).forEach(function (b) { b.addEventListener("click", MiniCart.close); });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape") MiniCart.close(); });
  }

  function cartIcon() { return $('[data-cart-count]') ? $('[data-cart-count]').closest("a,button") : null; }

  function flyToCart(srcImg) {
    var target = cartIcon();
    if (reduce || !srcImg || !target) return;
    var a = srcImg.getBoundingClientRect(), b = target.getBoundingClientRect();
    if (!a.width || b.width === 0) return;
    var g = doc.createElement("img");
    g.src = srcImg.currentSrc || srcImg.src; g.className = "m-fly";
    var size = Math.min(150, a.width);
    g.style.cssText = "width:" + size + "px;height:" + size + "px;left:" + (a.left + a.width / 2 - size / 2) + "px;top:" + (a.top + a.height / 2 - size / 2) + "px";
    doc.body.appendChild(g);
    var dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
    var anim = g.animate([
      { transform: "translate(0,0) scale(1) rotate(0)", opacity: 1, offset: 0 },
      { transform: "translate(" + dx * 0.45 + "px," + (dy * 0.45 - 90) + "px) scale(.7) rotate(8deg)", opacity: 1, offset: 0.55 },
      { transform: "translate(" + dx + "px," + dy + "px) scale(.08) rotate(24deg)", opacity: .2, offset: 1 }
    ], { duration: 850, easing: "cubic-bezier(.5,0,.2,1)" });
    anim.onfinish = function () { g.remove(); bumpCart(); };
  }

  function bumpCart() {
    $$("[data-cart-count]").forEach(function (el) { el.classList.remove("m-bump"); void el.offsetWidth; el.classList.add("m-bump"); });
  }

  // Describe what was added, from whichever markup is on the page (card, quick-view, product page)
  function describe(pid, qty) {
    var card = pid != null ? $('.product-card[data-id="' + pid + '"]') : null;
    var out = { qty: qty || 1, el: null };
    if (card) {
      out.name = card.dataset.name; out.price = parseFloat(card.dataset.price) || 0; out.image = card.dataset.image;
      out.el = $(".img-primary", card);
      return out;
    }
    var scope = $("#quickViewModal.show") || doc;
    var h = $("h1, h2.product-title, .product-title", scope);
    out.name = h ? h.textContent.trim() : "";
    var p = $("[data-final-price], #productPrice, .price-now", scope);
    out.price = p ? num(p.textContent) : 0;
    var im = $("#mainImage, #mainProductImage, .gallery-main img, .product-gallery img, img", scope);
    if (im) { out.image = im.currentSrc || im.src; out.el = im; }
    return out;
  }

  function wrapCart() {
    if (!window.Cart || typeof window.Cart.add !== "function" || window.Cart.__wrapped) return;
    var orig = window.Cart.add;
    window.Cart.add = function (pid, vid, qty) {
      var ctx = this, args = arguments;
      if (window.IS_AUTHENTICATED === false && typeof window.requireLogin === "function") { /* original handles the login prompt */ }
      var info = describe(pid, qty);
      var res = orig.apply(ctx, args);
      var btn = doc.activeElement && doc.activeElement.closest ? doc.activeElement.closest(".btn,button") : null;
      if (btn) btn.classList.add("is-loading");
      function ok(r) {
        if (btn) btn.classList.remove("is-loading");
        if (r && (r.success === false || r.ok === false || r.error)) return;   // server said no — keep the original error UI only
        if (window.IS_AUTHENTICATED === false) return;
        flyToCart(info.el);
        setTimeout(function () { MiniCart.open(info); if (window.refreshHeaderCounts) window.refreshHeaderCounts().then(bumpCart); }, reduce ? 0 : 650);
      }
      function bad() { if (btn) btn.classList.remove("is-loading"); }
      if (res && typeof res.then === "function") res.then(ok, bad); else setTimeout(ok, 350);
      return res;
    };
    window.Cart.__wrapped = true;
  }
  wrapCart();
  doc.addEventListener("DOMContentLoaded", wrapCart);
  window.addEventListener("load", wrapCart);

  // product-card quick-add bar
  doc.addEventListener("click", function (e) {
    var q = e.target.closest && e.target.closest(".m-quick-add");
    if (!q) return;
    e.preventDefault();
    if (typeof window.requireLogin === "function" && !window.requireLogin()) return;
    if (q.dataset.hasVariants === "true") { if (window.openQuickView) window.openQuickView(q.dataset.pid); return; } // needs a choice first
    if (window.Cart) window.Cart.add(q.dataset.pid, q.dataset.vid ? Number(q.dataset.vid) : null, 1);
    q.classList.add("is-added");
    q.innerHTML = '<i class="bi bi-check2"></i> Added';
    setTimeout(function () { q.classList.remove("is-added"); q.innerHTML = '<i class="bi bi-bag-plus"></i> Add to cart'; }, 2200);
  });

  // wishlist heart pop
  doc.addEventListener("click", function (e) {
    var w = e.target.closest && e.target.closest("[data-wishlist-btn]");
    if (!w) return;
    w.classList.remove("m-pop"); void w.offsetWidth; w.classList.add("m-pop");
    setTimeout(function () { w.classList.remove("m-pop"); bumpWishlist(); }, 700);
  });
  function bumpWishlist() { $$("[data-wishlist-count]").forEach(function (el) { el.classList.remove("m-bump"); void el.offsetWidth; el.classList.add("m-bump"); }); }

  /* keep header badges animating whenever their number changes */
  $$("[data-cart-count], [data-wishlist-count], #notificationCount").forEach(function (el) {
    var last = el.textContent;
    new MutationObserver(function () { if (el.textContent !== last) { last = el.textContent; el.classList.remove("m-bump"); void el.offsetWidth; el.classList.add("m-bump"); syncBottomNav(); } })
      .observe(el, { childList: true, characterData: true, subtree: true });
  });

  /* ------------------------------------------------------------------ *
   * 8. Mobile bottom navigation: active state + live counts + search
   * ------------------------------------------------------------------ */
  function syncBottomNav() {
    var c = $("[data-cart-count]"), n = $("#mbCart .nb");
    if (n && c) { var v = parseInt(c.textContent, 10) || 0; n.textContent = v; n.style.display = v ? "" : "none"; }
    var w = $("[data-wishlist-count]"), nw = $("#mbWish .nb");
    if (nw && w) { var v2 = parseInt(w.textContent, 10) || 0; nw.textContent = v2; nw.style.display = v2 ? "" : "none"; }
  }
  $$(".m-bottom-nav a[href]").forEach(function (a) {
    try {
      var p = new URL(a.href, location.href).pathname;
      if (p === location.pathname && !a.dataset.noActive) a.classList.add("active");
    } catch (_) {}
  });
  var mbSearch = $("#mbSearch");
  if (mbSearch) mbSearch.addEventListener("click", function () { var t = $("#mobileSearchToggle"); if (t) t.click(); });
  syncBottomNav();

  /* ------------------------------------------------------------------ *
   * 9. Hero parallax (very light) + 3D tilt on feature cards (desktop)
   * ------------------------------------------------------------------ */
  var hero = $(".hero") || $(".hero-section");
  if (hero && !reduce && window.matchMedia("(hover:hover)").matches) {
    var layer = function () { return $(".carousel-item.active .hero-image, .carousel-item.active .hero-slide-img", hero); };
    hero.addEventListener("mousemove", function (e) {
      var r = hero.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      var el = layer();
      if (el && el.classList.contains("hero-image")) el.style.transform = "translate(" + x * -16 + "px," + y * -10 + "px)";
    });
    hero.addEventListener("mouseleave", function () { var el = layer(); if (el && el.classList.contains("hero-image")) el.style.transform = ""; });
  }
  if (!reduce && window.matchMedia("(hover:hover)").matches) {
    doc.addEventListener("mousemove", function (e) {
      var c = e.target.closest && e.target.closest(".product-card");
      $$(".product-card.m-tilt").forEach(function (o) { if (o !== c) { o.classList.remove("m-tilt"); o.style.transform = ""; } });
      if (!c) return;
      var r = c.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      c.classList.add("m-tilt");
      c.style.transform = "translateY(-8px) perspective(900px) rotateX(" + (-y * 5) + "deg) rotateY(" + (x * 6) + "deg)";
    }, { passive: true });
  }

  /* ------------------------------------------------------------------ *
   * 10. Cart page: free-shipping meter, total flash, animated removal
   * ------------------------------------------------------------------ */
  var totalEl = $("#summaryTotal");
  if (totalEl) {
    var card = totalEl.closest(".card-body"), hr = card && $("hr", card);
    var meter = doc.createElement("div");
    meter.className = "m-summary-ship";
    meter.innerHTML = '<div class="msg"></div><div class="bar"><i></i></div>';
    if (hr) hr.parentNode.insertBefore(meter, hr); else if (card) card.appendChild(meter);

    var lastTotal = totalEl.textContent;
    var refreshMeter = function () {
      var sub = num(($("#summarySubtotal") || {}).textContent), disc = num(($("#summaryDiscount") || {}).textContent);
      var net = Math.max(0, sub - Math.abs(disc));
      var done = net >= FREE_SHIP, pct = Math.min(100, Math.round(net / FREE_SHIP * 100));
      meter.classList.toggle("done", done);
      $(".msg", meter).innerHTML = net <= 0 ? "Select items to see your shipping progress"
        : done ? '<i class="bi bi-gift-fill text-success"></i> Nice! Your order qualifies for <b>free shipping</b>'
        : '<i class="bi bi-truck"></i> Add <b>' + money(FREE_SHIP - net) + '</b> more to get <b>free shipping</b>';
      $(".bar > i", meter).style.width = pct + "%";
    };
    new MutationObserver(function () {
      if (totalEl.textContent !== lastTotal) { lastTotal = totalEl.textContent; totalEl.classList.remove("m-total-flash"); void totalEl.offsetWidth; totalEl.classList.add("m-total-flash"); }
      refreshMeter();
    }).observe(totalEl, { childList: true, characterData: true, subtree: true });
    setTimeout(refreshMeter, 250);
  }

  /* checkout button: show a spinner while the server stores the selection */
  var coBtn = $(".checkout-btn");
  if (coBtn) coBtn.addEventListener("click", function () {
    var b = this;
    if (!$(".item-check:checked")) return;
    b.classList.add("is-loading");
    setTimeout(function () { b.classList.remove("is-loading"); }, 6000);
  }, true);

  /* place-order button on checkout: loading state + guard against double submit */
  var placeBtn = $("#placeOrderBtn");
  if (placeBtn) placeBtn.addEventListener("click", function () {
    var f = $("#checkoutForm");
    if (f && f.checkValidity && !f.checkValidity()) {                    // scroll to the first problem, gently
      var bad = $(":invalid", f); if (bad) { bad.scrollIntoView({ behavior: "smooth", block: "center" }); }
      return;
    }
    this.classList.add("is-loading");
    var b = this; setTimeout(function () { b.classList.remove("is-loading"); }, 12000);
  }, true);

  /* ------------------------------------------------------------------ *
   * 11. Image fade-in (removes the skeleton once loaded)
   * ------------------------------------------------------------------ */
  $$(".product-media img, .cart-item img").forEach(function (img) {
    if (img.complete) return;
    img.style.opacity = "0";
    img.addEventListener("load", function () { img.style.transition = "opacity .6s ease"; img.style.opacity = ""; });
    img.addEventListener("error", function () { img.style.opacity = ""; });
  });
})();
