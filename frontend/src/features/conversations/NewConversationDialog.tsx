import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type SubmitEvent } from "react";
import { useNavigate } from "react-router";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { FormError, SelectInput, TextInput } from "../../components/ui/Field";
import { keys, useProject } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import { formatTokens } from "../../lib/format";
import { limits } from "../../lib/limits";

export function NewConversationDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const models = useModelInfo();
  const [title, setTitle] = useState("");
  const [picked, setPicked] = useState<string>("");
  // The project's default model unless the user picked another one.
  const modelId = picked || project.data?.default_model_id || models.chatModels[0]?.id || "";

  const create = useMutation({
    mutationFn: () => api.createConversation(projectId, { model_id: modelId, title: title.trim() }),
    onSuccess: (conversation) => {
      void client.invalidateQueries({ queryKey: keys.conversations(projectId) });
      setTitle("");
      onClose();
      void navigate(`/projects/${projectId}/c/${conversation.id}`);
    },
  });

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (modelId) create.mutate();
  };

  const model = models.byId.get(modelId);
  return (
    <Dialog title="New conversation" open={open} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <TextInput
          label="Title (optional)"
          value={title}
          maxLength={limits.conversationTitle}
          onChange={(e) => {
            setTitle(e.target.value);
          }}
          help="Left empty, the first message becomes the title."
        />
        <SelectInput
          label="Model"
          value={modelId}
          onChange={(e) => {
            setPicked(e.target.value);
          }}
          help={
            model && !models.hasKey(model)
              ? `No ${model.provider} key saved: add one in Settings.`
              : undefined
          }
        >
          {models.chatModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} ({formatTokens(m.context_window)})
              {models.hasKey(m) ? "" : " - no key"}
            </option>
          ))}
        </SelectInput>
        <FormError message={create.error ? errorMessage(create.error) : null} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={create.isPending} disabled={!modelId}>
            Create
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
