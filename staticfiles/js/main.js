document.addEventListener('DOMContentLoaded', function () {

  /* ---------- Flash Sale Countdown ---------- */
  document.querySelectorAll('.countdown').forEach(function (el) {
    var endAttr = el.getAttribute('data-countdown');
    var endTime = endAttr ? new Date(endAttr).getTime() : (Date.now() + (2 * 3600 + 18 * 60 + 45) * 1000);

    function tick() {
      var diff = endTime - Date.now();
      if (diff <= 0) { el.textContent = '00:00:00'; return; }
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      el.textContent = [h, m, s].map(function (n) { return String(n).padStart(2, '0'); }).join(':');
    }
    tick();
    setInterval(tick, 1000);
  });

  /* ---------- Wishlist toggle (visual + optional AJAX) ---------- */
  document.querySelectorAll('.wishlist-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var icon = btn.querySelector('i');
      btn.classList.toggle('active');
      icon.classList.toggle('bi-heart');
      icon.classList.toggle('bi-heart-fill');

      // Wire this up to your Django endpoint, e.g.:
      // fetch(`/wishlist/toggle/${btn.dataset.productId}/`, {
      //   method: 'POST',
      //   headers: { 'X-CSRFToken': getCookie('csrftoken') }
      // });
    });
  });

  /* ---------- Compare toggle ---------- */
  document.querySelectorAll('.compare-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('active');
    });
  });

  /* ---------- Add to cart via fetch (progressive enhancement) ---------- */
  document.querySelectorAll('.add-to-cart-form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      // Falls back to normal form POST if JS/fetch fails.
      // Uncomment to enable AJAX add-to-cart:
      //
      // e.preventDefault();
      // fetch(form.action, {
      //   method: 'POST',
      //   body: new FormData(form),
      //   headers: { 'X-Requested-With': 'XMLHttpRequest' }
      // })
      //   .then(function (res) { return res.json(); })
      //   .then(function (data) { updateCartCount(data.cart_count); showToast('Added to cart'); })
      //   .catch(function () { form.submit(); });
    });
  });

  /* ---------- Product grid horizontal scroll buttons ---------- */
  document.querySelectorAll('.scroll-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var grid = document.querySelector('.tab-pane.active .product-grid, .tab-pane.show .product-grid');
      if (!grid) return;
      grid.scrollBy({ left: parseInt(btn.dataset.dir, 10) * 300, behavior: 'smooth' });
    });
  });

  /* ---------- Category strip scroll arrow ---------- */
  var catNavBtn = document.querySelector('.category-nav-btn');
  var catScroll = document.querySelector('.category-scroll');
  if (catNavBtn && catScroll) {
    catNavBtn.addEventListener('click', function () {
      catScroll.scrollBy({ left: 240, behavior: 'smooth' });
    });
  }

  /* ---------- Simple messaging modal demo ---------- */
  var msgInput = document.querySelector('.modal-footer input');
  var msgSend = document.querySelector('.send-btn');
  var msgBody = document.querySelector('.messaging-body');
  if (msgSend && msgInput && msgBody) {
    msgSend.addEventListener('click', function () {
      var text = msgInput.value.trim();
      if (!text) return;
      var bubble = document.createElement('div');
      bubble.className = 'msg-bubble user';
      bubble.textContent = text;
      msgBody.appendChild(bubble);
      msgBody.scrollTop = msgBody.scrollHeight;
      msgInput.value = '';
    });
  }

  /* ---------- CSRF helper for future AJAX calls ---------- */
  window.getCookie = function (name) {
    var value = null;
    if (document.cookie && document.cookie !== '') {
      document.cookie.split(';').forEach(function (cookie) {
        cookie = cookie.trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          value = decodeURIComponent(cookie.substring(name.length + 1));
        }
      });
    }
    return value;
  };

});
