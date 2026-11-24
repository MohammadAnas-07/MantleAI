import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Banner, Skeleton } from "../../components/ui/Feedback";
import { keys, useHandoffPreview } from "../../hooks/queries";
import { noteFrom, noteKey } from "../../hooks/useHandoffNote";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import { formatTokens } from "../../lib/format";
import type { HandoffNote } from "../../lib/api/types";

import type { SwitchReason } from "../../hooks/useHandoffNote";

/**
 * Shows what would carry over to `targetModelId` and switches only when the user confirms.
 * Mantle never switches by itself.
 */
export function SwitchDialog({
  conversationId,
  targetModelId,
  reason = "user_choice",
  onClose,
}: {
  conversationId: string;
  targetModelId: string | null;
  reason?: SwitchReason;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const models = useModelInfo();
  const preview = useHandoffPreview(conversationId, targetModelId);
  const target = targetModelId ? models.byId.get(targetModelId) : undefined;

  const doSwitch = useMutation({
    mutationFn: () => api.switchModel(conversationId, targetModelId ?? "", reason),
    onSuccess: (result) => {
      client.setQueryData(keys.conversation(conversationId), result.conversation);
      client.setQueryData<HandoffNote | null>(
        noteKey(conversationId),
        noteFrom(result.handoff.note),
      );
      void client.invalidateQueries({ queryKey: ["preview", conversationId] });
      void client.invalidateQueries({ queryKey: keys.messages(conversationId) });
      onClose();
    },
  });

  const data = preview.data;
  return (
    <Dialog
      title={`Switch to ${target?.display_name ?? "model"}`}
      open={Boolean(targetModelId)}
      onClose={onClose}
    >
      {preview.isLoading ? <Skeleton label="Loading the handoff preview" /> : null}
      {preview.isError ? <Banner kind="danger">{errorMessage(preview.error)}</Banner> : null}
      {data ? (
        <div className="space-y-3 text-base">
          <p>
            {formatTokens(data.total_tokens)} of {formatTokens(data.budget)} tokens would be sent
            (context window {formatTokens(data.context_window)}).
          </p>
          {data.dropped.length > 0 ? (
            <p>
              Left out to fit: {data.dropped.length} item{data.dropped.length === 1 ? "" : "s"} (see
              the Context tab).
            </p>
          ) : (
            <p>Nothing is left out.</p>
          )}
          {data.will_build_summary ? (
            <Banner kind="info">
              Background summaries are off, so the new model writes the summary now (about{" "}
              {formatTokens(data.summary_input_tokens)} input tokens).
            </Banner>
          ) : null}
          {!data.has_key ? (
            <Banner kind="warning">
              No API key for this model&apos;s provider. Add one in Settings.
            </Banner>
          ) : null}
          <p className="text-muted">The current model is not called during the switch.</p>
        </div>
      ) : null}
      {doSwitch.isError ? (
        <p role="alert" className="mt-3 text-base text-danger">
          {errorMessage(doSwitch.error)}
        </p>
      ) : null}
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="primary"
          busy={doSwitch.isPending}
          disabled={!data?.has_key}
          onClick={() => {
            doSwitch.mutate();
          }}
        >
          Switch
        </Button>
      </div>
    </Dialog>
  );
}
