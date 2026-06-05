
## Project Summary

Project name: RAG Optimization Lab.

Backend-first RAG system for researching document processing, retrieval,
answer generation, logging, and later evaluation.

Supported MVP sources:
- PDF uploads.
- DOCX uploads.
- Single public website URLs.

Post-MVP capabilities include BM25 search, hybrid retrieval, and optional
reranking. Do not implement post-MVP capabilities until they are explicitly
requested.

## Current Implementation Status

This file describes the intended project rules and target architecture. Before
implementing any task, inspect the current repository state and do not assume
that a module, API route, database model, or provider already exists.

If the repository is still instruction-only or partially scaffolded, implement
only the requested slice and keep the structure compatible with the architecture
rules below.

## Instruction Map

Use this root `AGENTS.md` for project-wide rules. Use more specific instruction
files when working in those areas:

- `backend/AGENTS.md`: backend API, services, repositories, providers, config,
  and error handling.
- `.agents/architecture.md`: system architecture, dependency direction, module
  boundaries, contracts, and change approval rules.
- `.agents/rag-pipeline.md`: ingestion, extraction, cleaning, chunking,
  embedding, indexing, retrieval, generation, citations, logging, and
  evaluation.
- `.agents/security_policy.md`: URL ingestion, file upload, SSRF protections,
  external fetching, secrets, and logging safety.
- `tests/AGENTS.md`: pytest rules, mocks, fixtures, and test boundaries.

When a task touches multiple areas, read all relevant instruction files before
editing code.

## Non-Negotiable Rules

- Implement only the requested task.
- Do not build the full project in one step.
- Do not modify unrelated modules.
- Do not add dependencies without approval.
- Do not change API contracts or database schema without approval.
- Do not call external services directly from API routes.
- Do not call real external APIs in unit tests.
- Do not crawl private, authenticated, paywalled, social media, captcha, or
  anti-bot pages by default.
- Do not store secrets in code.

## Architecture Rules

Use this dependency direction:

API routes -> Services -> Repositories / Provider Interfaces

Rules:
- API routes must be thin.
- Routes validate request shape, parse inputs, and call services.
- Services contain application logic and coordinate pipeline steps.
- Repositories handle database access.
- Provider interfaces wrap external dependencies.
- RAG pipeline steps must communicate through explicit Pydantic schemas, not
  raw dictionaries.
- Keep ingestion, cleaning, chunking, embedding, retrieval, generation,
  evaluation, and logging separated.
- Do not let generation logic directly access parsers, vector stores, or
  repositories.

Read `.agents/architecture.md` before changing system-level design, module
boundaries, API contracts, database schema, or provider interfaces.

## MVP Scope

Core MVP:
- PDF upload.
- DOCX upload.
- Single public website URL ingestion.
- Text extraction.
- Cleaning.
- Chunking.
- Embedding.
- Qdrant indexing.
- Vector search.
- Answer generation with citations.
- Retrieval logs.

Post-MVP:
- BM25 search.
- Hybrid retrieval.
- Optional reranking.

Out of scope:
- Authentication.
- Multi-user workspace.
- Full website crawling.
- Private page crawling.
- Social media scraping.
- Playwright.
- Multi-agent workflow.

## Tech Stack

## Approved MVP Libraries

- FastAPI
- PyMuPDF
- python-docx
- trafilatura
- BeautifulSoup
- qdrant-client
- pytest

## Approved Infrastructure and Providers

- PostgreSQL (local PostgreSQL through Docker)
- Qdrant
- OpenAI `text-embedding-3-small`

Planned post-MVP dependencies:
- rank-bm25.
- sentence-transformers or another approved reranker dependency.

Do not add post-MVP dependencies until the related phase is explicitly
requested.

## RAG Pipeline Rules

- Keep ingestion, extraction, cleaning, chunking, embedding, indexing,
  retrieval, reranking, generation, logging, and evaluation as separate steps.
- Each pipeline step must have explicit input/output schemas.
- Chunks must preserve source metadata: `source_type`, `source_uri`,
  `document_id`, `chunk_id`, and `page_number` or `section` when available.
- Retrieval results must include `chunk_id`, `content`, `score`, `rank`, source
  metadata, and retrieval method.
- Reranking must preserve original retrieval score and add `rerank_score`
  separately.
- Answer generation must use retrieved context and return citations when context
  is available.
- If retrieved context is insufficient, answer generation must state
  insufficient context instead of inventing.

Read `.agents/rag-pipeline.md` before changing ingestion, chunking, retrieval,
reranking, generation, citations, logging, or evaluation.

## Security Rules

- Read `.agents/security_policy.md` before changing URL ingestion, file upload,
  crawling, external fetching, provider calls, or content logging.
- URL ingestion must block localhost, private IPs, link-local IPs, and cloud
  metadata IPs.
- Validate URLs before fetching and after redirects.
- Do not bypass captcha, login, paywall, authentication, robots restrictions, or
  anti-bot systems.
- File upload must allow only PDF and DOCX in MVP.
- Do not execute uploaded files or store uploads in a public web root.

## Coding Rules

- Use type hints.
- Use Pydantic schemas for request, response, and pipeline data models.
- Prefer pure functions for cleaning, chunking, scoring, and validation.
- Keep modules small and focused.
- Use environment variables for secrets and runtime configuration.
- Keep `.env.example` updated when adding new environment variables.
- Prefer existing project patterns over introducing new abstractions.

## Testing Rules

Use pytest.

Tests must cover:
- Normal case.
- Edge case.
- Failure case.

Rules:
- Unit tests must use mock embeddings, mock LLM provider, mock vector store, and
  mock web extractor.
- Unit tests must not call real external APIs, real websites, PostgreSQL, or
  Qdrant.
- Read `tests/AGENTS.md` before adding or changing tests.

## Development Workflow

Before implementing a task:

1. Follow this `AGENTS.md` and any more specific instruction files in the target
   directory.
2. Read relevant project instructions from `.agents/`.
3. Inspect the current code before assuming structure or implementation status.
4. If the task affects architecture, API, database, security, or RAG logic,
   propose a short plan first unless the user explicitly requested direct
   implementation.
5. Implement only the requested scope.
6. Add or update focused tests when code behavior changes.
7. Run the relevant tests.
8. Summarize changed files and test results.

For large or risky tasks:
- Propose the plan first.
- Do not edit code until the user approves the plan, unless the user explicitly
  requested direct implementation.
- Ask concise questions when a missing project decision would materially affect
  API contracts, schema design, provider behavior, security posture, or user
  workflow.

## Definition of Done

A task is done only when:
- Requested scope is implemented.
- Related tests are added or updated when code behavior changes.
- Relevant tests pass or failures are clearly explained.
- API contracts and database schema are preserved unless explicitly approved.
- Architecture, testing, and security rules are respected.
- External calls are mocked in unit tests.
- Changed files and test results are summarized.
