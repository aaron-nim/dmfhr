# DMF HR (dmfhr) — Documentation

Project docs for the **DMF fork of [Horilla](https://github.com/horilla-opensource/horilla)** and its
integration with **OpenIAM (dmfiam)**. These pages cover *our* customizations, environments, and
operations — not general Horilla usage (see the root `README.md`, `docker.md`, and
`horilla_api/README_API_DOCS.md` for upstream).

## How these docs are organized (Diátaxis)
Each page does exactly one job:

| Type | Answers | Pages |
|---|---|---|
| **Runbooks / How-to** | "How do I do X right now?" | [runbooks/](runbooks/) |
| **Reference** | "What is X exactly?" | [architecture.md](architecture.md), [deployment-and-environments.md](deployment-and-environments.md) |
| **Decisions (ADRs)** | "Why is it this way?" | [decisions/](decisions/) |
| **Tutorial** | "Teach me from zero" | Local setup (TODO) |

## Conventions
- **Docs live in the repo** and are reviewed in the same PR as the code change.
- **Update docs with the change.** If a PR touches deploy, models, or an ops procedure, update the doc in the same PR.
- **No secrets in docs.** Reference where a credential lives (`.env`, the host, GitHub Actions secrets,
  OpenIAM's credential store) — never paste the value.
- Keep pages **short and single-purpose**; link instead of repeating.
- We're a **fork** — clearly mark DMF-specific behavior vs. upstream Horilla.

## Index
- [architecture.md](architecture.md) — systems, environments, the identity/domain model
- [deployment-and-environments.md](deployment-and-environments.md) — branches → servers, deploy, rollback
- [issues-resolved-2026-07.md](issues-resolved-2026-07.md) — what/why/how of the July 2026 fixes
  (objectives permission, prod hardening, Postgres migration, scheduler connection exhaustion)
- **Runbooks**
  - [runbooks/reactivate-blocked-user.md](runbooks/reactivate-blocked-user.md)
  - _next:_ deploy-to-staging, reset-passwords, renew-dmfiam-cert
- **Decisions**
  - [decisions/0001-archive-persists-user-is-active.md](decisions/0001-archive-persists-user-is-active.md)
- **Related (outside `docs/` for now)**
  - OpenIAM ↔ Horilla connector design: `~/.claude/plans/openiam-horilla-connector-plan.md` (TODO: move into `docs/`)

## Owner
_TBD — assign a docs owner and add them here._
