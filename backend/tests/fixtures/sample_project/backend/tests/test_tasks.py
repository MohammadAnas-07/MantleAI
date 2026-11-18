from datetime import date

from app.tasks import TaskService


def test_overdue_tasks_are_sorted_by_due_date() -> None:
    service = TaskService()
    service.create_task("late", date(2026, 1, 2))
    service.create_task("later", date(2026, 1, 1))
    overdue = service.list_overdue(date(2026, 2, 1))
    assert [t.title for t in overdue] == ["later", "late"]


def test_empty_title_is_rejected() -> None:
    service = TaskService()
    try:
        service.create_task("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
