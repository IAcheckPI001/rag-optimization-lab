# RAG Optimization Lab Backend

This directory contains the Phase 1 FastAPI backend skeleton for RAG
Optimization Lab.

## Install

From this directory:

```bash
python -m pip install -e ".[test]"
```

## Run

```bash
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```

## Phase 1 Limitations

Phase 1 only includes the backend package skeleton, application factory, health
endpoint, central settings, base application error, initial schemas, provider
interfaces, and tests.

It does not implement file upload, PDF or DOCX extraction, URL fetching,
cleaning, chunking, embedding calls, Qdrant, PostgreSQL, indexing, retrieval,
answer generation, citations, retrieval logging persistence, evaluation,
authentication, Docker, deployment, or frontend behavior.
