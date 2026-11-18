import { useState } from "react";
import { formatDueDate, isOverdue } from "../utils/date";

export interface TaskItem {
  id: number;
  title: string;
  due: string | null;
  done: boolean;
}

// The task list, with a toggle that hides finished tasks.
export function TaskList({ tasks }: { tasks: TaskItem[] }) {
  const [hideDone, setHideDone] = useState(true);
  const visible = hideDone ? tasks.filter((task) => !task.done) : tasks;
  return (
    <section>
      <label>
        <input type="checkbox" checked={hideDone} onChange={() => setHideDone(!hideDone)} />
        Hide finished tasks
      </label>
      <ul>
        {visible.map((task) => (
          <li key={task.id} className={isOverdue(task.due) ? "overdue" : ""}>
            {task.title} {task.due && <small>{formatDueDate(task.due)}</small>}
          </li>
        ))}
      </ul>
    </section>
  );
}
