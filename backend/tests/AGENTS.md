## Backend Test Instructions

These instructions apply to backend tests under `backend/tests/`.

Use pytest and keep tests scoped to backend behavior. Follow the project-wide
testing rules in `../../tests/AGENTS.md` when they apply.

## Boundaries

- Do not call real OpenAI APIs, LLM providers, embedding providers, websites,
  Qdrant, or PostgreSQL.
- Mock or fake providers, repositories, vector stores, and web extractors when
  backend code depends on them.
- Keep tests focused on the requested phase or behavior.

## Phase 1

- Health tests should verify app import, HTTP 200, exact JSON response, and JSON
  content type.
- Phase 1 tests must not require external infrastructure.
