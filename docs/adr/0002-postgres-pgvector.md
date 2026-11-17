# ADR 0002: PostgreSQL + pgvector

Status: Accepted

## Context

Mantle needs structured data (projects, messages, memory, keys, usage, workflow) and vector search
for RAG over project files. `vision.md` says to use pgvector first "rather than introducing a
separate vector database too early."

## Decision

Use PostgreSQL 16 with the pgvector extension (Docker image `pgvector/pgvector:pg16`) for
**both** structured data and embeddings. Access it with SQLAlchemy 2 (async) and asyncpg, and
manage the schema with Alembic. Embeddings live in `chunks.embedding` with an HNSW index using
cosine distance, always filtered by `project_id`.

## Alternatives considered

- **A separate vector database (Qdrant, Chroma, Pinecone):** a second system to run and keep in
  sync, and no joins with project data.
- **SQLite + a vector extension:** simpler to install, but weaker async and concurrency support,
  and it would have to be migrated before going multi-user.
- **Keep vectors in memory or files (FAISS):** lost on restart, no transactions, no filtering by
  project.

## Consequences

- One database to back up, and chunks can be joined directly with documents and projects.
- Users need Docker Desktop running (already in `README.md`).
- A pgvector column has a fixed dimension. Every chunk stores its `embedding_model` and
  `embedding_dimensions`. Changing the embedding model means re-indexing the project, and a
  different dimension also needs a migration.
- Hybrid search (PostgreSQL full-text + vector) can be added later without a new system.
