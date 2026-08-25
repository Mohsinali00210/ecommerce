/* =========================================================
   AUGUST — cart.js
   Cart / Wishlist / Compare / Recently Viewed, persisted to
   localStorage so state carries across every page.
   ========================================================= */
(function(){
  "use strict";

  const LS = {
    cart: "august-cart",
    wishlist: "august-wishlist",
    compare: "august-compare",
    recent: "august-recent"
  };

  const Store = {
    get(key){ try{ return JSON.parse(localStorage.getItem(key)) || []; } catch(e){ return []; } },
    set(key, val){ localStorage.setItem(key, JSON.stringify(val)); }
  };

  /* Demo catalog snapshot used to hydrate cards by data-id when a page
     only lists an id (kept intentionally small — real app would fetch). */
  window.AUGUST_CATALOG = window.AUGUST_CATALOG || {};

  function registerProduct(el){
    const id = el.dataset.id;
    if(!id) return;
    if(!window.AUGUST_CATALOG[id]){
      window.AUGUST_CATALOG[id] = {
        id,
        name: el.dataset.name || "Product",
        price: parseFloat(el.dataset.price || "0"),
        was: parseFloat(el.dataset.was || "0"),
        image: el.dataset.image || "",
        cat: el.dataset.cat || ""
      };
    }
  }
  document.querySelectorAll("[data-id]").forEach(registerProduct);

  /* ---------- Cart ---------- */
  window.Cart = {
    items(){ return Store.get(LS.cart); },
    add(id, qty=1, meta={}){
      const items = Store.get(LS.cart);
      const existing = items.find(i => i.id === id && i.variant === (meta.variant || ""));
      if(existing){ existing.qty += qty; }
      else{
        const product = window.AUGUST_CATALOG[id] || {};
        items.push({ id, qty, variant: meta.variant || "", size: meta.size || "", ...product });
      }
      Store.set(LS.cart, items);
      renderBadges();
      bumpIcon("cart");
      window.showToast && window.showToast("Added to cart.");
    },
    updateQty(id, qty){
      const items = Store.get(LS.cart);
      const item = items.find(i=>i.id===id);
      if(item){ item.qty = Math.max(1, qty); Store.set(LS.cart, items); }
      renderBadges();
      renderCartPage();
    },
    remove(id){
      Store.set(LS.cart, Store.get(LS.cart).filter(i=>i.id!==id));
      renderBadges();
      renderCartPage();
      window.showToast && window.showToast("Removed from cart.", "rust");
    },
    subtotal(){
      return Store.get(LS.cart).reduce((sum,i)=> sum + (i.price||0)*i.qty, 0);
    },
    count(){ return Store.get(LS.cart).reduce((n,i)=> n+i.qty, 0); }
  };

  /* ---------- Wishlist ---------- */
  window.Wishlist = {
      items() {
          return Store.get(LS.wishlist);
      },
      has(id) {
          return Store.get(LS.wishlist).some(i => i.id == id);
      },
      toggle(id) {
        debugger
          let items = Store.get(LS.wishlist);
          let url = "/wishlisttoggle/" + id + "/";
          console.log("product id"+id);   // or use your generated URL
          fetch(url, {
              method: "GET",
              headers: {
                  "X-Requested-With": "XMLHttpRequest"
              }
          })
          .then(response => response.json())
          .then(data => {
              if (data.status === "added") {
                  if (!items.some(i => i.id == id)) {
                      const product = window.AUGUST_CATALOG[id] || {};
                      items.push({ id, ...product });
                  }
                  window.showToast && window.showToast("Added to wishlist.");
              }
              else if (data.status === "removed") {
                  items = items.filter(i => i.id != id);
                  window.showToast && window.showToast("Removed from wishlist.");
              }
              Store.set(LS.wishlist, items);
              renderBadges();
              syncWishlistIcons();
          })
          .catch(err => {
              console.error(err);
              window.showToast && window.showToast("Something went wrong.");
          });
      },
      remove(id) {
          Store.set(
              LS.wishlist,
              Store.get(LS.wishlist).filter(i => i.id != id)
          );
          renderBadges();
          syncWishlistIcons();
      }
  };

  /* ---------- Compare ---------- */
  window.Compare = {
    items(){ return Store.get(LS.compare); },
    toggle(id){
      let items = Store.get(LS.compare);
      if(items.some(i=>i.id===id)){
        items = items.filter(i=>i.id!==id);
      } else {
        if(items.length >= 4){ window.showToast && window.showToast("Compare list holds up to 4 items.", "rust"); return; }
        const product = window.AUGUST_CATALOG[id] || {};
        items.push({ id, ...product });
      }
      Store.set(LS.compare, items);
      renderBadges();
    }
  };

  /* ---------- Recently viewed ---------- */
  window.RecentlyViewed = {
    track(id){
      let items = Store.get(LS.recent).filter(i=>i.id!==id);
      const product = window.AUGUST_CATALOG[id] || {};
      items.unshift({ id, ...product });
      items = items.slice(0, 8);
      Store.set(LS.recent, items);
    },
    items(){ return Store.get(LS.recent); }
  };

  /* ---------- UI sync ---------- */
  function renderBadges(){
    document.querySelectorAll("[data-cart-count]").forEach(el=>{
      // const n = window.Cart.count();
      // el.textContent = n;
      // el.style.display = n > 0 ? "flex" : "none";
    });
    document.querySelectorAll("[data-wishlist-count]").forEach(el=>{
      const n = Store.get(LS.wishlist).length;
      el.textContent = n;
      el.style.display = n > 0 ? "flex" : "none";
    });
    document.querySelectorAll("[data-compare-count]").forEach(el=>{
      const n = Store.get(LS.compare).length;
      el.textContent = n;
      el.style.display = n > 0 ? "flex" : "none";
    });
  }

  function syncWishlistIcons(){
    document.querySelectorAll("[data-wishlist-btn]").forEach(btn=>{
      const id = btn.dataset.wishlistBtn;
      btn.classList.toggle("active", window.Wishlist.has(id));
    });
  }

  function bumpIcon(name){
    const el = document.querySelector(`[data-bump="${name}"]`);
    if(!el) return;
    el.classList.remove("cart-bump");
    void el.offsetWidth;
    el.classList.add("cart-bump");
  }

  /* ---------- Cart page rendering ---------- */
  function renderCartPage(){
    const list = document.getElementById("cartList");
    if(!list) return;
    const items = window.Cart.items();
    if(items.length === 0){
      list.innerHTML = `<div class="text-center py-5">
        <i class="bi bi-bag-x display-4 text-muted-custom"></i>
        <p class="mt-3 text-muted-custom">Your bag is empty. Everything you love is one click away.</p>
        <a href="shop.html" class="btn btn-brass mt-2">Continue Shopping</a>
      </div>`;
    } else {
      list.innerHTML = items.map(i => `
        <div class="cart-row" data-row="${i.id}">
          <div class="cart-thumb"><img src="${i.image || 'https://placehold.co/200x200'}" alt="${i.name}"></div>
          <div class="flex-grow-1">
            <div class="d-flex justify-content-between">
              <div>
                <div class="fw-semibold">${i.name}</div>
                <small class="text-muted-custom">${i.variant || ''} ${i.size ? '· Size ' + i.size : ''}</small>
              </div>
              <button class="btn btn-sm btn-ghost text-danger" onclick="Cart.remove('${i.id}')"><i class="bi bi-trash"></i></button>
            </div>
            <div class="d-flex justify-content-between align-items-center mt-2">
              <div class="qty-stepper">
                <button data-qty-step="-1" onclick="Cart.updateQty('${i.id}', ${i.qty}-1)">−</button>
                <input type="text" readonly value="${i.qty}">
                <button data-qty-step="1" onclick="Cart.updateQty('${i.id}', ${i.qty}+1)">+</button>
              </div>
              <span class="price-now">$${(i.price*i.qty).toFixed(2)}</span>
            </div>
          </div>
        </div>`).join("");
    }
    const subtotal = window.Cart.subtotal();
    document.querySelectorAll("[data-cart-subtotal]").forEach(el=> el.textContent = `$${subtotal.toFixed(2)}`);
    const shipping = subtotal > 75 || subtotal === 0 ? 0 : 6.5;
    document.querySelectorAll("[data-cart-shipping]").forEach(el=> el.textContent = shipping === 0 ? "Free" : `$${shipping.toFixed(2)}`);
    document.querySelectorAll("[data-cart-total]").forEach(el=> el.textContent = `$${(subtotal+shipping).toFixed(2)}`);
    const bar = document.querySelector(".free-ship-progress span");
    if(bar){
      const pct = Math.min(100, (subtotal/75)*100);
      bar.style.width = pct + "%";
      const note = document.querySelector("[data-free-ship-note]");
      if(note) note.textContent = subtotal >= 75 ? "You've unlocked free shipping!" : `Add $${(75-subtotal).toFixed(2)} more for free shipping`;
    }
  }

  document.addEventListener("DOMContentLoaded", ()=>{
    renderBadges();
    syncWishlistIcons();
    renderCartPage();
  });

  /* expose for inline onclick usage */
  window.renderCartPage = renderCartPage;
})();
