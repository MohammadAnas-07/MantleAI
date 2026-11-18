import { useQuery } from "@tanstack/react-query";

import type { HandoffNote } from "../lib/api/types";

export type SwitchReason = "user_choice" | "rate_limit" | "context_limit" | "provider_error";

export const noteKey = (conversationId: string) => ["handoff-note", conversationId] as const;

/** The backend sends the note as an untyped object; keep it only if it has the text. */
export function noteFrom(note: Record<string, unknown>): HandoffNote | null {
  if (typeof note.text !== "string") return null;
  return {
    text: note.text,
    from_model: typeof note.from_model === "string" ? note.from_model : "",
    to_model: typeof note.to_model === "string" ? note.to_model : "",
    dropped: Array.isArray(note.dropped)
      ? note.dropped.filter((d): d is string => typeof d === "string")
      : [],
  };
}

/** The note of the last switch made in this browser session, per conversation. */
export function useHandoffNote(conversationId: string): HandoffNote | null {
  const { data } = useQuery<HandoffNote | null>({
    queryKey: noteKey(conversationId),
    queryFn: () => null,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return data ?? null;
}
