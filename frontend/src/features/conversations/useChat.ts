import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { keys } from "../../hooks/queries";
import { sendMessage } from "../../lib/api/endpoints";
import { ApiError } from "../../lib/api/errors";
import type { SourceReport, StreamWarning, SuggestedModel } from "../../lib/api/types";

export interface ChatProblem {
  code: string;
  message: string;
  suggested: SuggestedModel[];
}

export interface ChatState {
  status: "idle" | "streaming";
  /** The message being sent, shown until the saved copy arrives. */
  pendingUserText: string | null;
  replyText: string;
  messageId: string | null;
  userMessageId: string | null;
  sources: SourceReport[];
  warnings: StreamWarning[];
  problem: ChatProblem | null;
  stopped: boolean;
}

const IDLE: ChatState = {
  status: "idle",
  pendingUserText: null,
  replyText: "",
  messageId: null,
  userMessageId: null,
  sources: [],
  warnings: [],
  problem: null,
  stopped: false,
};

function suggestedFrom(details: Record<string, unknown>): SuggestedModel[] {
  const list = details.suggested_models;
  return Array.isArray(list) ? (list as SuggestedModel[]) : [];
}

/**
 * Sends a message and streams the reply. Render the owning component with
 * `key={conversationId}`: switching conversation unmounts it, which aborts the stream, so an
 * old reply can never show up in a new conversation.
 */
export function useChat(conversationId: string) {
  const client = useQueryClient();
  const [state, setState] = useState<ChatState>(IDLE);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  const refresh = useCallback(async () => {
    await client.invalidateQueries({ queryKey: keys.messages(conversationId) });
    void client.invalidateQueries({ queryKey: keys.conversation(conversationId) });
    void client.invalidateQueries({ queryKey: ["usage-records"] });
  }, [client, conversationId]);

  const send = useCallback(
    async (text: string) => {
      if (controller.current) return; // a reply is already streaming: no double submit
      const abort = new AbortController();
      controller.current = abort;
      setState({ ...IDLE, status: "streaming", pendingUserText: text });
      // Events that arrive after a stop are ignored.
      const update = (fn: (s: ChatState) => ChatState) => {
        if (!abort.signal.aborted) setState(fn);
      };
      try {
        await sendMessage(
          conversationId,
          text,
          (event) => {
            switch (event.type) {
              case "message_start":
                update((s) => ({
                  ...s,
                  messageId: event.data.message_id,
                  userMessageId: event.data.user_message_id,
                  sources: event.data.sources,
                }));
                break;
              case "warning":
                update((s) => ({ ...s, warnings: [...s.warnings, event.data] }));
                break;
              case "delta":
                update((s) => ({ ...s, replyText: s.replyText + event.data.text }));
                break;
              case "error":
                update((s) => ({
                  ...s,
                  problem: {
                    code: event.data.code,
                    message: event.data.message,
                    suggested: suggestedFrom(event.data.details),
                  },
                }));
                break;
              case "message_end":
                break;
            }
          },
          abort.signal,
        );
      } catch (error) {
        if (error instanceof ApiError && error.isAbort) {
          setState((s) => ({ ...s, stopped: true }));
        } else if (error instanceof ApiError) {
          setState((s) => ({
            ...s,
            problem: {
              code: error.code,
              message: error.message,
              suggested: suggestedFrom(error.details),
            },
          }));
        } else {
          setState((s) => ({
            ...s,
            problem: {
              code: "client_error",
              message: "The reply could not be shown.",
              suggested: [],
            },
          }));
        }
      } finally {
        controller.current = null;
        // Show what the backend saved (complete, error or cancelled), then drop the local copy.
        await refresh();
        setState((s) => ({ ...s, status: "idle", pendingUserText: null, replyText: "" }));
      }
    },
    [conversationId, refresh],
  );

  const stop = useCallback(() => {
    controller.current?.abort();
  }, []);

  return { state, send, stop };
}
