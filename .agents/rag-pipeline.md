## RAG Pipeline Instructions

Use this file before changing ingestion, extraction, cleaning, chunking,
embedding, indexing, retrieval, reranking, generation, citations, logging, or
evaluation.

## Pipeline Principles

- Keep every pipeline stage separated.
- Each stage must use explicit input and output schemas.
- Preserve source metadata through the whole flow.
- Prefer deterministic, pure functions for cleaning, chunking, scoring, and
  citation formatting.
- Unit tests must mock external providers.
- Do not add post-MVP retrieval or reranking dependencies without approval.

## MVP Pipeline

MVP stages:

1. Source intake.
2. Text extraction.
3. Cleaning.
4. Chunking.
5. Embedding.
6. Qdrant indexing.
7. Vector retrieval.
8. Answer generation with citations.
9. Retrieval logging.

Evaluation may be added when explicitly requested or when a task already targets
evaluation.

## Source Intake

Supported MVP source types:
- PDF upload.
- DOCX upload.
- Single public website URL.

Source metadata must include:
- `source_type`.
- `source_uri`.
- `document_id`.
- Original filename when available.
- URL after validated redirects when applicable.

Do not support full website crawling, private pages, authenticated pages,
paywalled pages, social media scraping, captcha bypass, anti-bot bypass, or
Playwright in MVP.

## Text Extraction

PDF extraction:
- Use PyMuPDF when PDF extraction is implemented.
- Preserve page numbers when available.
- Do not execute uploaded files.

DOCX extraction:
- Use python-docx when DOCX extraction is implemented.
- Preserve headings or section labels when practical.

Web extraction:
- Use trafilatura and/or BeautifulSoup when public URL extraction is
  implemented.
- Validate URLs before fetching and after redirects.
- Follow `.agents/security_policy.md`.

Extraction output should include:
- Extracted text.
- Source metadata.
- Page number or section when available.
- Extraction warnings when useful.

## Cleaning

Cleaning should be deterministic and testable.

Allowed cleaning examples:
- Normalize whitespace.
- Remove repeated empty lines.
- Trim leading and trailing text.
- Normalize common extraction artifacts when safe.

Avoid cleaning that changes meaning:
- Do not remove citations, headings, tables, or lists blindly.
- Do not summarize during cleaning.
- Do not call LLMs during cleaning.

## Chunking

Chunking output must preserve:
- `document_id`.
- `chunk_id`.
- `source_type`.
- `source_uri`.
- `page_number` or `section` when available.
- Chunk content.
- Chunk index or order.

Chunk ids should be stable enough for citation and retrieval logs. If stable id
strategy is undecided, ask before adopting a broad convention.

Do not mix chunking with embedding, indexing, or generation logic.

## Embedding

Use OpenAI `text-embedding-3-small` for MVP runtime embedding unless the user
approves another provider or model.

Embedding rules:
- Call embedding providers through provider interfaces.
- Do not call OpenAI directly from API routes.
- Unit tests must use mock embedding providers.
- Keep embedding input and output schemas explicit.
- Do not store API keys in code.

## Indexing

Use Qdrant for MVP vector indexing.

Indexing rules:
- Call Qdrant through a provider interface.
- Preserve chunk metadata in vector payloads where needed for retrieval and
  citation.
- Keep repository persistence separate from vector-store indexing.
- Unit tests must mock the vector store.

If collection naming, vector size, distance metric, or payload schema is
undecided and affects API or data compatibility, ask before implementing.

## Retrieval

MVP retrieval is vector search.

Retrieval results must include:
- `chunk_id`.
- `content`.
- `score`.
- `rank`.
- `source_type`.
- `source_uri`.
- `document_id`.
- `page_number` or `section` when available.
- `retrieval_method`.

Retrieval services should normalize provider-specific results into project
schemas before passing them to generation.

Do not implement BM25, hybrid retrieval, or reranking until explicitly
requested.

## Reranking

Reranking is post-MVP.

If reranking is explicitly requested:
- Preserve original retrieval score.
- Add `rerank_score` separately.
- Preserve original rank when useful.
- Do not replace retrieval metadata.
- Do not add reranker dependencies without approval.

## Answer Generation

Generation must use retrieved context.

Rules:
- Generation services receive normalized retrieval results.
- Generation logic must not access parsers, repositories, or vector stores
  directly.
- If context is sufficient, return an answer with citations.
- If context is insufficient, state insufficient context instead of inventing.
- Unit tests must mock the LLM provider.

Citation output should reference chunk/source metadata. If exact citation format
is not already established and the task depends on it, ask before changing API
contracts.

## Retrieval Logging

Retrieval logs should capture enough metadata to evaluate and debug retrieval
quality without storing secrets.

Useful fields include:
- Query text or safe query representation.
- Retrieval method.
- Returned chunk ids.
- Scores and ranks.
- Document ids.
- Generation outcome when applicable.
- Timestamp when persistence is implemented.

Do not log API keys, authorization headers, secrets, or unnecessary full raw
documents.

## Evaluation

Evaluation is part of the broader project, but do not invent a full evaluation
framework unless requested.

Before changing metrics or judge logic, define:
- Dataset format.
- Metric names and formulas.
- Expected inputs and outputs.
- Mock strategy for judge or LLM behavior.
- Tests for normal, edge, and failure cases.
