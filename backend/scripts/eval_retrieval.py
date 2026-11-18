"""Retrieval evaluation with a REAL embedding model. Not part of pytest.

Indexes tests/fixtures/sample_project with your embedding model (your setting, else
DEFAULT_EMBEDDING_MODEL), then asks the 20 questions in tests/fixtures/retrieval_questions.yaml
and prints recall@5 and MRR for vector-only, text-only and hybrid search.

It makes real, paid API calls with the key you saved in Mantle (about 30 segments to index
and one query embedding per question; text-only search needs no call). The sample project has
no secrets, but its text goes to your embedding provider.

Run from backend/ with the venv active, after `alembic upgrade head` and
`python -m app.db.seed`, with a key saved for the embedding model's provider:

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --project-id <id>   # reuse an indexed project, no indexing
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.repositories import UserRepository  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.modules.llm.service import (  # noqa: E402
    LLMError,
    UsageLinks,
    UsageTrigger,
    get_embedding_model,
    get_gateway,
)
from app.modules.projects.service import create_project  # noqa: E402
from app.modules.rag import service as rag  # noqa: E402
from app.modules.rag.search import SearchMode, hybrid_search  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = BACKEND / "tests" / "fixtures" / "sample_project"
QUESTIONS = BACKEND / "tests" / "fixtures" / "retrieval_questions.yaml"
K = 5
MODES: tuple[SearchMode, ...] = ("vector", "text", "hybrid")


@dataclass
class Scores:
    hits: int = 0
    reciprocal_ranks: float = 0.0

    def add(self, rank: int | None) -> None:
        if rank is not None and rank <= K:
            self.hits += 1
            self.reciprocal_ranks += 1 / rank


async def default_user() -> uuid.UUID:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_default()
        if user is None:
            raise SystemExit("Run `python -m app.db.seed` first.")
        return user.id


async def index_sample(user_id: uuid.UUID) -> uuid.UUID:
    gateway = get_gateway()
    async with SessionLocal() as session:
        project = await create_project(session, user_id, "Retrieval eval", "Sample project")
        await rag.set_source(session, user_id, project.id, str(SAMPLE))
        run = await rag.start_index(session, user_id, project.id)
        await session.commit()
        print(f"Indexing {SAMPLE} into project {project.id} ...")
    await rag.run_index_job(SessionLocal, gateway, user_id, run.id)
    async with SessionLocal() as session:
        run = await rag.get_run(session, user_id, run.id)
        print(
            f"  run {run.status}: {run.files_indexed} files, {run.chunks_created} segments, "
            f"~{run.tokens} tokens, ~${run.cost_estimate_usd}"
        )
        if run.status != "succeeded":
            raise SystemExit(f"Indexing failed: {run.error}")
    return project.id


def first_rank(paths: list[str], expected: str) -> int | None:
    for rank, path in enumerate(paths, start=1):
        if path == expected:
            return rank
    return None


async def evaluate(user_id: uuid.UUID, project_id: uuid.UUID) -> None:
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    gateway = get_gateway()
    scores = {mode: Scores() for mode in MODES}
    print(f"\n{'question':58} " + " ".join(f"{m:>7}" for m in MODES))
    for item in questions:
        question, expected = item["question"], item["expected"]
        async with SessionLocal() as session:
            model = await get_embedding_model(session, user_id)
            [vector] = await gateway.embed(
                session, user_id, model.id, [question], trigger=UsageTrigger.USER,
                links=UsageLinks(project_id=project_id), input_type="query",
            )  # fmt: skip
            ranks = {}
            for mode in MODES:
                blocks = await hybrid_search(
                    session, user_id, project_id, model=model.litellm_model, vector=vector,
                    query=question, top_k=K, candidates=settings.retrieval_candidates,
                    rrf_k=settings.retrieval_rrf_k, mode=mode,
                )  # fmt: skip
                ranks[mode] = first_rank([b.path for b in blocks], expected)
                scores[mode].add(ranks[mode])
            await session.commit()
        cells = " ".join(f"{(str(ranks[m]) if ranks[m] else '-'):>7}" for m in MODES)
        print(f"{question[:58]:58} {cells}")
        await asyncio.sleep(settings.embed_batch_delay_seconds)

    total = len(questions)
    print(f"\n{'':58} " + " ".join(f"{m:>7}" for m in MODES))
    print(f"{f'recall@{K}':58} " + " ".join(f"{s.hits / total:7.2f}" for s in scores.values()))
    print(f"{'MRR':58} " + " ".join(f"{s.reciprocal_ranks / total:7.3f}" for s in scores.values()))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", type=uuid.UUID, help="reuse an indexed project")
    args = parser.parse_args()
    try:
        user_id = await default_user()
        project_id = args.project_id or await index_sample(user_id)
        await evaluate(user_id, project_id)
        print(f"\nProject id (reuse with --project-id): {project_id}")
    except LLMError as exc:
        raise SystemExit(f"Embedding call failed: {exc.code} ({exc.message})") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
