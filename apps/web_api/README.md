The web API stack lives here.

- `api/` contains FastAPI entrypoints, dependencies, and routers.
- `services/` contains API-only service modules.
- `workers/` contains Dramatiq workers used by API-triggered jobs.

This layout keeps custom web functionality grouped under one namespace, which
reduces rebase friction when pulling upstream CLI changes.
