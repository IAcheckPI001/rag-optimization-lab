# Phase 1: Backend Skeleton

## Goal

Create the initial FastAPI backend skeleton for RAG Optimization Lab.

This phase establishes the backend package structure, application entrypoint,
basic configuration, initial data contracts, provider interfaces, and test
setup.

Do not implement actual RAG processing or external infrastructure integration in
this phase.

---

## Fixed Phase Decisions

* Backend root: `backend/`
* Application package: `backend/app/`
* Framework: FastAPI
* Test framework: pytest
* Dependency configuration: `backend/pyproject.toml`
* Health endpoint: `GET /health`
* Health response: `{"status": "ok"}`
* API versioning is deferred.
* Database migration tooling is deferred.
* Provider implementations are deferred.
* RAG behavior is deferred.

---

## Allowed Phase Dependencies

Runtime:

* `fastapi`
* `uvicorn`
* `pydantic`
* `pydantic-settings`

Testing:

* `pytest`
* `httpx`, when required by FastAPI test utilities

Do not add parser, database, vector-store, LLM, crawling, retrieval, or
evaluation dependencies in this phase.

---

## Target Structure

Create only the packages and files required by Phase 1.

```text
backend/
├── AGENTS.md
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py
│   │
│   ├── services/
│   │   └── __init__.py
│   │
│   ├── repositories/
│   │   └── __init__.py
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── extraction/
│   │   │   ├── __init__.py
│   │   │   └── interface.py
│   │   ├── embedding/
│   │   │   ├── __init__.py
│   │   │   └── interface.py
│   │   ├── vector_store/
│   │   │   ├── __init__.py
│   │   │   └── interface.py
│   │   └── llm/
│   │       ├── __init__.py
│   │       └── interface.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── source.py
│   │   ├── document.py
│   │   ├── retrieval.py
│   │   └── generation.py
│   │
│   ├── rag/
│   │   └── __init__.py
│   │
│   └── core/
│       ├── __init__.py
│       ├── config.py
│       └── errors.py
│
├── tests/
│   ├── AGENTS.md
│   ├── __init__.py
│   ├── conftest.py
│   └── test_health.py
│
├── pyproject.toml
├── .env.example
└── README.md
```

Empty package boundaries are acceptable in this phase. Do not create speculative
service, repository, or RAG implementation classes.

---

## Application Entrypoint

Create `app/main.py`.

Requirements:

* Provide `create_app()`.
* Export `app = create_app()`.
* Load the application name from central settings.
* Register the root API router.
* The application must import and start without external infrastructure.

Expected command from `backend/`:

```bash
uvicorn app.main:app --reload
```

---

## API Router

Create:

* `app/api/router.py`
* `app/api/routes/health.py`

`app/api/router.py` aggregates application routes.

`app/main.py` registers the aggregated router.

---

## Health Endpoint

Implement:

```text
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Requirements:

* Return HTTP 200.
* Use `HealthResponse` as the explicit response model.
* The endpoint checks only application availability.

---

## Configuration

Create `app/core/config.py` with an environment-backed settings model.

Minimum settings:

* `app_name: str`
* `app_env: str`
* `log_level: str`

Add matching entries to `.env.example`:

```env
APP_NAME=RAG Optimization Lab
APP_ENV=development
LOG_LEVEL=INFO
```

Do not add provider, database, Qdrant, embedding, or chunking settings until
their implementation phases.

---

## Base Application Error

Create `app/core/errors.py`.

Minimum contract:

```python
class ApplicationError(Exception):
    pass
```

Do not introduce a broad error hierarchy before concrete use cases require it.

---

## Initial Schemas

The schemas in this phase establish terminology and data boundaries. They do not
require implementation logic.

### `HealthResponse`

* `status: Literal["ok"]`

### `SourceType`

Values:

* `pdf`
* `docx`
* `url`

### `SourceStatus`

Values:

* `pending`
* `processing`
* `completed`
* `failed`

### `SourceCreateResponse`

* `source_id: str`
* `status: SourceStatus`
* `message: str | None = None`

### `SourceDetailResponse`

* `source_id: str`
* `source_type: SourceType`
* `status: SourceStatus`
* `source_uri: str | None = None`
* `original_filename: str | None = None`

### `RawDocumentUnit`

* `document_id: str`
* `source_id: str`
* `source_type: SourceType`
* `source_uri: str | None`
* `content: str`
* `page_number: int | None = None`
* `section: str | None = None`
* `metadata: dict[str, object]`

### `CleanDocumentUnit`

* `document_id: str`
* `source_id: str`
* `source_type: SourceType`
* `source_uri: str | None`
* `content: str`
* `page_number: int | None = None`
* `section: str | None = None`
* `metadata: dict[str, object]`

### `DocumentChunk`

* `chunk_id: str`
* `document_id: str`
* `source_id: str`
* `source_type: SourceType`
* `source_uri: str | None`
* `content: str`
* `chunk_index: int`
* `page_number: int | None = None`
* `section: str | None = None`
* `metadata: dict[str, object]`

`chunk_index` is zero-based.

The stable `chunk_id` strategy is deferred to the chunking phase.

### `RetrievedContext`

* `chunk_id: str`
* `document_id: str`
* `content: str`
* `score: float`
* `rank: int`
* `retrieval_method: str`
* `source_type: SourceType`
* `source_uri: str | None`
* `page_number: int | None = None`
* `section: str | None = None`
* `metadata: dict[str, object]`

`rank` is one-based.

### `QueryRequest`

* `question: str`
* `top_k: int = 5`

Validation:

* `question` must not be blank.
* `top_k` must be greater than zero.

### `Citation`

* `chunk_id: str`
* `document_id: str`
* `source_uri: str | None`
* `page_number: int | None = None`
* `section: str | None = None`
* `label: str | None = None`

The final public citation format is deferred to the generation phase.

### `QueryResponse`

* `answer: str`
* `citations: list[Citation]`
* `contexts: list[RetrievedContext]`
* `insufficient_context: bool`

---

## Initial Provider Interfaces

Use Python `Protocol`, unless an established repository pattern requires
abstract base classes.

### Extraction

Create:

* `PDFExtractor`
* `DocxExtractor`
* `WebExtractor`

Expected output:

```python
list[RawDocumentUnit]
```

Suggested inputs:

* PDF and DOCX extractors receive a file path.
* Web extractor receives a URL.

### Embedding

Create `EmbeddingProvider`.

Suggested method:

```python
def embed_texts(self, texts: list[str]) -> list[list[float]]:
    ...
```

The output order must correspond to the input order.

### Vector Store

Create `VectorStore`.

Suggested methods:

```python
def upsert(...) -> None:
    ...

def search(...) -> list[RetrievedContext]:
    ...
```

Collection configuration, vector size, distance metric, and payload schema are
deferred to the indexing phase.

### LLM

Create `LLMProvider`.

Suggested method:

```python
def generate(
    self,
    question: str,
    contexts: list[RetrievedContext],
) -> str:
    ...
```

Prompt and citation-generation contracts are deferred to the generation phase.

---

## Services, Repositories, and RAG Packages

Create these as importable package boundaries only:

* `app/services/`
* `app/repositories/`
* `app/rag/`

Do not add placeholder classes or methods without a Phase 1 use case.

---

## Testing Requirements

Configure pytest to run from `backend/`.

Required test:

### Health Endpoint Smoke Test

Verify:

* `GET /health` returns HTTP 200.
* Response body equals `{"status": "ok"}`.
* Response content type is JSON.

Also verify that the application imports successfully.

Follow all testing rules from `backend/tests/AGENTS.md`.

---

## Documentation

Create or update `backend/README.md`.

Include:

* Backend purpose.
* Dependency installation command.
* Application startup command.
* Test command.
* Current Phase 1 limitations.

Minimum commands:

```bash
cd backend
uvicorn app.main:app --reload
pytest
```

Do not document unimplemented behavior as available.

---

## In Scope

Phase 1 includes:

1. Backend package structure.
2. FastAPI application factory and exported application.
3. API router aggregation.
4. Health endpoint.
5. Central application settings.
6. Base application error.
7. Initial Pydantic schemas.
8. Initial provider interfaces.
9. Empty service, repository, and RAG package boundaries.
10. pytest configuration and health smoke test.
11. `pyproject.toml`.
12. `.env.example`.
13. Minimal backend README.

---

## Out of Scope

Do not implement:

* File upload endpoints.
* PDF or DOCX extraction.
* URL fetching or crawling.
* URL security validation.
* Cleaning.
* Chunking.
* Embedding calls.
* Qdrant integration.
* PostgreSQL integration.
* Indexing.
* Retrieval.
* BM25 or hybrid search.
* Reranking.
* Answer generation.
* Citation formatting.
* Retrieval logging persistence.
* Evaluation.
* Authentication.
* Background jobs.
* Docker.
* Frontend.
* Deployment.

---

## Verification

Run from `backend/`:

```bash
pytest
```

```bash
python -c "from app.main import app; print(app.title)"
```

Optional manual startup:

```bash
uvicorn app.main:app
```

---

## Acceptance Criteria

### Application

* [ ] `create_app()` exists.
* [ ] `app = create_app()` is exported.
* [ ] The API router is registered.
* [ ] The application imports without external infrastructure.

### Health Endpoint

* [ ] `GET /health` returns HTTP 200.
* [ ] The response is exactly `{"status": "ok"}`.
* [ ] An explicit response model is used.

### Configuration

* [ ] Central settings exist.
* [ ] `.env.example` matches Phase 1 settings.
* [ ] No provider or database settings are introduced prematurely.

### Contracts

* [ ] Required schemas exist.
* [ ] Required provider interfaces exist.
* [ ] No concrete external provider implementation is added.

### Package Structure

* [ ] Required package boundaries exist.
* [ ] No speculative service, repository, or RAG classes are introduced.

### Tests

* [ ] pytest is configured.
* [ ] Health smoke test exists.
* [ ] Relevant tests pass.

### Documentation

* [ ] Backend startup instructions exist.
* [ ] Test instructions exist.
* [ ] Documentation reflects only implemented behavior.

---

## Definition of Done

Phase 1 is complete when:

* The FastAPI application imports and starts successfully.
* The health endpoint returns the required response.
* Initial configuration, schemas, and provider interfaces exist.
* Backend package boundaries are established.
* Required tests pass.
* No external infrastructure or actual RAG behavior is implemented.
* No out-of-scope feature or unapproved dependency is added.

---

## Required Completion Report

After implementation, report:

1. Summary of implemented work.
2. Created and changed files.
3. Dependencies added.
4. Verification commands and results.
5. Acceptance criteria status.
6. Deferred decisions or unverified behavior.
