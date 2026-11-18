"""Reminder emails for overdue tasks."""

from app.tasks import Task

SMTP_HOST = "localhost"
SMTP_PORT = 1025
REMINDER_SUBJECT = "You have overdue tasks"


def render_reminder(tasks: list[Task]) -> str:
    lines = [f"- {t.title} (due {t.due})" for t in tasks]
    return "These tasks are overdue:\n" + "\n".join(lines)


def send_reminder_email(address: str, tasks: list[Task], outbox: list[dict]) -> bool:
    """Queue one reminder email per user; nothing is sent when no task is overdue."""
    if not tasks:
        return False
    outbox.append({"to": address, "subject": REMINDER_SUBJECT, "body": render_reminder(tasks)})
    return True
