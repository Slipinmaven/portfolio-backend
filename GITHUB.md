# GitHub workflow

Use this guide when this backend is maintained as a standalone public repository.

## Pre-push checklist

Before a push or pull request:

1. Confirm PostgreSQL and the migration state.
2. Run the backend test suite.
3. Review generated migrations.
4. Confirm `.env` and generated media/logs are untracked.
5. Review the diff for credentials or private host information.

```powershell
python -m unittest discover -s tests
python -m alembic -c alembic.ini current
git status
git diff --stat
git diff --name-only
```

Render SQL if a database is not available for migration validation:

```powershell
python -m alembic -c alembic.ini upgrade head --sql
```

## Ignore local files

The repository should ignore at least:

```gitignore
.venv/
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.pytest_cache/
media/
logs/
.vscode/
.DS_Store
Thumbs.db
*.log
```

Never commit a populated `.env`, database dump, uploaded media, runtime log,
private key, certificate, access token, refresh token, or password.

To stop tracking an already tracked secret or runtime file without deleting
the local copy:

```powershell
git rm --cached .env
git rm --cached -r media
git rm --cached -r logs
git commit -m "chore: remove local runtime files"
```

Only do this for files that were not required by source control.

## Create and push

Create an empty GitHub repository. If initializing locally:

```powershell
git init
git branch -M main
git add .
git diff --cached --stat
git diff --cached --name-only
git commit -m "feat: establish portfolio backend"
git remote add origin git@github.com:<owner>/<backend-repository>.git
git push -u origin main
```

HTTPS is also supported:

```powershell
git remote add origin https://github.com/<owner>/<backend-repository>.git
git remote -v
```

## Feature workflow

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/backend-change

# Make and test the change.
python -m unittest discover -s tests

git diff --stat
git status
git add app alembic tests README.md .env.example
git diff --cached --stat
git diff --cached --name-only
git commit -m "fix: describe the backend change"
git push -u origin feat/backend-change
```

Open a pull request and merge after tests and migration review.

## Migration updates

After pulling a migration:

```powershell
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
```

For production, back up PostgreSQL, review migration SQL and downgrade
behavior, apply migrations before incompatible application instances start,
and preserve uploaded media on persistent storage.
