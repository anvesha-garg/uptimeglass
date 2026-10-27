# UptimeGlass

![CI](https://github.com/anvesha-garg/uptimeglass/actions/workflows/ci.yml/badge.svg)

A website uptime and performance monitoring platform (a mini Better Stack).
Add URLs, and UptimeGlass checks them on a schedule, tracks uptime, latency and
SSL expiry, opens incidents, sends alerts, and shows a live dashboard and public
status pages. The UI uses a liquid glassmorphism design.

> Status: under construction. Built phase by phase with a pull request for every change.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Redis
- **Frontend:** React, TypeScript, Vite, hand-written CSS, Recharts, Framer Motion
- **AI (optional):** Groq API
- **Tooling:** Docker Compose, GitHub Actions, pytest, ruff, pre-commit

## Quick start (Windows, CMD)

You need Docker Desktop, Python 3.12, Node, and Git.

```
git clone https://github.com/anvesha-garg/uptimeglass.git
cd uptimeglass
copy .env.example .env
docker compose up -d --wait
```

This starts PostgreSQL and Redis. The app itself arrives in the next phases.

## Project structure

```
backend/    FastAPI app, tests (from Phase 1)
frontend/   React app (from Phase 6)
docs/       Architecture notes (from Phase 13)
.github/    CI workflow, issue and PR templates
```

## Roadmap

The project is built in 14 phases, from foundation to deployment.
This section will be filled in as phases are merged.

currently in the Phase 5 of building-
## License

To be added.
