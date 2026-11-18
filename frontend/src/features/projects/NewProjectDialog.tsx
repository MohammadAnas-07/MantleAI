import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type SubmitEvent } from "react";
import { useNavigate } from "react-router";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { FormError, TextArea, TextInput } from "../../components/ui/Field";
import { keys } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { ApiError, errorMessage, fieldErrors } from "../../lib/api/errors";
import { limits } from "../../lib/limits";

/** Create a project. The folder is typed as text: a browser can't hand out a folder path. */
export function NewProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [description, setDescription] = useState("");
  const [nameError, setNameError] = useState<string>();

  const create = useMutation({
    mutationFn: () =>
      api.createProject({
        name: name.trim(),
        description: description.trim() || null,
        root_path: rootPath.trim() || null,
      }),
    onSuccess: (project) => {
      void client.invalidateQueries({ queryKey: keys.projects });
      setName("");
      setRootPath("");
      setDescription("");
      onClose();
      void navigate(`/projects/${project.id}`);
    },
  });

  const errors = fieldErrors(create.error);
  const pathError =
    errors.root_path ??
    (create.error instanceof ApiError && create.error.code === "invalid_source_path"
      ? create.error.message
      : undefined);
  const otherError = create.error && !pathError && !errors.name ? errorMessage(create.error) : null;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setNameError("Give the project a name.");
      return;
    }
    setNameError(undefined);
    create.mutate();
  };

  return (
    <Dialog title="New project" open={open} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <TextInput
          label="Name"
          value={name}
          maxLength={limits.projectName}
          required
          onChange={(e) => {
            setName(e.target.value);
          }}
          error={nameError ?? errors.name}
        />
        <TextInput
          label="Source folder (optional)"
          value={rootPath}
          maxLength={limits.path}
          placeholder="C:\code\my-app"
          spellCheck={false}
          onChange={(e) => {
            setRootPath(e.target.value);
          }}
          help="The full path of the folder to index. Type or paste it."
          error={pathError}
        />
        <TextArea
          label="Description (optional)"
          value={description}
          maxLength={limits.projectDescription}
          onChange={(e) => {
            setDescription(e.target.value);
          }}
        />
        <FormError message={otherError} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={create.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
