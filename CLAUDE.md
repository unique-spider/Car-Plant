# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

CarPlant is a single-service Flask web app for managing a car manufacturer's sales-to-production pipeline: dealerships place orders, factory workers move cars through assembly sections, QC logs/resolves issues, and managers oversee everything. There is no frontend build step, API layer, or JS framework — server-rendered Jinja2 templates + Bootstrap 4 + vanilla JS/CSS.

The entire application logic lives in one file, `app.py` (~1480 lines): DB schema, connection handling, auth, and all routes. `config.py` loads settings from environment variables (via `.env`).

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY and DB_* values
python app.py           # dev server on :5000 with debug=True
```

There is no separate migration/seed command — `init_db()` runs automatically at import time (inside `with app.app_context(): init_db()` near the top of `app.py`) and issues `CREATE TABLE IF NOT EXISTS` for every table plus a one-time seed of the six `PRODUCTION_SECTION` rows. Just having valid `DB_*` env vars and starting the app is enough to get a working schema.

Production runs via gunicorn (see `Procfile` / `railway.toml`):
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```
Note `--workers 1`: the app is not verified safe for multiple worker processes (in particular `init_db()` running redundantly on each worker boot, and per-request `g.db` connection reuse). Keep it single-worker unless that's been reviewed.

There is no lint, test, or type-check tooling configured in this repo (no `pytest`, no linter config, no CI). Don't invent commands for these — verify changes by running the app and exercising the affected route/template in a browser.

## Database

MySQL, accessed via `pymysql` with `DictCursor` (rows come back as dicts, e.g. `row["Order_ID"]`). Table/column names are `UPPER_SNAKE_CASE` — this is deliberate schema style, keep it consistent when adding tables/columns.

Core tables and relationships (all defined inline in `init_db()` in `app.py`):
- `DEALERSHIP` → `USER` (salespeople/factory workers/managers, `Role` enum) and `CUSTOMER` belong to a dealership.
- `MODEL` → `VARIANT` (a sellable trim with `Cost`) → `PART`/`VARIANT_PART` (bill of materials — defined but not yet used by any route).
- `ORDER_TABLE`: a customer's order for a variant, placed by a salesperson. `Status`: `pending → accepted → in_production → completed → delivered` (plus `cancelled`, `returned` used ad hoc by the order-edit UI, not in the enum's `ON UPDATE`/`DEFAULT` but accepted by app logic).
- `CAR_PRODUCTION`: one physical car being built for an order. `SECTION_PROGRESS` tracks that car's progress through each `PRODUCTION_SECTION` (Body Shop, Paint Shop, Engine Assembly, Trim and Chassis, Final Assembly, Quality Inspection — seeded in that order, and section completion order follows `Section_ID ASC`), each row assigned to one `USER` (factory worker).
- `ISSUE_LOG`: QC issues raised against a `CAR_PRODUCTION` row; a car can't move to `PRODUCED_CAR` while it has an open issue.
- `PRODUCED_CAR`: a car that has finished all sections with no open QC issues — this is the terminal "done" record, created by whichever of `factory_complete_section` or `qc_resolve` happens to close out the last blocker.

**Known gap:** `COMPLAINTS` is queried/inserted by the `/complaints*` routes and the manager dashboard, but no `CREATE TABLE COMPLAINTS` exists in `init_db()`. Those routes will fail against a fresh database until a migration for that table (with at least `Complaint_ID, Order_ID, Customer_ID, Description, Status, Priority, Created_At, Resolved_At, Resolution_Notes, Assigned_To`) is added — check for this before assuming complaint features work end-to-end. Similarly, `account_settings()` selects `USER.Created_At`, which also isn't in the `USER` schema.

`setup_issue_log.py` is a standalone legacy script (uses `mysql.connector`, not `pymysql`) that predates `init_db()`'s auto-creation of `ISSUE_LOG`. It's redundant with app startup and not part of the run path — don't wire it into anything new.

## Request/data-access conventions

- All DB access goes through the two helpers defined near the top of `app.py`:
  - `query_db(sql, args=(), one=False)` — SELECTs, returns a list of dicts (or one dict/`None` if `one=True`).
  - `execute_db(sql, args=())` — INSERT/UPDATE/DELETE, auto-commits and returns `cur.lastrowid`; rolls back and re-raises on `pymysql.Error`.
  - Always use `%s` placeholders with a tuple of args — never f-string user input into SQL. (The one exception, `update_complaint`'s dynamic `SET` clause, builds column *names* from a fixed internal dict, not user input, and still parameterizes values.)
- Per-request connection lives on `g.db`, created by `get_db()` and closed in the `teardown_appcontext` handler `close_db`. `get_db()` pings and reconnects if the connection was dropped — don't add your own connection management in a route.
- Auth is session-based (`session["user_id"]`, `session["role"]`, `session["dealership_id"]`), no tokens/JWT. Two decorators gate routes:
  - `@login_required` — any authenticated user.
  - `@role_required("manager", ...)` — one of the listed roles. Roles are exactly `salesperson`, `factory_worker`, `manager` (matches the `USER.Role` enum).
  - A few routes (`qc_dashboard`, `qc_raise`, `qc_resolve`) check `session.get("role")` manually instead of using the decorator — follow that inline pattern if you touch those routes, or better, migrate them to `@role_required` if you're already editing them.
- Passwords are stored and compared as **plaintext** (`WHERE Email = %s AND Password = %s`, direct string equality in account settings) — this is existing behavior, not a pattern to extend elsewhere in the app.
- Manager routes frequently double as an "admin view" of a lower role's page rather than having separate manager-only templates — e.g. `salesperson_dashboard`/`salesperson_orders` are decorated `@role_required("salesperson", "manager")` and branch internally on `session.get("role") == "manager"` to show all-dealership data instead of just the current user's. Follow this pattern (shared route + `is_manager` branch) rather than duplicating routes/templates when adding a manager view of an existing worker-facing page.

## Adding a route/page

1. Add the `@app.route(...)` + `@role_required(...)`/`@login_required` handler in the relevant section of `app.py` (sections are marked with `# ──` banner comments: Auth, Salesperson, Factory Worker, Quality Control, Manager, Manager Employee Management, Complaint Management, Order Management, Account Settings).
2. Add a template under `templates/`, following the existing layout: role-specific pages live in `templates/<role>/`, shared/cross-role pages sit flat in `templates/` (e.g. `complaints.html`, `account_settings.html`).
3. Extend `templates/base.html` (`{% block content %}`, `{% block title %}`, `{% block page_title %}`) and add a sidebar nav entry gated on `session.get('role')` if the page needs one.
4. New tables/columns go into the `schema_sql` string inside `init_db()` in `app.py` — there's no separate migrations directory or tool.

## Frontend

- Templates extend `templates/base.html`, which pulls in Bootstrap 4.6 and jQuery from CDN plus local `static/css/style.css` and `static/js/main.js` — no bundler, no npm.
- Dark/light theme is a `data-theme="dark"` attribute on `<html>`, toggled client-side and persisted in `localStorage`; if you add new UI, make sure new CSS respects `[data-theme="dark"]` overrides in `style.css` rather than assuming light mode.
- Flash messages (`flash(message, category)`) auto-dismiss after 4s via `static/js/main.js`; category maps to a `flash-<category>` CSS class (`success`, `danger`, `warning`, `info`).
