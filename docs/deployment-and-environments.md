# Deployment & environments

## Branch → environment
| Branch | Role |
|---|---|
| `dev` | integration / latest work (not auto-deployed) |
| `staging` | → **staging.dmfhorilla.ch** (auto-deploys on push) |
| `main` | → **production** (`dmfhorilla.ch`) — renamed from `1.0` on 2026-07-13; deploy is **manual** |

> `master` and `1.0` no longer exist. `dev`/`staging`/`main` were unified at `e0ad6a42`
> (2026-07-13) and production was deployed from `main` the same day.

## Staging (verified)
- **Host / layout:** staging host (address in the private ops notes — never in this public repo);
  app at `~/app`, virtualenv at `~/app/venv`, PostgreSQL. Served by **gunicorn** under **systemd** —
  service `horilla.service` (behind a web server that fronts `staging.dmfhorilla.ch`).
- **Auto-deploy:** push to `staging` → GitHub Actions **`.github/workflows/deploy-staging.yml`** → SSH →
  runs `~/deploy.sh`.
- **`~/deploy.sh`** does: `git pull --ff-only origin staging` → `pip install -r requirements.txt` →
  `makemigrations` → `migrate` → `collectstatic` → `sudo systemctl restart horilla.service`.
- **Manual deploy / redeploy:** SSH to the staging host and run `bash ~/deploy.sh`.
- **Note:** the repo **gitignores migration files**, so `deploy.sh` runs `makemigrations` on the server.

## Production (verified 2026-07-13)
- **Host / layout:** production host (address in the private ops notes — never in this public repo);
  app at `~/horilla`, python packages in `~/.local` (no venv), PostgreSQL. Served by **gunicorn**
  under **systemd** (`gunicorn.service`) behind nginx (`dmfhorilla.ch`).
- **Deploy: manual.** Sequence: `git fetch origin && git checkout main && git pull --ff-only` →
  `python3 manage.py migrate` → `python3 manage.py collectstatic --noinput` →
  `sudo systemctl restart gunicorn` → `sudo systemctl restart horilla-scheduler` →
  **verify** `systemctl is-active gunicorn horilla-scheduler`.
- Config lives in `~/horilla/.env` (`DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`).

## Background schedulers (REQUIRED service — since the scheduler-connection fix)
- gunicorn workers start **zero** APScheduler schedulers. **All background jobs** (leave reset,
  contract expiry, work records, auto payslips, shift rotation, notifications) run only in the
  dedicated **`horilla-scheduler.service`** (`manage.py run_schedulers` with
  `HORILLA_RUN_SCHEDULERS=1` set **in the unit, never in `.env`**).
- Unit template + install steps: [deploy/horilla-scheduler.service](deploy/horilla-scheduler.service).
- **Post-deploy check (mandatory, both envs):** `systemctl is-active horilla-scheduler` and
  `journalctl -u horilla-scheduler -n 20` shows "Background schedulers running".
- If the service is down, background jobs stop **silently** — this check is not optional.

## Rollback
- **Staging:** point the branch back and redeploy —
  `git push origin <previous_sha>:staging --force`, then re-run `deploy.sh`; or on the host
  `git checkout <sha> && bash ~/deploy.sh`.
- Always record the pre-deploy SHA before shipping so rollback is one command.

## Secrets (never in git or these docs)
- **App config / DB credentials:** `.env` on each host.
- **Deploy SSH keys / host secrets:** GitHub Actions repository **secrets** (`STAGING_SSH_*`).
- **dmfiam:** OpenIAM credential store + the manually-renewed TLS cert.

## Related runbooks
- [runbooks/reactivate-blocked-user.md](runbooks/reactivate-blocked-user.md)
