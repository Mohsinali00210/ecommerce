/* =====================================================================
   SHAN ZEE — MOTION & INTERACTION LAYER
   Pure vanilla JS, no dependencies. Safe to load on every page: every
   feature checks that its target exists, and nothing here touches the
   cart / wishlist / checkout business logic.
   ===================================================================== */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  root.classList.add('js');

  function $(sel, ctx) { return (ctx || doc).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || doc).querySelectorAll(sel)); }
  function ready(fn) { doc.readyState !== 'loading' ? fn() : doc.addEventListener('DOMContentLoaded', fn); }
  function raf(fn) { return window.requestAnimationFrame(fn); }

  /* ---------- scroll progress bar + shared scroll state ------------- */
  var scrollSubs = [];
  function onScroll(fn) { scrollSubs.push(fn); }
  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    raf(function () {
      var y = window.pageYOffset || root.scrollTop;
      var h = Math.max(1, root.scrollHeight - window.innerHeight);
      scrollSubs.forEach(function (fn) { fn(y, y / h); });
      ticking = false;
    });
  }, { passive: true });

  function scrollProgress() {
    var bar = doc.createElement('div');
    bar.className = 'mz-progress';
    doc.body.appendChild(bar);
    onScroll(function (y, p) { bar.style.transform = 'scaleX(' + p.toFixed(4) + ')'; });
  }

  /* ---------- sticky header: shadow + hide on scroll-down ----------- */
  function headerBehaviour() {
    var header = $('.site-header');
    if (!header) return;
    var last = 0;
    onScroll(function (y) {
      header.classList.toggle('is-scrolled', y > 8);
      // hide when scrolling down past the header, reveal on any upward scroll
      if (y > 220 && y > last + 6) header.classList.add('is-hidden');
      else if (y < last - 4 || y < 220) header.classList.remove('is-hidden');
      last = y;
    });
    // never hide while a dropdown / search is open
    doc.addEventListener('show.bs.dropdown', function () { header.classList.remove('is-hidden'); });
  }

  /* ---------- reveal on scroll (+ automatic stagger) ---------------- */
  function revealOnScroll() {
    // elements that should animate in even if the template forgot .reveal
    var auto = [
      '.section-head', '.trust-item', '.mz-promo', '.mz-cat-tile', '.newsletter-band',
      '.checkout-panel', '.summary-card', '.cart-item', '.mz-ship', '.card',
      '.blog-card', '.post-card', '.account-nav-link', '.table-responsive',
      '.site-footer .col-6', '.site-footer .col-lg-4'
    ].join(',');
    $$(auto).forEach(function (el) {
      if (!el.classList.contains('reveal') && !el.closest('.modal, .dropdown-menu, .offcanvas')) el.classList.add('reveal');
    });

    // stagger siblings: a grid / row marks its own children
    $$('[data-stagger], .row.g-3, .row.g-4, .trust-row .row, .cat-strip-group').forEach(function (parent) {
      var kids = $$(':scope > .reveal, :scope > [class*="col"] .reveal, :scope > [class*="col"].reveal', parent);
      kids.forEach(function (el, i) { el.style.setProperty('--d', Math.min(i, 12) * 70 + 'ms'); });
    });

    var items = $$('.reveal, .reveal-left, .reveal-right, .reveal-zoom');
    if (reduce || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -6% 0px' });
    items.forEach(function (el) { if (!el.classList.contains('in')) io.observe(el); });

    // tab panes / dynamically injected cards (quick view, ajax grids)
    var mo = new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1) return;
          var found = n.matches && n.matches('.reveal') ? [n] : [];
          found = found.concat($$('.reveal', n));
          found.forEach(function (el) { if (!el.classList.contains('in')) io.observe(el); });
        });
      });
    });
    mo.observe(doc.body, { childList: true, subtree: true });

    // safety net — never leave content invisible
    setTimeout(function () {
      $$('.reveal:not(.in), .reveal-left:not(.in), .reveal-right:not(.in), .reveal-zoom:not(.in)').forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight * 1.2) el.classList.add('in');
      });
    }, 2500);
  }

  /* ---------- material ripple on buttons ---------------------------- */
  function rippleButtons() {
    if (reduce) return;
    doc.addEventListener('pointerdown', function (e) {
      var btn = e.target.closest && e.target.closest('.btn-brass, .btn-brass2, .btn-primary, .btn-light, .btn-outline-ink');
      if (!btn) return;
      var rect = btn.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height);
      var s = doc.createElement('span');
      s.className = 'mz-ripple';
      s.style.cssText = 'width:' + size + 'px;height:' + size + 'px;left:' + (e.clientX - rect.left - size / 2) + 'px;top:' + (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(s);
      setTimeout(function () { s.remove(); }, 650);
    }, { passive: true });
  }

  /* ---------- bump header badges whenever their number changes ------ */
  function badgeBump() {
    var targets = $$('[data-cart-count], [data-wishlist-count], #notificationCount');
    targets.forEach(function (el) {
      var prev = el.textContent;
      new MutationObserver(function () {
        if (el.textContent === prev) return;
        prev = el.textContent;
        var host = el.closest('[data-bump]') || el;
        [el, host].forEach(function (n) {
          n.classList.remove('mz-bump'); void n.offsetWidth; n.classList.add('mz-bump');
        });
        syncBottomNav();
      }).observe(el, { childList: true, characterData: true, subtree: true });
    });
  }

  /* ---------- back to top with progress ring ------------------------ */
  function backToTop() {
    var b = doc.createElement('button');
    b.className = 'mz-top';
    b.setAttribute('aria-label', 'Back to top');
    b.innerHTML = '<svg width="48" height="48" viewBox="0 0 48 48"><circle class="trk" cx="24" cy="24" r="22"/><circle class="bar" cx="24" cy="24" r="22"/></svg><i class="bi bi-arrow-up"></i>';
    doc.body.appendChild(b);
    var bar = $('.bar', b);
    onScroll(function (y, p) {
      b.classList.toggle('show', y > 600);
      bar.style.strokeDashoffset = String(138.2 * (1 - p));
    });
    b.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' }); });
  }

  /* ---------- count-up numbers -------------------------------------- */
  function countUp() {
    var els = $$('[data-countup]');
    if (!els.length || !('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        var el = e.target, end = parseFloat(el.getAttribute('data-countup')) || 0;
        var dur = 1400, t0 = null, dec = (String(end).split('.')[1] || '').length;
        function step(t) {
          if (!t0) t0 = t;
          var k = Math.min(1, (t - t0) / dur), ease = 1 - Math.pow(1 - k, 3);
          el.textContent = (end * ease).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
          if (k < 1) raf(step);
        }
        raf(step);
      });
    }, { threshold: .5 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- countdown ([data-countdown="ISO date"]) --------------- */
  function countdowns() {
    $$('[data-countdown]').forEach(function (el) {
      var end = new Date(el.getAttribute('data-countdown')).getTime();
      if (!end || isNaN(end)) return;
      var parts = {
        d: $('[data-u="d"]', el), h: $('[data-u="h"]', el), m: $('[data-u="m"]', el), s: $('[data-u="s"]', el)
      };
      function pad(n) { return String(n).padStart(2, '0'); }
      function tick() {
        var left = Math.max(0, end - Date.now());
        var s = Math.floor(left / 1000);
        if (parts.d) parts.d.textContent = pad(Math.floor(s / 86400));
        if (parts.h) parts.h.textContent = pad(Math.floor(s % 86400 / 3600));
        if (parts.m) parts.m.textContent = pad(Math.floor(s % 3600 / 60));
        if (parts.s) parts.s.textContent = pad(s % 60);
      }
      tick(); setInterval(tick, 1000);
    });
  }

  /* ---------- cursor-follow glow on [data-glow] cards --------------- */
  function cursorGlow() {
    if (reduce) return;
    doc.addEventListener('pointermove', function (e) {
      var el = e.target.closest && e.target.closest('[data-glow]');
      if (!el) return;
      var r = el.getBoundingClientRect();
      el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      el.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }, { passive: true });
  }

  /* ---------- heart pop on wishlist toggle -------------------------- */
  function wishlistPop() {
    doc.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-wishlist-btn]');
      if (!b) return;
      b.classList.remove('mz-pop'); void b.offsetWidth; b.classList.add('mz-pop');
    });
  }

  /* ---------- mobile bottom nav: mirror header counts --------------- */
  function syncBottomNav() {
    var cart = $('[data-cart-count]'), wish = $('[data-wishlist-count]');
    var cc = $('#mzNavCart'), wc = $('#mzNavWish');
    if (cart && cc) { cc.textContent = cart.textContent; cc.style.display = parseInt(cart.textContent, 10) > 0 ? 'grid' : 'none'; }
    if (wish && wc) { wc.textContent = wish.textContent; wc.style.display = parseInt(wish.textContent, 10) > 0 ? 'grid' : 'none'; }
  }
  function mobileNavSync() {
    syncBottomNav();
    var path = location.pathname.replace(/\/+$/, '') || '/';
    $$('.mz-bottom-nav a[href]').forEach(function (a) {
      var p = (a.getAttribute('href') || '').replace(/\/+$/, '') || '/';
      if (p === path) a.classList.add('active');
    });
    var s = $('#mzNavSearch');
    if (s) s.addEventListener('click', function () {
      var t = $('#mobileSearchToggle'); if (t) t.click();
    });
    var m = $('#mzNavMenu');
    if (m) m.addEventListener('click', function () {
      var off = $('#mobileNav');
      if (off && window.bootstrap) bootstrap.Offcanvas.getOrCreateInstance(off).show();
    });
  }

  /* ---------- cart: free-shipping progress meter -------------------- */
  function shippingMeter() {
    var meter = $('#mzShipMeter');
    var sub = $('#summarySubtotal');
    if (!meter || !sub) return;
    var goal = parseFloat(meter.getAttribute('data-goal')) || 3500;
    var fill = $('i', meter), msg = $('.msg', meter);
    function num(t) { return parseFloat(String(t).replace(/[^0-9.]/g, '')) || 0; }
    function update() {
      var v = num(sub.textContent);
      var pct = Math.min(100, Math.round(v / goal * 100));
      fill.style.width = pct + '%';
      var ok = v >= goal;
      meter.classList.toggle('ok', ok);
      msg.innerHTML = ok
        ? '<i class="bi bi-stars me-1"></i><strong>You\'ve unlocked free shipping!</strong>'
        : '<i class="bi bi-truck me-1"></i>Add <strong>RS ' + (goal - v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + '</strong> more for <strong>free shipping</strong>';
    }
    update();
    // the cart JS rewrites the subtotal on quantity / selection changes
    new MutationObserver(update).observe(sub, { childList: true, characterData: true, subtree: true });
  }

  /* ---------- cart: slide-out when a row is removed ----------------- */
  function cartRemoveMotion() {
    doc.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('.remove-cart-item');
      if (!b) return;
      var row = b.closest('.cart-item');
      if (row) row.classList.add('is-removing');
    }, true);
  }

  /* ---------- checkout: highlight the panel you're working on ------- */
  function checkoutFocus() {
    var panels = $$('#checkoutForm .checkout-panel');
    if (!panels.length) return;
    doc.addEventListener('focusin', function (e) {
      var p = e.target.closest && e.target.closest('.checkout-panel');
      if (!p) return;
      panels.forEach(function (x) { x.classList.toggle('is-current', x === p); });
      var idx = panels.indexOf(p);
      $$('#mzCheckoutSteps [data-step]').forEach(function (s) {
        var n = parseInt(s.getAttribute('data-step'), 10);
        s.classList.toggle('active', n === idx + 1);
        s.classList.toggle('done', n < idx + 1);
      });
    });
  }

  /* ---------- product page: sticky buy bar on mobile ---------------- */
  function productBuyBar() {
    var add = $('#addToCartBtn');
    if (!add) return;
    var priceEl = $('#priceNow');
    var bar = doc.createElement('div');
    bar.className = 'mz-buybar';
    bar.innerHTML =
      '<div class="flex-grow-1"><div class="small text-muted-custom">Total price</div><div class="fw-bold font-display fs-5" id="mzBuyPrice"></div></div>' +
      '<button type="button" class="btn btn-brass px-4"><i class="bi bi-bag-plus me-1"></i>Add to cart</button>';
    doc.body.appendChild(bar);
    var price = $('#mzBuyPrice', bar);
    function syncPrice() { if (priceEl) price.textContent = priceEl.textContent.trim(); }
    syncPrice();
    if (priceEl) new MutationObserver(syncPrice).observe(priceEl, { childList: true, characterData: true, subtree: true });
    $('button', bar).addEventListener('click', function () { add.click(); });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (en) { bar.classList.toggle('show', !en[0].isIntersecting && en[0].boundingClientRect.top < 0); }, { threshold: 0 }).observe(add);
    }
  }

  /* ---------- init (last, so every helper above is defined) ---------- */
  ready(function () {
    scrollProgress();
    headerBehaviour();
    revealOnScroll();
    rippleButtons();
    badgeBump();
    backToTop();
    countUp();
    countdowns();
    cursorGlow();
    wishlistPop();
    mobileNavSync();
    shippingMeter();
    cartRemoveMotion();
    checkoutFocus();
    productBuyBar();
  });
})();
