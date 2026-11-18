"""Tasks: create, complete, and find overdue ones."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Task:
    id: int
    title: str
    due: date | None = None
    done: bool = False


class TaskService:
    """Keeps tasks in memory, ordered by id."""

    def __init__(self) -> None:
        self.tasks: dict[int, Task] = {}
        self.next_id = 1

    def create_task(self, title: str, due: date | None = None) -> Task:
        """Add a task. Titles are trimmed and must not be empty."""
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")
        task = Task(self.next_id, title, due)
        self.tasks[task.id] = task
        self.next_id += 1
        return task

    def complete_task(self, task_id: int) -> Task:
        """Mark a task as done. Completing a done task changes nothing."""
        task = self.tasks[task_id]
        task.done = True
        return task

    def list_overdue(self, today: date) -> list[Task]:
        """Open tasks whose due date is before today, oldest first."""
        overdue = [t for t in self.tasks.values() if not t.done and t.due and t.due < today]
        return sorted(overdue, key=lambda t: t.due)
