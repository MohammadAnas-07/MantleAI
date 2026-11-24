import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, Send, Square } from "lucide-react";
import { useState, type SubmitEvent, type KeyboardEvent } from "react";
import { useParams } from "react-router";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Field";
import { Badge, Banner, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { keys, useConversation, useMessages } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import { lineRange } from "../../lib/format";
import { limits } from "../../lib/limits";
import { llmErrorText } from "../../lib/llmErrors";
import type { Message } from "../../lib/api/types";
import { MessageList, type ShownMessage } from "./MessageList";
import { useHandoffNote, type SwitchReason } from "../../hooks/useHandoffNote";
import { SwitchDialog } from "./switching";
import { useChat, type ChatProblem } from "./useChat";

/** The route component: keyed by conversation, so nothing carries over between them. */
export function ConversationRoute() {
  const { conversationId = "" } = useParams();
  return <ConversationView key={conversationId} conversationId={conversationId} />;
}

const textOf = (m: Message): string =>
  m.content.map((p) => (p.type === "text" && typeof p.text === "string" ? p.text : "")).join("");

function ConversationView({ conversationId }: { conversationId: string }) {
  const conversation = useConversation(conversationId);
  const messages = useMessages(conversationId);
  const models = useModelInfo();
  const { state, send, stop } = useChat(conversationId);
  const note = useHandoffNote(conversationId);
  const [draft, setDraft] = useState("");
  const [switchTo, setSwitchTo] = useState<{ id: string; reason: SwitchReason } | null>(null);
  const streaming = state.status === "streaming";

  const shown: ShownMessage[] = (messages.data ?? [])
    // While streaming, the local copy replaces the saved one (which is still empty).
    .filter((m) => !(streaming && (m.id === state.messageId || m.id === state.userMessageId)))
    .map((m) => ({
      id: m.id,
      role: m.role,
      text: textOf(m),
      status: m.status,
      model: m.model_id ? models.name(m.model_id) : null,
    }));
  if (streaming && state.pendingUserText !== null) {
    shown.push({
      id: "pending-user",
      role: "user",
      text: state.pendingUserText,
      status: "complete",
      model: null,
    });
    shown.push({
      id: "pending-reply",
      role: "assistant",
      text: state.replyText,
      status: "streaming",
      model: null,
    });
  }

  const submit = (event?: SubmitEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || streaming) return;
    setDraft("");
    void send(text);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  if (conversation.isError)
    return <Banner kind="danger">{errorMessage(conversation.error)}</Banner>;

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line pb-3">
        <h1 className="min-w-0 flex-1 truncate font-serif text-xl font-normal" dir="auto">
          {conversation.data?.title || "Untitled conversation"}
        </h1>
        {conversation.data ? (
          <CodeContextSwitch
            conversationId={conversationId}
            enabled={conversation.data.code_context_enabled}
          />
        ) : null}
      </div>

      {note ? <Banner kind="info">{note.text}</Banner> : null}
      {state.warnings.map((w, i) => (
        <Banner key={`${w.code}-${i}`} kind="warning">
          {w.message}
        </Banner>
      ))}
      {state.problem ? (
        <ProblemNotice
          problem={state.problem}
          onPick={(id) => {
            setSwitchTo({ id, reason: reasonFor(state.problem?.code) });
          }}
        />
      ) : null}
      {state.stopped ? (
        <p className="text-base text-muted">
          Stopped. The part that arrived is kept and marked incomplete.
        </p>
      ) : null}

      <div aria-live="polite" className="sr-only">
        {streaming ? "Mantle is replying." : state.stopped ? "Reply stopped." : ""}
      </div>

      {messages.isLoading ? <Skeleton label="Loading messages" /> : null}
      {messages.isError ? (
        <QueryError
          error={messages.error}
          onRetry={() => void messages.refetch()}
          retrying={messages.isFetching}
        />
      ) : null}
      {messages.data && shown.length === 0 ? (
        <EmptyState icon={MessagesSquare}>
          No messages yet. Ask something about this project to start. The model sees the project
          memory, the profile and, if the project is indexed, the matching code.
        </EmptyState>
      ) : null}
      <MessageList messages={shown} />

      {state.sources.length > 0 ? (
        <details className="text-base">
          <summary className="cursor-pointer font-medium">
            Code used for this reply ({state.sources.length})
          </summary>
          <ul aria-label="Code used" className="mt-2 flex flex-wrap gap-1.5">
            {state.sources.map((s) => (
              <li
                key={`${s.path}:${s.start_line}`}
                className="code rounded-sm bg-sunken px-1.5 py-0.5 break-all"
              >
                {s.path}:{lineRange(s.start_line, s.end_line)}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <form
        onSubmit={submit}
        className="rounded-lg border border-field bg-paper transition-colors duration-150 ease-out focus-within:border-text has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-accent"
      >
        <label htmlFor="composer" className="sr-only">
          Message
        </label>
        <textarea
          id="composer"
          value={draft}
          maxLength={limits.message}
          dir="auto"
          rows={3}
          placeholder={streaming ? "Wait for the reply, or stop it." : "Ask about this project"}
          aria-describedby="composer-hint"
          onChange={(e) => {
            setDraft(e.target.value);
          }}
          onKeyDown={onKeyDown}
          className="block min-h-16 w-full resize-y rounded-lg bg-transparent px-3 pt-2.5 text-md focus-visible:outline-none"
        />
        <div className="flex items-center gap-2 px-2 pb-2">
          <p id="composer-hint" className="min-w-0 flex-1 truncate pl-1 text-sm text-muted">
            Enter to send, Shift+Enter for a new line
          </p>
          {streaming ? (
            <Button
              variant="danger"
              onClick={stop}
              icon={<Square aria-hidden className="size-4" />}
            >
              Stop
            </Button>
          ) : (
            <Button
              type="submit"
              variant="primary"
              disabled={!draft.trim()}
              icon={<Send aria-hidden className="size-4" />}
            >
              Send
            </Button>
          )}
        </div>
      </form>

      <SwitchDialog
        key={switchTo?.id ?? "none"}
        conversationId={conversationId}
        targetModelId={switchTo?.id ?? null}
        reason={switchTo?.reason ?? "user_choice"}
        onClose={() => {
          setSwitchTo(null);
        }}
      />
    </div>
  );
}

function reasonFor(code: string | undefined): SwitchReason {
  if (code === "rate_limited" || code === "quota_exhausted") return "rate_limit";
  if (code === "context_too_long") return "context_limit";
  return "provider_error";
}

function ProblemNotice({
  problem,
  onPick,
}: {
  problem: ChatProblem;
  onPick: (modelId: string) => void;
}) {
  const busy = problem.code === "generation_in_progress";
  return (
    <Banner kind="danger">
      <p>
        {busy
          ? "A reply is already being generated for this conversation. Wait for it to finish."
          : llmErrorText(problem.code, problem.message)}
      </p>
      {problem.suggested.length > 0 ? (
        <div className="mt-2">
          <p>You can switch to another model. Mantle won&apos;t switch by itself:</p>
          <ul aria-label="Suggested models" className="mt-2 flex flex-wrap gap-2">
            {problem.suggested.map((m) => (
              <li key={m.model_id}>
                <Button
                  size="sm"
                  onClick={() => {
                    onPick(m.model_id);
                  }}
                >
                  {m.display_name}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Banner>
  );
}

function CodeContextSwitch({
  conversationId,
  enabled,
}: {
  conversationId: string;
  enabled: boolean;
}) {
  const client = useQueryClient();
  const toggle = useMutation({
    mutationFn: (value: boolean) =>
      api.updateConversation(conversationId, { code_context_enabled: value }),
    onSuccess: (conversation) => {
      client.setQueryData(keys.conversation(conversationId), conversation);
    },
  });
  return (
    <div className="flex items-center gap-2">
      <Checkbox
        label="Use project code"
        checked={enabled}
        disabled={toggle.isPending}
        onChange={(e) => {
          toggle.mutate(e.target.checked);
        }}
      />
      {!enabled ? <Badge>code off</Badge> : null}
      {toggle.isError ? (
        <span role="alert" className="text-sm text-danger">
          {errorMessage(toggle.error)}
        </span>
      ) : null}
    </div>
  );
}
