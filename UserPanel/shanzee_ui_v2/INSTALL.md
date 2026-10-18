# Shan Zee UI v2 — colour themes, custom alerts, guidance, dark/light

1. Copy `static/css/*` and `static/js/*` into your project's `static/`
   (new: `js/theme.js`, `js/szui.js`; changed: `css/modern.css`, `js/app.js`, `js/motion.js`).
2. Replace your `templates/` folder with the one here (`base2.html` loads `theme.js` in `<head>`).
3. `collectstatic` if you use it, then hard-refresh (Ctrl+F5).

## Colours
- Palette button in the header opens "Make it yours": Light / Dark / Auto, 12 colour themes, and free colour pickers (main + highlight).
- Everything derives from the chosen colour: gradients, soft tints, glow, link/text colour and **button text colour** (light colours such as yellow automatically get dark text).
- Saved per visitor (`shanzee-theme`, `shanzee-accent`). Default stays Shan Zee green #198754. API: `SZTheme.setColors('#7c3aed')`, `SZTheme.setMode('dark')`, `SZTheme.reset()`.
- In your own CSS use `var(--accent)`, `var(--accent-deep)` (readable text), `var(--accent-soft)`, `var(--accent-grad)`, `var(--on-accent)` instead of fixed hex colours.

## Alerts & guidance
`SZ.toast("Saved","success")`, `await SZ.confirm("Delete?",{tone:"danger"})`; `<aside class="sz-guide" data-guide="id">` panels on key pages.
