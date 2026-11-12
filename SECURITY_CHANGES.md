# Security fixes in this delivery

| # | Problem | Fix | Where |
|---|---------|-----|-------|
| 1 | SECRET_KEY + SMTP password hardcoded; `.env` shipped in the zip; DEBUG on | All secrets from env (`.env.example`), DEBUG off by default, HTTPS/secure cookies/HSTS when DEBUG is off | `shanzeeecommerce/settings.py` |
| 2 | Any logged-in customer could edit/delete products, variants, images, promotions, tags | All admin-panel views in `products/views.py` are staff-only; delete actions are POST-only (links now submit a POST form) | `products/views.py`, `product_form.html` |
| 3 | Reports (sales/revenue) open to everyone / any JWT | Pages staff-only, APIs `IsAdminUser` | `reports/views.py` |
| 4 | `/api/v1/users/` let any user list all users and block/unblock anyone | `IsAdminUser`; users page staff-only | `accounts/views.py` |
| 5 | Order detail API returned any order by id | Filtered to the requesting user's orders | `Web/views.py OrderDetailAPIView` |
| 6 | Order cancel/return requests could target other users' orders | Order must belong to the user | `Web/views.py OrderRequestAPIView` |
| 7 | Remove-cart-item worked on any cart (no login needed) | Only items in your own cart (user or session) | `Web/views.py RemoveCartItemAPIView` |
| 8 | Chat WebSocket let anyone join any thread | Owner or staff only; new-thread placeholder is a private group | `chat/consumers.py` |
| 9 | `send_message` was `csrf_exempt` without login, and crashed on a first message | Login + CSRF + POST required; thread is created correctly | `Web/views.py send_message` |
| 10 | Stock check and decrement were not atomic (two checkouts could oversell) | Conditional SQL `UPDATE ... WHERE stock >= qty`; checkout returns a clean error; cancel/return restock uses F() too | `Web/models.py`, `Web/serializers.py` |
| 11 | Password-reset OTP used `random` and could be guessed without limit | `secrets` generator, code burned after 5 wrong tries, rate limits on forgot/resend/reset | `accounts/utils.py`, `accounts/views.py` |
| 12 | Unlimited login attempts | 10/5 min per IP and 5/5 min per username | `accounts/views.py` |
| 13 | `IsAdminRole` crashed for anonymous users | Checks authentication first | `products/views.py` |
| 14 | Duplicate `userpanel` URL include registered the `home` namespace twice | Removed (nothing linked to it) | `shanzeeecommerce/urls.py` |

Not changed (still worth doing): payment gateway, splitting the large view files, removing the
`shanzee_ui_v2` / `* copy.html` duplicates.
