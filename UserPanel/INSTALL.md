# Shan Zee UI refresh

1. Copy `static/css/modern.css` -> your `static/css/` and `static/js/motion.js` -> your `static/js/`.
2. Replace your `templates/` folder with the one here (the `* copy.html` backups are not included).
3. Run `collectstatic` if you use it.

Notes
- Section colours come from `{% block body_class %}theme-xxx{% endblock %}` at the top of each page
  (shop, checkout, orders, account, wishlist, blog, support, deals, product).
- Cart free-shipping goal: `data-goal="3500"` in `home/cart.html`.
- Quick-add on product cards opens the existing quick view.
