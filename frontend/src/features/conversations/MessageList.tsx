import { useLayoutEffect, useRef } from "react";

import { Loader2 } from "lucide-react";

import { Badge } from "../../components/ui/Feedback";
import { Markdown } from "./Markdown";

export interface ShownMessage {
  id: string;
  role: string;
  text: string;
  status: string; // complete | streaming | error | cancelled
  model: string | null;
}

// Within this many pixels of the end counts as "at the bottom".
const STICK_PX = 48;

/**
 * The message list. It follows new text only while the user is already at the bottom, so
 * scrolling up to read is never interrupted. Long histories stay fast with CSS
 * content-visibility on each message (index.css).
 */
export function MessageList({ messages }: { messages: ShownMessage[] }) {
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const last = messages.at(-1);

  useLayoutEffect(() => {
    const el = box.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, last?.text]);

  return (
    <div
      ref={box}
      role="log"
      aria-label="Messages"
      onScroll={(e) => {
        const el = e.currentTarget;
        atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
      }}
      className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1"
    >
      {messages.map((m) => (
        <article
          key={m.id}
          aria-label={m.role === "user" ? "You" : "Assistant"}
          className={`message rounded-sm px-3 py-2.5 ${m.role === "user" ? "bg-sunken" : ""}`}
        >
          <header className="mb-1 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-text">
              {m.role === "user" ? "You" : (m.model ?? "Assistant")}
            </span>
            {m.status === "cancelled" ? <Badge kind="warning">incomplete</Badge> : null}
            {m.status === "error" ? <Badge kind="danger">error</Badge> : null}
            {m.status === "streaming" ? (
              <Badge kind="info">
                <Loader2 aria-hidden className="size-3 animate-spin" />
                {m.text ? "writing…" : "waiting…"}
              </Badge>
            ) : null}
          </header>
          <div dir="auto" className="text-md">
            {m.role === "user" ? (
              <p className="whitespace-pre-wrap break-words">{m.text}</p>
            ) : (
              <Markdown text={m.text} />
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
