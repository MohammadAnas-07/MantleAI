import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Trash2 } from "lucide-react";
import { useState, type SubmitEvent } from "react";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { FormError, SelectInput, TextInput } from "../../components/ui/Field";
import { QueryError } from "../../components/QueryError";
import { Badge, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { keys, useCredentials, useProviders } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import { formatDateTime } from "../../lib/format";
import { limits } from "../../lib/limits";
import type { Credential } from "../../lib/api/types";
import { KEYS_UNREADABLE, llmErrorText } from "../../lib/llmErrors";

/**
 * Provider keys. The key lives only in this form's state until it is sent; the input is
 * cleared after every submit, and only the last 4 characters ever come back.
 */
export function KeysSection() {
  const client = useQueryClient();
  const providers = useProviders();
  const credentials = useCredentials();
  const [provider, setProvider] = useState("");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [keyError, setKeyError] = useState<string>();
  const [removing, setRemoving] = useState<Credential | null>(null);
  const chosen = provider || providers.data?.[0]?.id || "";

  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.credentials });
    void client.invalidateQueries({ queryKey: keys.providers });
  };
  const add = useMutation({
    mutationFn: (key: string) =>
      api.addCredential({ provider: chosen, label: label.trim(), api_key: key }),
    onSuccess: () => {
      setLabel("");
      refresh();
    },
  });
  const test = useMutation({
    mutationFn: (id: string) => api.testCredential(id),
    onSettled: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCredential(id),
    onSuccess: () => {
      setRemoving(null);
      refresh();
    },
  });

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    const key = apiKey.trim();
    // Clear the field first, whatever happens next: the key must not linger on screen.
    setApiKey("");
    if (key.length < limits.apiKeyMin || key.length > limits.apiKeyMax) {
      setKeyError(
        `A key has ${limits.apiKeyMin} to ${limits.apiKeyMax} characters. Paste it again.`,
      );
      return;
    }
    setKeyError(undefined);
    add.mutate(key);
  };

  return (
    <section aria-labelledby="keys-title" className="space-y-4">
      <h2 id="keys-title" className="text-lg">
        Provider keys
      </h2>
      {credentials.isLoading ? <Skeleton label="Loading keys" /> : null}
      {credentials.isError ? (
        <QueryError
          error={credentials.error}
          onRetry={() => void credentials.refetch()}
          retrying={credentials.isFetching}
        />
      ) : null}
      {credentials.data?.length === 0 ? (
        <EmptyState icon={KeyRound}>
          No keys saved yet. Add one below to chat or index. A free Google AI Studio key is enough
          for both.
        </EmptyState>
      ) : null}
      {credentials.data?.some((c) => !c.readable) ? (
        <p role="alert" className="text-base text-danger">
          {KEYS_UNREADABLE} Remove the old key once a new one works.
        </p>
      ) : null}
      <ul className="divide-y divide-line rounded-lg border border-line text-base empty:hidden">
        {credentials.data?.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
            <span className="font-medium">{c.provider}</span>
            {c.label ? <span>{c.label}</span> : null}
            <span className="code" aria-label={`Key ending in ${c.key_hint}`}>
              ••••{c.key_hint}
            </span>
            {!c.readable ? <Badge kind="danger">can&apos;t be read</Badge> : null}
            {c.last_test_ok === true ? <Badge kind="success">works</Badge> : null}
            {c.last_test_ok === false ? <Badge kind="danger">failed</Badge> : null}
            <span className="text-sm text-muted">tested {formatDateTime(c.last_tested_at)}</span>
            <div className="ml-auto flex gap-1">
              <Button
                size="sm"
                busy={test.isPending && test.variables === c.id}
                onClick={() => {
                  test.mutate(c.id);
                }}
              >
                Test
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Remove the ${c.provider} key ending in ${c.key_hint}`}
                onClick={() => {
                  setRemoving(c);
                }}
                icon={<Trash2 aria-hidden className="size-4" />}
              />
            </div>
          </li>
        ))}
      </ul>
      {test.data && !test.data.ok ? (
        <p role="alert" className="text-base text-danger">
          The test failed:{" "}
          {llmErrorText(test.data.error_code, `error ${test.data.error_code ?? "unknown"}.`)}
        </p>
      ) : null}

      <form
        onSubmit={submit}
        noValidate
        aria-label="Add a provider key"
        className="grid items-start gap-3 rounded-lg bg-sunken p-4 sm:grid-cols-3"
      >
        <h3 className="text-base sm:col-span-3">Add a key</h3>
        <SelectInput
          label="Provider"
          value={chosen}
          onChange={(e) => {
            setProvider(e.target.value);
          }}
        >
          {providers.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.supports_embeddings ? " (chat + embeddings)" : ""}
            </option>
          ))}
        </SelectInput>
        <TextInput
          label="Label (optional)"
          value={label}
          maxLength={limits.credentialLabel}
          onChange={(e) => {
            setLabel(e.target.value);
          }}
        />
        <TextInput
          label="API key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={apiKey}
          maxLength={limits.apiKeyMax}
          onChange={(e) => {
            setApiKey(e.target.value);
          }}
          error={keyError}
          help="Stored encrypted on your machine. Cleared from this form after you submit."
        />
        <div className="space-y-2 sm:col-span-3">
          <FormError message={add.isError ? errorMessage(add.error) : null} />
          <Button type="submit" variant="primary" busy={add.isPending} disabled={!chosen}>
            Save key
          </Button>
        </div>
      </form>

      <ConfirmDialog
        title="Remove this key?"
        open={removing !== null}
        danger
        onCancel={() => {
          setRemoving(null);
        }}
        onConfirm={() => {
          if (removing) remove.mutate(removing.id);
        }}
        confirmLabel="Remove"
        busy={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
      >
        <p>
          The {removing?.provider} key ending in {removing?.key_hint} is deleted. Models of that
          provider stop working until you add a key again.
        </p>
      </ConfirmDialog>
    </section>
  );
}
