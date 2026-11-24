# NovaSwap — integration starter

Full-stack prototype with a responsive browser UI, Python HTTP backend, SQLite schema, ChangeNOW adapter and Binance public market reference data. Not a certified or production-ready financial service. No fake deposits or payouts. Live orders off by default.

## Start locally (Windows)
Install Python 3.11+ from python.org (include Python launcher). Extract the ZIP. Copy `.env.example` to `.env` if configuring credentials; otherwise run `start.bat`. Visit http://localhost:8000. Do not open index.html directly. Linux/macOS: `sh start.sh`. The local server requires internet access for external quotes/market data. SQLite database is created automatically from schema.sql.

## Provider setup
Create and obtain approval for a ChangeNOW business/affiliate account: https://changenow.io/program-affiliate . Set CHANGENOW_API_KEY in .env (never publish). Start with ENABLE_SWAPS=0. Verify asset list, quote, and wallet validation responses against your account. Fixed rates require separate provider approval; ENABLE_FIXED=1 only after testing. ENABLE_SWAPS=1 permits real order creation and must not be used before operational/compliance review. Binance uses the public data-api.binance.vision endpoint with no secret. Market prices are reference prices only. Provider estimates include provider-defined pricing; itemized fee data is not implemented. Revenue/commissions should be reconciled against provider statements, not inferred from user amounts.

## Admin
Generate a unique long password and base32 TOTP secret with `python -c "import secrets,base64; print(secrets.token_urlsafe(24)); print(base64.b32encode(secrets.token_bytes(20)).decode())"`. Configure ADMIN_PASSWORD and ADMIN_TOTP_SECRET. Add the secret manually to an authenticator as a time-based 6-digit token. Visit /admin. Admin is single-role with one-hour in-memory sessions, not a multi-role IAM solution. Asset controls are a local deny list; only assets returned by the provider can be used. Provider credentials remain environment-only. Do not share .env or swap.db. 

## Integration endpoints
GET /api/config, /api/assets, /api/market, /api/order?id=private-id; POST /api/quote (from/to as ticker:network, amount, fixed); POST /api/create (same plus address, refund, memo, refundMemo, accepted, nonce). Admin POST /api/login, /api/admin/logout, /api/admin/assets; GET /api/admin. Provider endpoints: /v2/exchange/currencies, /v2/exchange/estimated-amount, /v2/validate/address, /v2/exchange, /v2/exchange/by-id. Provider owns deposit monitoring, conversion and payout; the worker polls status. No local custody or private signing keys. QR is address-only, amount and memo displayed separately. Provider validation unsupported on some networks; those orders fail closed.

## Deployment and required hardening
Deploy behind HTTPS reverse proxy on a private backend listener, set PUBLIC_ORIGIN to exact HTTPS origin, restrict file permissions, back up encrypted DB, protect secrets with a vault, and configure process supervision. Python built-in HTTP server is for local integration testing; replace with hardened production serving stack. SQLite is single-node; migrate to managed relational DB before scaling. Add independent reconciliation, provider webhook authentication, retries with durable idempotency and provider-side search by userId for ambiguous creation failures; attempts table prevents automatic duplicate submission but does not recover remote orphan orders. Add compliance gating, jurisdiction restrictions, legal review, verified operator contact, provider-approved refund handling, full RBAC, audit retention, alerting, independent security review, transactional tests and real provider sandbox/low-value supervised tests. Confirm provider response schemas, supported memo requirements and fixed quote expiration behavior before any launch. Do not enable real orders until all gates pass. The current UI does not implement itemized fees, countdown, configurable margin/limits, revenue reporting, customer accounts or ticketing. Policy pages are drafts. History is local only. Market and provider errors fail visibly, not by inventing rates.

## Research references
- https://simpleswap.io/faq — fixed/floating flows
- https://swapzone.io/ — quote comparison and tracking inspiration (multi-provider comparison not implemented)
- https://changenow.io/how-it-works — provider deposit and payout workflow
- https://changenow.io/program-affiliate — v2 create payload and partner API
- https://support.changenow.io/hc/en-us/articles/22686695418396-Integration-Transaction-management-and-troubleshooting — provider fixed-rate approval, memo and validation limitations
- https://developers.binance.com/en/docs/products/spot/rest-api — public market API

## Binance market preview
If CHANGENOW_API_KEY is absent, the app loads active Binance Spot USDT markets and calculates reference cross-rates from public prices. No network availability, executable quotes, fees, deposits or payouts are implied. The wallet step is a non-transactional preview. Live Binance custody/conversion/payout integration is not implemented. Keep ENABLE_SWAPS=0. Upload server.py and public/app.js to the existing repository to trigger Railway redeployment.
