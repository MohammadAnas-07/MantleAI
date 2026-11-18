import { useId, useState } from "react";

import { Badge, Banner, Skeleton } from "../../components/ui/Feedback";
import { useConversation, useHandoffPreview } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { errorMessage } from "../../lib/api/errors";
import { formatTokens, lineRange } from "../../lib/format";
import type { SourceReport } from "../../lib/api/types";

const SECTION_NAMES: Record<string, string> = {
  system: "System prompt",
  pinned_items: "Pinned memory",
  conversation_summary: "Summary",
  recent_messages: "Recent messages",
  retrieved_context: "Project code",
};

/** What would be sent to a model right now (the handoff preview). Makes no model call. */
export function ContextPanel({ conversationId }: { conversationId: string }) {
  const selectId = useId();
  const conversation = useConversation(conversationId);
  const models = useModelInfo();
  const [picked, setPicked] = useState<string>("");
  const modelId = picked || conversation.data?.current_model_id || null;
  const preview = useHandoffPreview(conversationId, modelId);
  const p = preview.data;

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-col gap-1">
        <label htmlFor={selectId}>Preview for</label>
        <select
          id={selectId}
          value={modelId ?? ""}
          onChange={(e) => {
            setPicked(e.target.value);
          }}
          className="rounded-sm border-2 border-line bg-surface px-2 py-1"
        >
          {models.chatModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} · {formatTokens(m.context_window)}
              {m.id === conversation.data?.current_model_id ? " (current)" : ""}
            </option>
          ))}
        </select>
      </div>

      {preview.isLoading ? <Skeleton label="Loading the context preview" /> : null}
      {preview.isError ? <Banner kind="danger">{errorMessage(preview.error)}</Banner> : null}
      {p ? (
        <>
          <p>
            <strong>{formatTokens(p.total_tokens)}</strong> of {formatTokens(p.budget)} tokens
            (window {formatTokens(p.context_window)}, {formatTokens(p.reserved_output_tokens)} kept
            for the reply, {formatTokens(p.safety_margin_tokens)} margin)
          </p>
          <table className="w-full text-left">
            <caption className="sr-only">Sections</caption>
            <thead>
              <tr className="label text-xs">
                <th scope="col">Section</th>
                <th scope="col">Tokens</th>
                <th scope="col">Items</th>
              </tr>
            </thead>
            <tbody>
              {p.sections.map((s) => (
                <tr key={s.name}>
                  <td>
                    {SECTION_NAMES[s.name] ?? s.name} {s.included ? null : <Badge>not sent</Badge>}
                  </td>
                  <td>{formatTokens(s.tokens)}</td>
                  <td>{s.items_total ? `${s.items_included}/${s.items_total}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <section aria-label="Project code" className="space-y-1">
            <h3 className="text-sm">
              Project code ({formatTokens(p.retrieved.tokens)} of{" "}
              {formatTokens(p.retrieved.max_tokens)})
            </h3>
            {p.retrieved.used.length === 0 && p.retrieved.dropped.length === 0 ? (
              <p className="text-muted">No code yet: it is retrieved when you send a message.</p>
            ) : null}
            <SourceList sources={p.retrieved.used} />
            {p.retrieved.dropped.length > 0 ? (
              <>
                <h4 className="text-xs">Left out</h4>
                <SourceList
                  sources={p.retrieved.dropped}
                  reasons={p.retrieved.dropped.map((d) => d.reason)}
                />
              </>
            ) : null}
          </section>

          {p.dropped.length > 0 ? (
            <section aria-label="Dropped" className="space-y-1">
              <h3 className="text-sm">Dropped to fit</h3>
              <ul className="code list-disc pl-5">
                {p.dropped.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {p.pinned.dropped.length > 0 ? (
            <p className="text-muted">
              {p.pinned.dropped.length} pinned item{p.pinned.dropped.length === 1 ? "" : "s"} left
              out ({[...new Set(p.pinned.dropped.map((d) => d.reason))].join(", ")}).
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function SourceList({ sources, reasons }: { sources: SourceReport[]; reasons?: string[] }) {
  return (
    <ul className="space-y-0.5">
      {sources.map((s, i) => (
        <li key={`${s.path}:${s.start_line}`} className="flex flex-wrap items-center gap-2">
          <span className="code break-all">
            {s.path}:{lineRange(s.start_line, s.end_line)}
          </span>
          <span className="text-xs text-muted">score {s.score.toFixed(4)}</span>
          {reasons?.[i] ? <Badge kind="warning">{reasons[i]}</Badge> : null}
        </li>
      ))}
    </ul>
  );
}
