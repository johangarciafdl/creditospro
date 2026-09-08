# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Task Observer skill (always active)

Before the first tool call of any session — and before writing or proposing a plan, not merely before executing one — invoke the `task-observer` skill (`.claude/skills/task-observer/SKILL.md`) and run its Session Start Protocol (storage check, frontmatter scan, review trigger). Any turn that will involve a tool call counts; do not skip this because the opening request looks simple.

After completing each task, check the observation records written this session and report a one-line summary (ids and titles, or "none logged and why").

The task-observer workspace for this project is pinned to the stable Claude Code project-identity directory (not this repo, so it survives worktrees/clones):
`C:\Users\johan\.claude\projects\c--Users-johan-Downloads-CreditosPro-DEPLOY\skill-observations\`

- Observation log: `...\skill-observations\observation-log\`
- Cross-cutting principles: `...\skill-observations\cross-cutting-principles.md`
- Staging: `...\skill-updates\` (manifest at `...\skill-updates\PENDING.md`)

Never resolve these paths from the current working directory.

## Project overview

CreditosPro is a multi-tenant loan/collections management system (Spanish-language UI) built with FastAPI + SQLAlchemy, server-rendered with Jinja2 templates, and gated by a per-machine license system. It's distributed as a licensed product to multiple companies ("empresas"), each running their own deployment/database, plus a WhatsApp bot for payment reminders and a PWA for offline collector use.

## Commands

Windows dev environment; a `.venv` already exists at the repo root.

```powershell
# Activate venv
.\.venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Run the app (auto-opens browser at http://127.0.0.1:8000)
python run.py
# or directly:
python -m app.main
# or via uvicorn with reload:
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test file / test
pytest tests/test_cobros_race_condition.py
pytest tests/test_cobros_race_condition.py::test_aplicar_cobro_atomico_rechaza_si_otra_tx_ya_escribio

# Lint (ruff config lives in pyproject.toml)
ruff check .

# DB migrations (Alembic)
alembic upgrade head
alembic revision -m "descripcion"
```

`tests/conftest.py` sets required env vars (`DATABASE_URL=sqlite:///:memory:`, `SECRET_KEY`, `AUTO_CREATE_TABLES=0`, etc.) before anything else imports, so tests don't need a `.env` file. Some integration tests (`tests/test_integration.py`) build their own file-based SQLite DB and a real license file — read that fixture before changing license or middleware behavior.

Environment variables are documented in `.env.example` — copy it to `.env` for local runs. Never hardcode `DATABASE_URL` or `SECRET_KEY`; the app refuses to start without them (see `app/database.py` and `app/main.py`'s `lifespan`).

## Architecture

### Multi-tenancy model

Every business table (`Empresa`, `Usuario`, `Zona`, `Cliente`, `Prestamo`, `Cuota`, `Cobro`, `AuditLog`, …) carries an `empresa_id` foreign key, and uniqueness constraints are scoped per-empresa (e.g. `uq_cliente_empresa` on `(empresa_id, cedula)`), not global. There is no cross-tenant query path in normal application code — every repository/router query filters by `empresa_id` derived from the authenticated user's session.

Optional defense-in-depth: Postgres Row-Level Security. `app/database.py` sets a session GUC (`app.empresa_id`) via `set_tenant_context()` and a `after_begin` SQLAlchemy event, but it only fires when `ENABLE_DATABASE_RLS=1` **and** the DB is Postgres (RLS is inert on SQLite). The actual policies live in `rls_policies.sql` and must be applied and tested against a non-`BYPASSRLS` role before enabling the flag in production — see the warning in `.env.example`.

### App composition (`app/main.py`)

FastAPI app with a stack of custom middleware, order matters (outermost first as registered):
`LicenseMiddleware` → `CSRFMiddleware` → `InMemoryRateLimitMiddleware` → `BodySizeLimitMiddleware` → `SecurityHeadersMiddleware` → CORS → `SessionMiddleware` → `AuditMiddleware` → `RequestIDMiddleware`.

Routers are mounted per feature under `app/routers/` (`auth`, `registro`, `selector`, `license_router`, `dashboard`, `clientes`, `prestamos`, `cobros`, `zonas`, `reportes`, `whatsapp`, `pwa`), each owning its own URL prefix. `lifespan()` validates required env vars, calls `init_db()` (idempotent `create_all`, skippable via `AUTO_CREATE_TABLES=0`), seeds demo data, and starts the background scheduler (`app/services/scheduler.py`) for WhatsApp reminders.

### Auth & sessions

Session state is a JWT stored in an HttpOnly cookie (`cp_session`), not server-side sessions — see `get_current_user()` in `app/routers/auth.py`. The JWT carries `sub` (user id) and `empresa_id`; on every request `set_tenant_context(db, empresa_id)` is called before querying, and a `jti` blacklist (`app/utils/token_blacklist.py`) supports logout/revocation. 2FA (TOTP + backup codes) is supported per-user (`app/utils/two_factor.py`). Role checks (`admin`/`superadmin`/`cobrador`) and per-zone data visibility go through `app/utils/zone_permissions.py` — non-admin users only see zones they're assigned to (`usuario_zonas` join table, max 5 zones per user).

### Licensing (separate from application auth)

Licensing is a single per-*empresa* commercial activation key — there is no per-machine/hardware-fingerprint licensing (that system existed historically and was removed; don't reintroduce it). `Empresa.activation_key_hash`/`activation_key_hint` store only the hash (see `app/utils/company_activation.py`); `scripts/crear_clave_empresa.py --empresa-id <id>` generates/rotates one. `POST /license/activate` (`app/routers/license_router.py`) checks a submitted key against that hash and sets `activated_empresa_id` in the session — `app/utils/license_middleware.py` blocks every route except a small public allowlist (`/`, `/inicio`, `/license/activar`, `/license/activate`, `/license/status`, `/health`, `/static/*`) until that session value is present. This is a session-level gate, not tied to a device.

### Financial correctness

All money math goes through `Decimal` with explicit rounding (`app/utils/money.py`: `money()`/`money_int()`, `ROUND_HALF_UP`, quantized to cents) — never use `float` for currency. `app/services/prestamo_service.py.calcular_cuotas()` computes installment schedules and pushes any rounding remainder onto the last cuota so installments always sum exactly to `total_pagar`.

Payments (`Cobro`) update `Cuota.valor_pagado` through `aplicar_cobro_atomico()` in `app/routers/cobros.py`: a conditional `UPDATE ... WHERE valor_pagado == <value read>` (optimistic concurrency), not `SELECT ... FOR UPDATE`, so it works identically on SQLite (dev) and Postgres (prod) and rejects the loser of a race with `rowcount == 0` rather than corrupting state. `tests/test_cobros_race_condition.py` and `tests/test_cobros_concurrent_load.py` are the reference for this pattern — replicate it for any other concurrent read-modify-write on financial fields.

### Database

`DATABASE_URL` decides the backend: `sqlite://...` for local dev (auto-detected via `IS_SQLITE` in `app/database.py`), Postgres in production (`postgres://` is normalized to `postgresql://`). SQLite doesn't support `with_for_update()` — code that needs row locking guards it behind `IS_SQLITE`. Schema changes go through Alembic (`alembic/versions/`); `Base.metadata.create_all()` in `init_db()` is only for bootstrapping new/empty databases, not for evolving existing schemas.

### Deployment

Deployed to Railway (`Procfile`, `nixpacks.toml`, `Dockerfile` all point to `start.sh`, which runs `uvicorn app.main:app` with `$PORT`). The `Dockerfile` runs as a non-root user and defines a `/health` healthcheck.

## Root-level scripts and docs

[`README.md`](README.md) is the end-user/operator-facing guide (installation, daily use, mobile/PWA access, offline mode, syncing between machines, licensing) — read it for anything touching those topics rather than re-deriving them from code. `scripts/` holds standalone maintenance CLI tools (backups, index creation, one-off data cleanup/migration scripts, ElRusso-specific setup) — none of them are imported by `app/`; each resolves its own path to the repo root and loads `.env` independently, so they only need to be run as `python scripts/<name>.py` from the repo root, not installed anywhere. The root-level `.bat`/`.ps1` files (`Iniciar CreditosPro.bat`, `crear_acceso_directo.bat`, `setup_inicio_automatico.bat`, `copiar_a_usb.*`, `sync_archivos.*`, `BUILD.bat`) are Windows operator tooling, not developer docs — they're not required reading for code changes.
