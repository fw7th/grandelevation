# Solar Ordering Site — Project Spec

> **This file lives in this Project's knowledge.** Claude pulls from it
> automatically in any chat within this Project — no need to paste it.
> It is the source of truth, not any single conversation: keep it updated
> as decisions change, ideally at the end of each chat that changes
> something here, so the next chat starts accurate. If you ever start a
> *new* Project for this work, re-add this file there too — Project
> knowledge doesn't carry across Projects.

## What this is

An e-commerce site for solar equipment (panels, inverters, batteries,
charge controllers, mounts). The core domain challenge: components must be
electrically compatible based on **wattage, voltage, and current ratings**
— a calculation against the combination a customer is building (e.g. sum
of series-connected panel voltages must not exceed an inverter's max input
voltage), not a forbidden-pairs list.

## Who's involved

- **Me (developer):** Python/backend background, no prior frontend
  experience, uses neovim.
- **Brother:** site owner, co-manages products via an admin dashboard.
- **Customers:** browse, configure a compatible system, create an account,
  check out, view order history.

## Locked architecture decisions

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI | Developer's strength; async; fits serverless |
| Frontend | Jinja2 + htmx (not React/Next.js) | Zero JS-framework learning curve |
| Styling | Custom CSS, token-based (see Brand tokens) | No build step |
| ORM | SQLModel | Bridges Pydantic + SQLAlchemy, no duplicate schemas |
| Database | Postgres via **Neon** | Serverless-friendly; auth built custom, so no bundled extras needed |
| Dependency manager | **uv** | Fast, modern, replaces pip+venv |
| Hosting | **Vercel**, Python/FastAPI runtime | Developer has prior experience with this combo |
| Auth | `customer` + `admin` roles, custom-built in FastAPI | Brother + developer = admin |
| Payments | Stripe Checkout (hosted page) | Least frontend work to start |
| Inventory | **Excluded.** Brother sources on demand per order. | Deliberate scope cut |
| Email | **Excluded for now.** No transactional/confirmation emails. | Cost; revisit if needed |
| Compatibility engine | Pure Python module, no DB/HTTP dependency: specs in -> (is_valid, reasons) out | Unit-testable in isolation; the unique core logic |

### Brand tokens (Grand Elevation Solar)

From the brother's logo (black sprout + gold sun mark, no blue):

- Light: `--ink:#0A0A0A` `--bg:#FAF8F3` `--gold:#F2A623` `--gold-light:#FBDFA8` `--gold-deep:#E8651C` `--green:#3D5C3A` `--gray-mid:#6B6B6B` `--border:rgba(10,10,10,.1)`
- Dark (`html[data-theme="dark"]`): `--ink:#F4F1EA` `--bg:#14130F` `--gold:#F2A623` `--gold-light:#4A3A1A` `--gold-deep:#FFB648` `--green:#7FA87A` `--gray-mid:#9B968A` `--border:rgba(244,241,234,.12)`
- Type: display = Sora (700/800), body = Inter
- Logo mark: re-cropped from the source file to isolate just the sprout+sun icon (wordmark excluded), centered on a square canvas with verified clearance from the inscribed circle, then given a true alpha-masked circular crop (not just CSS `border-radius`). Used in nav/footer inside a thin dashed orbit ring with a slowly-orbiting dot, scaled per context (38px nav / 22px footer).
- A corner "ambient sun" background texture was tried and explicitly removed — don't re-add without being asked.

## Light/dark mode

Toggle is a small circular pill button in the nav (sun/moon icon swap),
next to "Sign in". Implementation: CSS variables only (no hardcoded
colors anywhere in the stylesheet), overridden under
`html[data-theme="dark"]`. JS sets `data-theme` on `<html>`, defaults to
`prefers-color-scheme` on load, no persistence (no localStorage — not
available in this environment, and not yet needed since there's no
backend session to store it in). When this gets merged into the real
FastAPI templates, persistence could move to a cookie or per-user setting
on the `User` model — not decided yet.

## Known platform caveats (Vercel + FastAPI)

1. **Serverless = stateless.** No in-memory cache or `/tmp` persistence; expect cold starts.
2. **DB connections must be serverless-friendly** -- Neon handles this, don't size a pool for a long-running process.
3. **Never auto-run migrations on startup** -- multiple instances can start independently. Run Alembic manually against `DATABASE_URL`.
4. Vercel's Python runtime expects a FastAPI instance named `app` at `api/index.py`. Real app code lives in `app/main.py`; `api/index.py` just re-imports it.
5. Server-rendered Jinja2/htmx (one app, one domain) avoids cross-domain cookie issues seen in split Next.js/FastAPI setups on Vercel.

## Architecture diagrams

Three were produced during system design (not re-embedded here -- regenerate on request):
1. **System context** -- browser <-> FastAPI app on Vercel <-> Postgres/Stripe. One app serves both frontend and backend.
2. **Order flow** -- component picks -> compatibility engine -> valid/invalid branch -> checkout.
3. **Module map** -- routers -> services/models -> templates, with `services/` deliberately decoupled from HTTP and templates so the compatibility engine stays unit-testable in isolation.

## Repo structure (as scaffolded)

```
solar-site/
├── api/index.py        # Vercel entrypoint shim, imports `app` from app/main.py
├── app/
│   ├── main.py           # Real FastAPI() app, routes mounted here
│   ├── models/            # SQLModel tables (Product, User, Order...) -- NOT BUILT
│   ├── routers/            # products.py, auth.py, cart.py, admin.py -- NOT BUILT
│   ├── services/            # Compatibility engine -- NOT BUILT
│   ├── templates/            # Jinja2 .html -- landing page not yet merged in
│   └── static/                 # CSS, images
├── tests/test_app_boots.py       # App boots, home renders, htmx round-trip, static files -- PASSING
├── alembic/                        # NOT INITIALIZED
├── .env.example
├── pyproject.toml / uv.lock
└── vercel.json                       # Untested against a real deployment
```

## Current status

**Backend skeleton:** boots locally via `uv run uvicorn app.main:app --reload`. Jinja2 rendering, one htmx round-trip (`POST /api/ping`), static files, 3 passing tests -- all confirmed working.

**Landing page** (`grand-elevation-landing.html`): built as a **standalone HTML file**, not yet merged into `app/templates/`. Self-contained, real brand tokens, light/dark toggle, circular logo with orbit ring (nav + footer), eyebrow pill badge, hero with ray-burst motif, three value props (compatibility checking / on-demand sourcing / order history), closing CTA, footer.

**Not yet done:** merging the landing page into the real FastAPI project (swap hardcoded anchors/asset paths for `{{ url_for(...) }}` and real routes), plus everything below.

## What's not built yet (by section, for future chats)

- **B. Domain modeling** -- Product/spec schema per category, Order/Cart/OrderItem, User/Role.
- **C. Compatibility engine** -- rule definitions, validation function, unit tests.
- **D. Backend API/routes** -- product listing, cart + live compatibility check endpoint, auth, admin CRUD, Stripe session + webhook.
- **E. Frontend templates** -- integrate the landing page; then product browsing, cart/configurator (main htmx-heavy page), checkout, admin dashboard, customer account pages.
- **F. Deployment/ops** -- real Vercel deploy, Neon provisioning, Alembic workflow, Stripe webhook (needs a public URL, likely Stripe CLI for local forwarding).

## How to work across chats

1. New chat per section (B-F), inside this Project. This file is already
   available automatically — no pasting needed.
2. If a section has its own spec file by then, add that to Project
   knowledge too (or paste it for that one chat if it's still in flux).
3. After a chat changes anything in this file's scope, update this file
   directly so the next chat starts accurate.
