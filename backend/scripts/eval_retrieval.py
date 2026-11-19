"""Retrieval evaluation with a REAL embedding model. Not part of pytest.

Indexes a folder with your embedding model (your setting, else DEFAULT_EMBEDDING_MODEL), asks
the questions in a YAML file, and prints recall@5 and MRR for vector-only, text-only and hybrid
search, overall and per kind of question. Defaults: the sample project in tests/fixtures and
its 20 questions.

Indexing and every question make real, paid embedding calls with the key you saved in Mantle
(text-only search needs no call). The folder's text goes to your embedding provider.
`--estimate-only` makes no call at all: it reads the folder the way indexing would and prints
the segments, tokens and cost.

Run from backend/ with the venv active, after `alembic upgrade head` and
`python -m app.db.seed`, with a key saved for the embedding model's provider:

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --project-path C:\\code\\repo --questions questions.yaml
    python scripts/eval_retrieval.py --project-path C:\\code\\repo --estimate-only
    python scripts/eval_retrieval.py --project-id <id> --questions ...   # reuse an index

Questions file: a list of
    - question: How are passwords hashed?
      kind: behaviour | name | two_files     (optional, default "behaviour")
      expected: path/relative/to/root.py     (or a list of paths)
      verify: true                           (optional: the expected answer needs a check)

Scores per question, for the top 5 results:
  recall@5   share of the expected files found (1 or 0 for one file, 0.5 if one of two)
  all@5      1 when every expected file is found
  MRR        1 / rank of the first expected file found
"""

import argparse
import asyncio
import math
import sys
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = BACKEND / "tests" / "fixtures" / "sample_project"
QUESTIONS = BACKEND / "tests" / "fixtures" / "retrieval_questions.yaml"
K = 5
MODES = ("vector", "text", "hybrid")
KINDS = ("behaviour", "name", "two_files")


# ---- questions and scoring (pure, tested in tests/test_eval_retrieval.py) ------------------


@dataclass(frozen=True)
class Question:
    question: str
    expected: tuple[str, ...]
    kind: str = "behaviour"
    verify: bool = False


def load_questions(path: Path) -> list[Question]:
    """Read and check a questions file. Raises ValueError naming the bad entry."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: expected a non-empty list of questions")
    out: list[Question] = []
    for number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"question {number}: expected a mapping")
        unknown = set(item) - {"question", "expected", "kind", "verify"}
        if unknown:
            raise ValueError(f"question {number}: unknown keys {sorted(unknown)}")
        expected = item.get("expected")
        files = (expected,) if isinstance(expected, str) else tuple(expected or ())
        if not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError(f"question {number}: missing question text")
        if not files or not all(isinstance(f, str) and f for f in files):
            raise ValueError(f"question {number}: expected must be a path or a list of paths")
        kind = item.get("kind", "behaviour")
        if kind not in KINDS:
            raise ValueError(f"question {number}: kind must be one of {KINDS}")
        out.append(Question(item["question"].strip(), files, kind, bool(item.get("verify"))))
    return out


@dataclass
class Score:
    recall: float  # share of expected files in the top K
    all_found: bool
    reciprocal_rank: float
    first_rank: int | None


def score(result_paths: list[str], expected: tuple[str, ...], k: int = K) -> Score:
    """Score one question from the paths of the results, best first. A file counts at the
    rank of its first result."""
    top = result_paths[:k]
    ranks = [top.index(path) + 1 for path in expected if path in top]
    first = min(ranks) if ranks else None
    return Score(
        recall=len(ranks) / len(expected),
        all_found=len(ranks) == len(expected),
        reciprocal_rank=1 / first if first else 0.0,
        first_rank=first,
    )


@dataclass
class Totals:
    count: int = 0
    recall: float = 0.0
    all_found: int = 0
    reciprocal_ranks: float = 0.0

    def add(self, s: Score) -> None:
        self.count += 1
        self.recall += s.recall
        self.all_found += int(s.all_found)
        self.reciprocal_ranks += s.reciprocal_rank

    def row(self) -> tuple[float, float, float]:
        n = self.count or 1
        return self.recall / n, self.all_found / n, self.reciprocal_ranks / n


@dataclass
class Report:
    overall: dict[str, Totals] = field(default_factory=lambda: {m: Totals() for m in MODES})
    by_kind: dict[str, dict[str, Totals]] = field(default_factory=dict)

    def add(self, question: Question, mode: str, s: Score) -> None:
        self.overall[mode].add(s)
        kind = self.by_kind.setdefault(question.kind, {m: Totals() for m in MODES})
        kind[mode].add(s)

    def lines(self) -> list[str]:
        out = [f"{'':24}" + "".join(f"{m:>22}" for m in MODES)]
        out.append(f"{'':24}" + "".join(f"{'recall  all   MRR':>22}" for _ in MODES))
        groups = [("all questions", self.overall)]
        groups += [(f"  {kind}", self.by_kind[kind]) for kind in KINDS if kind in self.by_kind]
        for name, totals in groups:
            count = next(iter(totals.values())).count
            cells = "".join("{:>10.2f}{:>6.2f}{:>6.3f}".format(*totals[m].row()) for m in MODES)
            out.append(f"{f'{name} ({count})':24}{cells}")
        return out


# ---- estimate without any model call -------------------------------------------------------


def estimate(root: Path) -> dict[str, Any]:
    """Read `root` the way indexing does (same filters, same splitting) and count what would be
    embedded. No database, no model call."""
    from app.modules.llm.catalog import DEFAULT_MODELS
    from app.modules.rag.chunker import ChunkSettings, embedding_input, split
    from app.modules.rag.scanner import SkipReason, WalkLimits, read_text, walk

    limits = WalkLimits(settings.index_max_file_bytes, settings.index_max_files)
    walked = walk(root, limits)
    report = walked.report
    cfg = ChunkSettings.from_settings()
    files = segments = tokens = 0
    for entry in walked.files:
        read = read_text(entry.abs_path, limits.max_file_bytes)
        if read.text is None:
            report.add(read.skip_reason or "unreadable", entry.path)
            continue
        parts = split(read.text, entry.language, cfg).segments
        if len(parts) > settings.index_max_chunks_per_file:
            report.add(SkipReason.TOO_MANY_SEGMENTS, entry.path)
            continue
        files += 1
        segments += len(parts)
        tokens += sum(
            math.ceil(len(embedding_input(entry.path, s.symbol, s.text)) / 4) for s in parts
        )
    model = next(m for m in DEFAULT_MODELS if m.litellm_model == settings.default_embedding_model)
    price = model.input_cost_per_mtok or Decimal(0)
    return {
        "files": files,
        "segments": segments,
        "tokens": tokens,
        "cost_usd": (Decimal(tokens) * price / Decimal(1_000_000)).quantize(Decimal("0.0001")),
        "model": model.litellm_model,
        "provider": model.provider,
        "skipped": report.as_dict(),
    }


# ---- the real run --------------------------------------------------------------------------


async def default_user() -> uuid.UUID:
    from app.core.repositories import UserRepository
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        user = await UserRepository(session).get_default()
        if user is None:
            raise SystemExit("Run `python -m app.db.seed` first.")
        return user.id


async def index_folder(user_id: uuid.UUID, root: Path) -> uuid.UUID:
    from app.db.session import SessionLocal
    from app.modules.llm.service import get_gateway
    from app.modules.projects.service import create_project
    from app.modules.rag import service as rag

    async with SessionLocal() as session:
        project = await create_project(session, user_id, f"Retrieval eval: {root.name}", str(root))
        await rag.set_source(session, user_id, project.id, str(root))
        # force: running this script is the request; --estimate-only shows the cost beforehand.
        run = await rag.start_index(session, user_id, project.id, force=True)
        await session.commit()
        print(f"Indexing {root} into project {project.id} ...")
    await rag.run_index_job(SessionLocal, get_gateway(), user_id, run.id)
    async with SessionLocal() as session:
        run = await rag.get_run(session, user_id, run.id)
        print(
            f"  run {run.status}: {run.files_indexed} files, {run.chunks_created} segments, "
            f"~{run.tokens} tokens, ~${run.cost_estimate_usd}"
        )
        if run.status != "succeeded":
            raise SystemExit(f"Indexing failed: {run.error}")
    return project.id


async def evaluate(user_id: uuid.UUID, project_id: uuid.UUID, questions: list[Question]) -> None:
    from app.db.session import SessionLocal
    from app.modules.llm.service import UsageLinks, UsageTrigger, get_embedding_model, get_gateway
    from app.modules.rag.search import hybrid_search

    gateway = get_gateway()
    report = Report()
    print(f"\n{'#':>3} {'kind':10} {'question':52} " + " ".join(f"{m:>7}" for m in MODES))
    for number, q in enumerate(questions, start=1):
        async with SessionLocal() as session:
            model = await get_embedding_model(session, user_id)
            [vector] = await gateway.embed(
                session, user_id, model.id, [q.question], trigger=UsageTrigger.USER,
                links=UsageLinks(project_id=project_id), input_type="query",
            )  # fmt: skip
            cells = []
            for mode in MODES:
                blocks = await hybrid_search(
                    session, user_id, project_id, model=model.litellm_model, vector=vector,
                    query=q.question, top_k=K, candidates=settings.retrieval_candidates,
                    rrf_k=settings.retrieval_rrf_k, mode=mode,
                )  # fmt: skip
                s = score([b.path for b in blocks], q.expected)
                report.add(q, mode, s)
                found = f"{round(s.recall * len(q.expected))}/{len(q.expected)}"
                cells.append(f"{(str(s.first_rank) if s.first_rank else '-')}:{found}")
            await session.commit()
        flag = " (verify)" if q.verify else ""
        print(f"{number:>3} {q.kind:10} {(q.question + flag)[:52]:52} "
              + " ".join(f"{c:>7}" for c in cells))  # fmt: skip
        await asyncio.sleep(settings.embed_batch_delay_seconds)

    print(
        "\nEach cell above: rank of the first expected file : expected files found in the top 5.\n"
    )
    for line in report.lines():
        print(line)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-path", type=Path, default=SAMPLE, help="folder to index")
    parser.add_argument("--questions", type=Path, default=QUESTIONS, help="questions YAML")
    parser.add_argument("--project-id", type=uuid.UUID, help="reuse an indexed project")
    parser.add_argument(
        "--estimate-only", action="store_true", help="count tokens and cost; no model call"
    )
    args = parser.parse_args()
    root = args.project_path.resolve()
    questions = load_questions(args.questions)
    missing = [f for q in questions for f in q.expected if not (root / f).is_file()]
    if missing and not args.project_id:
        raise SystemExit(f"Expected files not found under {root}: {missing[:5]}")

    if args.estimate_only:
        e = estimate(root)
        print(f"{root}: {e['files']} files, {e['segments']} segments, ~{e['tokens']} tokens")
        print(f"Indexing cost with {e['model']} ({e['provider']}): about ${e['cost_usd']}")
        print(f"Questions: {len(questions)} query embeddings (a few tokens each)")
        for reason, info in e["skipped"].items():
            print(f"  skipped {reason}: {info['count']} (e.g. {', '.join(info['examples'][:2])})")
        return

    from app.db.session import engine
    from app.modules.llm.service import LLMError

    try:
        user_id = await default_user()
        project_id = args.project_id or await index_folder(user_id, root)
        await evaluate(user_id, project_id, questions)
        print(f"\nProject id (reuse with --project-id): {project_id}")
    except LLMError as exc:
        raise SystemExit(f"Embedding call failed: {exc.code} ({exc.message})") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
