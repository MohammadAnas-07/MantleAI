"""The OpenAPI schema gives generated clients clean, stable names."""

from collections import Counter

from app.main import app


def operations() -> list[dict]:
    spec = app.openapi()
    return [op for methods in spec["paths"].values() for op in methods.values()]


def test_operation_ids_are_unique_function_names() -> None:
    ids = [op["operationId"] for op in operations()]
    assert [i for i, n in Counter(ids).items() if n > 1] == []
    assert all(i.isidentifier() and "api_v1" not in i for i in ids)


def test_every_operation_has_a_tag() -> None:
    assert all(op.get("tags") for op in operations())
