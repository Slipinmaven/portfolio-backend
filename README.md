# Portfolio backend

FastAPI backend for the portfolio platform. It provides authentication,
role-based content management, PostgreSQL persistence, Alembic migrations,
revision-aware page publishing, media processing, and public portfolio APIs.

The companion Next.js frontend is maintained in the
[portfolio-web repository](https://github.com/Slipinmaven/portfolio-web).

## Stack

- Python 3.12+
- FastAPI and Pydantic
- PostgreSQL 15+
- SQLAlchemy async and asyncpg
- Alembic
- Argon2id password hashing
- JWT access tokens and rotating refresh sessions
- Pillow, FFmpeg, and FFprobe
- unittest and FastAPI TestClient

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-database.txt
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS`, and media settings in
`.env`. `DATABASE_URL` must use the `postgresql+asyncpg://` driver.

Generate a signing key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create the database and apply migrations:

```powershell
python -m alembic -c alembic.ini upgrade head
python -m app.scripts.create_admin
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

- Swagger UI: `http://127.0.0.1:8001/docs`
- OpenAPI JSON: `http://127.0.0.1:8001/openapi.json`
- Health: `/api/v1/health`
- Database readiness: `/api/v1/ready`

`/api/v1/health` confirms that the process is responsive.
`/api/v1/ready` performs a database query and returns HTTP 503 when PostgreSQL
is unavailable.

## Configuration

The complete safe template is [`.env.example`](.env.example). Never commit a
populated `.env`.

| Prefix | Purpose |
| --- | --- |
| `DATABASE_*` | PostgreSQL connection and pool behavior |
| `JWT_*`, `ACCESS_TOKEN_*`, `REFRESH_SESSION_*` | Authentication and session lifetimes |
| `SESSION_*`, `TRUSTED_DEVICE_*`, `LOGIN_FAILURE_*` | Session security and login limits |
| `CORS_ORIGINS` | Exact browser origins allowed to call the API |
| `MEDIA_*` | Upload storage, limits, processing, and warning thresholds |
| `LOG_*` | Log level, directory, and retention |

Use HTTPS and `ENVIRONMENT=production` in production. Supply secrets through
the hosting provider's secret manager.

## Application structure

```text
app/
├── application/                 Use cases and application DTOs
├── core/                        Configuration and logging
├── infrastructure/
│   ├── database/                Models, repositories, sessions
│   └── security/                Password, JWT, and security helpers
└── presentation/
    ├── api/                     FastAPI routes
    ├── dependencies/            Authentication and service dependencies
    ├── middleware/              Request logging and error mapping
    └── schemas/                 Pydantic HTTP schemas
```

Routes translate HTTP input to application DTOs and results to HTTP schemas.
Use cases coordinate transactions and repositories own persistence queries.

## API overview

Routes are mounted below `/api/v1`.

| Area | Main paths |
| --- | --- |
| Health | `/api/v1/health`, `/api/v1/ready` |
| Auth | `/api/v1/auth/*` |
| Users | `/api/v1/users/*` |
| Projects | `/api/v1/projects/*` |
| Posts | `/api/v1/posts/*` |
| Pages | `/api/v1/pages/*` |
| Media | `/api/v1/media/*` |
| Resources | `/api/v1/resources/*` |
| Navigation | `/api/v1/navigation/*` |
| Categories | `/api/v1/categories/*` |
| Tags | `/api/v1/tags/*` |
| Site settings | `/api/v1/site-settings/*` |

## Authentication

- Access JWT lifetime defaults to 15 minutes.
- Refresh sessions default to seven absolute days and 60 idle minutes.
- Remembered devices default to 30 days.
- Refresh and trusted-device credentials are stored as hashes.
- Refresh, logout, and device operations require a matching browser Origin.
- Password changes revoke the account's active sessions and devices.
- Browser clients keep access tokens in memory.

Protected endpoints use `get_current_user` and role dependencies from
`app/presentation/dependencies/auth.py`.

## Migrations

Before generating migrations, inspect model exports in
`app/infrastructure/database/models/__init__.py`.

```powershell
python -m alembic -c alembic.ini history
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini revision --autogenerate -m "describe change"
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini upgrade head --sql
python -m alembic -c alembic.ini downgrade -1
```

Always review generated migrations. Alembic may not detect renames, data
transformations, custom constraints, or operational data requirements.
Back up production databases before applying migrations.

## Tests

```powershell
python -m unittest discover -s tests
```

Examples of focused checks:

```powershell
python -m unittest discover -s tests -p "test_post_routes.py"
python -m unittest discover -s tests -p "test_page_routes.py"
python -m unittest discover -s tests -p "test_media.py"
python -m unittest discover -s tests -p "test_auth_sessions.py"
```

Database-dependent tests require a reachable PostgreSQL database.

## Media

Local uploads default to `media/`. Set `MEDIA_DIRECTORY` to persistent
storage in deployment and include it in backups.

Video uploads require FFmpeg and FFprobe. The backend generates MP4 previews
and JPEG posters, persists processing jobs, and prevents deletion of
referenced media.

## Initial admin

After migrations:

```powershell
python -m app.scripts.create_admin
```

The script prompts for credentials and hides password input. Never pass
passwords as command-line arguments.

## Production deployment

This repository does not currently include a container or platform-specific
deployment manifest. A typical host needs:

1. PostgreSQL 15 or newer.
2. A persistent volume for `MEDIA_DIRECTORY`.
3. FFmpeg and FFprobe when video uploads are enabled.
4. Environment variables rather than a committed `.env`.
5. HTTPS and exact production frontend origins in `CORS_ORIGINS`.
6. Database migrations run against the target database before application
   rollout.
7. Persistent database, media, and log backups.

Set at least `ENVIRONMENT=production`, `DEBUG=false`,
`JWT_SECRET_KEY=<long-random-secret>`, and `CORS_ORIGINS=<exact-origins>`.
Apply migrations during a controlled deployment and use a platform health check
for `/api/v1/health` plus a readiness check for `/api/v1/ready` if supported.

## Public API conventions

- JSON request and response bodies use Pydantic schemas.
- List endpoints use offsets and limits where pagination is supported.
- Authentication uses bearer access tokens.
- Refresh credentials are HttpOnly cookies.
- Public content routes expose only published content.
- Editor/admin routes require the appropriate backend role.
- Uploaded file paths are not private database IDs or credentials.

## Security and maintenance

- Never commit `.env`, credentials, signing secrets, refresh tokens, private
  keys, media uploads, logs, or database dumps.
- Use HTTPS and a random JWT secret of at least 32 bytes.
- Keep access tokens in memory in browser clients.
- Review migrations and back up PostgreSQL before production upgrades.
- Rotate secrets and revoke sessions through the supported API when required.
- Monitor `/api/v1/ready`, application logs, database capacity, and media
  storage capacity.

## GitHub workflow

See [GITHUB.md](GITHUB.md) for secret checks, migrations, tests, commits,
remote setup, and pushing to a public repository.
