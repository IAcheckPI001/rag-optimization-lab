## Architecture Instructions

Use this file before changing system design, module boundaries, API contracts,
database schema, provider interfaces, or cross-cutting behavior.

## Architectural Goal

RAG Optimization Lab is a backend-first RAG research system. The architecture
should make it easy to compare ingestion, cleaning, chunking, embedding,
retrieval, generation, logging, and evaluation decisions without mixing those
responsibilities together.

## Dependency Direction

Required direction:

API routes -> Services -> Repositories / Provider Interfaces

Rules:
- Higher-level layers may depend on lower-level abstractions.
- Lower-level layers must not import API routes.
- Repositories must not import services.
- Provider implementations must not import services.
- Generation logic must not directly access parsers, vector stores, or
  repositories.
- Pipeline steps communicate through explicit schemas, not raw dictionaries.

## Layer Responsibilities

API routes:
- Validate request shape.
- Convert HTTP inputs into service calls.
- Return typed response models.
- Map application errors to HTTP errors.

Services:
- Own application workflows.
- Coordinate repositories and providers.
- Enforce domain rules.
- Compose RAG pipeline steps.

Repositories:
- Encapsulate PostgreSQL persistence.
- Read and write database records.
- Hide query details from services.

Provider interfaces:
- Define contracts for external systems.
- Wrap OpenAI, Qdrant, document extraction libraries, and web extraction tools.
- Make external behavior mockable in tests.

Pipeline components:
- Implement focused transformations such as cleaning, chunking, scoring, and
  citation formatting.
- Prefer pure functions where practical.

## Suggested Module Boundaries

Use these boundaries when no stronger existing pattern exists:

- Ingestion: source validation, upload metadata, URL intake, extraction
  orchestration.
- Extraction: PDF, DOCX, and public web text extraction.
- Cleaning: deterministic text normalization.
- Chunking: chunk construction and metadata preservation.
- Embedding: embedding request schemas and embedding provider interface.
- Indexing: vector-store persistence and document/chunk indexing.
- Retrieval: vector search, result normalization, and retrieval logs.
- Generation: answer creation from retrieved context and citation handling.
- Evaluation: metrics, test datasets, and optional judge logic.
- Logging: retrieval logs and pipeline observability metadata.

Keep modules small. Add abstractions only when they remove real duplication,
protect a boundary, or match an established local pattern.

## Contracts

Preserve API contracts unless the user explicitly approves a change.

Before changing an API contract, define:
- Endpoint path and method.
- Request schema.
- Response schema.
- Error behavior.
- Compatibility impact.
- Tests that will prove the contract.

Before changing database schema, define:
- New or changed tables/columns.
- Migration approach.
- Backward compatibility impact.
- Repository changes.
- Tests or verification plan.

Before changing provider interfaces, define:
- Interface method signatures.
- Input and output schemas.
- Failure behavior.
- Mock strategy for unit tests.

## Data Flow

Typical ingestion flow:

1. API route receives PDF, DOCX, or public URL input.
2. Service validates and coordinates ingestion.
3. Extraction provider returns extracted text with source metadata.
4. Cleaning step normalizes text.
5. Chunking step creates chunks with stable metadata.
6. Embedding provider creates embeddings.
7. Indexing provider stores vectors in Qdrant.
8. Repository records document, chunk, and log metadata as needed.

Typical question-answer flow:

1. API route receives a query.
2. Retrieval service embeds the query and searches indexed chunks.
3. Retrieval results are normalized and logged.
4. Generation service receives retrieved context.
5. LLM provider generates an answer with citations when context is sufficient.
6. Service returns answer, citations, and relevant retrieval metadata.

## Change Control

Ask for approval before:
- Adding dependencies.
- Changing API contracts.
- Changing database schema.
- Adding post-MVP capabilities.
- Introducing real external service behavior in tests.
- Broadly refactoring module structure.

For large or risky architecture changes, present a short plan before editing.

## Open Project Decisions

If a task depends on one of these decisions and no existing code answers it,
ask the user before implementing:

- Exact API versioning strategy.
- Database migration tool.
- Error response envelope.
- Retrieval log persistence schema.
- Citation response format.
- Evaluation dataset format.
- Whether backend root should remain `backend/` or use another package name.
