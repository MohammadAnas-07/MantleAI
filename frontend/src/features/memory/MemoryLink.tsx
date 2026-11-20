import { Link } from "react-router";

import type { MemoryIndex } from "../../hooks/useMemoryIndex";

/** A link to one memory item, by its title when it is known (it may have been deleted). */
export function MemoryLink({
  projectId,
  id,
  index,
}: {
  projectId: string;
  id: string;
  index: MemoryIndex;
}) {
  const item = index.get(id);
  return (
    <Link to={`/projects/${projectId}/memory/${id}`} dir="auto">
      {item ? `${item.kind}: ${item.title}` : `item ${id.slice(0, 8)}`}
    </Link>
  );
}
