## Backend Instructions

These instructions apply to backend code under `backend/`.

## Backend Role

The backend owns API routes, application services, repositories, provider
interfaces, configuration, and orchestration of RAG pipeline steps.

The backend must stay backend-first. Do not introduce frontend, authentication,
multi-user workspace, full crawling, Playwright, or multi-agent workflow unless
explicitly requested and approved.

## Expected Structure

Prefer this structure when adding backend code, adapting names only when an
existing project pattern already exists:

- `api/`: FastAPI routes and route dependencies.
- `services/`: application services and workflow orchestration.
- `repositories/`: PostgreSQL persistence access.
- `providers/`: external provider interfaces and implementations.
- `schemas/`: Pydantic request, response, and pipeline schemas.
- `rag/`: focused RAG pipeline components when they are not better placed in
  services.
- `core/`: settings, configuration, logging setup, and shared errors.

Do not create all folders preemptively. Add only the folders needed by the
requested task.

## API Routes

- Routes must be thin.
- Routes validate request shape, parse path/query/body parameters, and call
  services.
- Routes must not directly call OpenAI, Qdrant, trafilatura, PyMuPDF,
  python-docx, BeautifulSoup, or PostgreSQL queries.
- Routes must not contain business logic for chunking, retrieval, generation, or
  evaluation.
- Preserve existing API contracts unless the user explicitly approves a change.
- Prefer explicit response models.
- Keep error responses consistent with existing project conventions. If no
  convention exists yet, propose one before broad adoption.

## Services

- Services contain application logic and coordinate pipeline steps.
- Services depend on repositories and provider interfaces, not concrete external
  clients when avoidable.
- Services should accept and return explicit schemas.
- Keep services focused by workflow: ingestion, retrieval, generation,
  evaluation, and logging should not collapse into one large service.
- Generation services must consume retrieved context. They must not directly
  access parsers, vector stores, upload handlers, or repositories.

## Repositories

- Repositories handle database access only.
- Repositories must not call external AI providers or vector store providers.
- Repositories should expose methods in domain language, not leak SQL details to
  services.
- Do not change database schema or migrations without approval.
- If a task requires new persistence, propose the schema and migration approach
  first.

## Provider Interfaces

- Provider interfaces wrap external dependencies such as embedding models, LLMs,
  Qdrant, document extractors, and web extractors.
- External calls should happen through providers, not routes.
- Unit tests must mock provider interfaces.
- Provider implementations should read secrets and runtime configuration from
  environment-backed settings, never from hardcoded values.
- Do not call real external providers in unit tests.

## Configuration

- Use environment variables for secrets and runtime settings.
- Keep `.env.example` updated when adding new environment variables.
- Do not store secrets in code, tests, fixtures, logs, or docs.
- Prefer a central settings module if configuration grows beyond a few values.

## Errors And Logging

- Use explicit application errors for domain failures such as unsupported file
  type, invalid URL, blocked URL, insufficient context, provider failure, and
  indexing failure.
- Do not log API keys, raw secrets, authorization headers, or full uploaded
  document content.
- Log enough metadata to debug pipeline state: document id, source type, chunk
  count, retrieval method, and provider names where safe.

## Backend Tests

- Add focused tests for service logic and route behavior when backend behavior
  changes.
- Mock repositories and providers in unit tests.
- Do not require PostgreSQL, Qdrant, OpenAI, or real websites for unit tests.
- Read `../tests/AGENTS.md` before adding tests.