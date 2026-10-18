/* =========================================================
   AUGUST — app.js
   Theme toggle, header behaviour, search overlay, notifications,
   chat widget, countdowns, reveal-on-scroll, validation helpers.
   ========================================================= */
(function(){
  "use strict";

  /* Theme (mode + colour picker) now lives in theme.js, loaded in <head>. */

  /* ---------- Sticky header shadow ---------- */
  const header = document.querySelector(".site-header");
  if(header){
    window.addEventListener("scroll", ()=>{
      header.classList.toggle("is-scrolled", window.scrollY > 8);
      const top = document.querySelector(".fab-top");
      if(top) top.classList.toggle("show", window.scrollY > 500);
    }, { passive: true });
  }

  /* ---------- Back to top ---------- */
  document.addEventListener("click", (e)=>{
    if(e.target.closest(".fab-top")){
      window.scrollTo({ top:0, behavior:"smooth" });
    }
  });

  /* ---------- Mobile mega-menu toggle ---------- */
  document.querySelectorAll(".nav-item.has-mega > .nav-link").forEach(link=>{
    link.addEventListener("click", (e)=>{
      if(window.innerWidth < 992){
        e.preventDefault();
        link.closest(".nav-item").classList.toggle("open");
      }
    });
  });

  /* ---------- Search overlay ---------- */
  const searchOverlay = document.getElementById("searchOverlay");
  document.addEventListener("click", (e)=>{
    if(e.target.closest("[data-open-search]") && searchOverlay){
      searchOverlay.classList.add("show");
      setTimeout(()=> searchOverlay.querySelector("input")?.focus(), 200);
    }
    if((e.target.closest(".search-close") || e.target === searchOverlay) && searchOverlay){
      searchOverlay.classList.remove("show");
    }
  });
  document.addEventListener("keydown", (e)=>{
    if(e.key === "Escape" && searchOverlay) searchOverlay.classList.remove("show");
  });

  /* ---------- Toast helper ---------- */
  // Branded toast (see szui.js). Falls back to a no-op if szui.js is not loaded.
  window.showToast = function(message, variant="brass"){
    if (window.SZ && SZ.toast) SZ.toast(message, variant === "rust" ? "danger" : "success");
  };

  /* ---------- Chat widget ---------- */
  document.addEventListener("click", (e)=>{
    if(e.target.closest("[data-toggle-chat]")){
      document.getElementById("chatWindow")?.classList.toggle("show");
    }
    if(e.target.closest("[data-close-chat]")){
      document.getElementById("chatWindow")?.classList.remove("show");
    }
  });
  const chatForm = document.getElementById("chatForm");
  if(chatForm){
    chatForm.addEventListener("submit", (e)=>{
      e.preventDefault();
      const input = chatForm.querySelector("input");
      if(!input.value.trim()) return;
      const body = document.getElementById("chatBody");
      const me = document.createElement("div");
      me.className = "chat-bubble me";
      me.textContent = input.value;
      body.appendChild(me);
      input.value = "";
      body.scrollTop = body.scrollHeight;
      setTimeout(()=>{
        const them = document.createElement("div");
        them.className = "chat-bubble them";
        them.textContent = "Thanks for reaching out — a stylist will reply within a few minutes.";
        body.appendChild(them);
        body.scrollTop = body.scrollHeight;
      }, 900);
    });
  }

  /* ---------- Countdown timers ---------- */
  function startCountdown(el){
    const end = new Date(el.dataset.countdown).getTime();
    function tick(){
      const dist = end - Date.now();
      if(dist <= 0){ el.innerHTML = "<span class='unit'><b>00</b><span>Ended</span></span>"; return; }
      const d = Math.floor(dist/86400000);
      const h = Math.floor((dist%86400000)/3600000);
      const m = Math.floor((dist%3600000)/60000);
      const s = Math.floor((dist%60000)/1000);
      el.querySelectorAll("[data-u]").forEach(u=>{
        const map = {d,h,m,s};
        u.textContent = String(map[u.dataset.u]).padStart(2,"0");
      });
    }
    tick();
    setInterval(tick, 1000);
  }
  document.querySelectorAll("[data-countdown]").forEach(startCountdown);

  /* ---------- Reveal on scroll ---------- */
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting){ entry.target.classList.add("in"); io.unobserve(entry.target); }
    });
  }, { threshold: .15 });
  document.querySelectorAll(".reveal").forEach(el=> io.observe(el));

  /* ---------- Bootstrap-style client validation ---------- */
  document.querySelectorAll("form.needs-validation").forEach(form=>{
    form.addEventListener("submit", function(e){
      if(!form.checkValidity()){
        e.preventDefault();
        e.stopPropagation();
      } else if (form.dataset.demoSubmit !== undefined) {
        e.preventDefault();
        window.showToast(form.dataset.successMessage || "Done.");
      }
      form.classList.add("was-validated");
    });
  });

  /* ---------- OTP input auto-advance ---------- */
  document.querySelectorAll(".otp-group").forEach(group=>{
    const inputs = [...group.querySelectorAll(".otp-input")];
    inputs.forEach((input, i)=>{
      input.addEventListener("input", ()=>{
        input.value = input.value.replace(/\D/g,"").slice(0,1);
        if(input.value && inputs[i+1]) inputs[i+1].focus();
      });
      input.addEventListener("keydown", (e)=>{
        if(e.key === "Backspace" && !input.value && inputs[i-1]) inputs[i-1].focus();
      });
    });
  });

  /* ---------- Quantity steppers ---------- */
  document.addEventListener("click", (e)=>{
    const btn = e.target.closest("[data-qty-step]");
    if(!btn) return;
    const wrap = btn.closest(".qty-stepper");
    const input = wrap.querySelector("input");
    let val = parseInt(input.value || "1", 10);
    val += parseInt(btn.dataset.qtyStep, 10);
    if(val < 1) val = 1;
    if(val > 99) val = 99;
    input.value = val;
    input.dispatchEvent(new Event("change", { bubbles:true }));
  });

  /* ---------- Star rating input (reviews form) ---------- */
  document.querySelectorAll(".rating-input").forEach(group=>{
    const stars = [...group.querySelectorAll("i")];
    stars.forEach((star, idx)=>{
      star.addEventListener("click", ()=>{
        group.dataset.value = idx+1;
        stars.forEach((s,i)=> s.className = i<=idx ? "bi bi-star-fill" : "bi bi-star");
      });
    });
  });

  /* ---------- Size / variant selectors ---------- */
  document.addEventListener("click", (e)=>{
    const pill = e.target.closest(".size-pill:not(.disabled)");
    if(pill){
      pill.closest(".d-flex, .size-group")?.querySelectorAll(".size-pill").forEach(p=>p.classList.remove("active"));
      pill.classList.add("active");
    }
    const swatch = e.target.closest(".variant-swatch");
    if(swatch){
      swatch.closest(".d-flex, .variant-group")?.querySelectorAll(".variant-swatch").forEach(s=>s.classList.remove("active"));
      swatch.classList.add("active");
      const label = document.querySelector("[data-variant-label]");
      if(label && swatch.dataset.color) label.textContent = swatch.dataset.color;
    }
  });

  /* ---------- Image zoom (PDP) ---------- */
  document.querySelectorAll(".pdp-main-media[data-zoom]").forEach(media=>{
    const img = media.querySelector("img");
    media.addEventListener("mousemove", (e)=>{
      if(window.innerWidth < 992) return;
      const rect = media.getBoundingClientRect();
      const x = ((e.clientX - rect.left)/rect.width)*100;
      const y = ((e.clientY - rect.top)/rect.height)*100;
      img.style.transformOrigin = `${x}% ${y}%`;
      img.style.transform = "scale(1.8)";
    });
    media.addEventListener("mouseleave", ()=>{
      img.style.transform = "scale(1)";
    });
  });

  /* ---------- PDP thumbnail switch ---------- */
  document.addEventListener("click", (e)=>{
    const thumb = e.target.closest(".pdp-thumb");
    if(!thumb) return;
    const gallery = thumb.closest("[data-gallery]");
    gallery.querySelectorAll(".pdp-thumb").forEach(t=>t.classList.remove("active"));
    thumb.classList.add("active");
    const main = gallery.querySelector(".pdp-main-media img");
    if(main && thumb.dataset.full) main.src = thumb.dataset.full;
  });

})();
