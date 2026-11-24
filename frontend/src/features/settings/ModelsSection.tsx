import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Checkbox, SelectInput } from "../../components/ui/Field";
import { Badge, Banner, Skeleton } from "../../components/ui/Feedback";
import { keys, useModelSettings } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import { formatCost, formatTokens } from "../../lib/format";
import type { ModelSettingsPatch } from "../../lib/api/types";

export function ModelsSection() {
  const client = useQueryClient();
  const info = useModelInfo();
  const settings = useModelSettings();
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.updateModel(id, { enabled }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.models });
    },
  });
  const save = useMutation({
    mutationFn: (patch: ModelSettingsPatch) => api.updateModelSettings(patch),
    onSuccess: (data) => {
      client.setQueryData(keys.modelSettings, data);
      void client.invalidateQueries({ queryKey: keys.projects });
    },
  });

  return (
    <section aria-labelledby="models-title" className="space-y-3">
      <h2 id="models-title" className="text-base">
        Models
      </h2>
      {settings.data ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectInput
            label="Utility model (writes summaries)"
            value={settings.data.utility_model_id ?? ""}
            onChange={(e) => {
              save.mutate({ utility_model_id: e.target.value || null });
            }}
            help="Empty: the conversation's own model writes them."
          >
            <option value="">The conversation&apos;s model</option>
            {info.chatModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name}
              </option>
            ))}
          </SelectInput>
          <SelectInput
            label="Embedding model (indexing)"
            value={settings.data.embedding_model_id ?? ""}
            onChange={(e) => {
              save.mutate({ embedding_model_id: e.target.value || null });
            }}
            help="Changing it makes indexed projects need a re-index."
          >
            <option value="">Server default (DEFAULT_EMBEDDING_MODEL)</option>
            {info.embeddingModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name}
                {info.hasKey(m) ? "" : " - no key"}
              </option>
            ))}
          </SelectInput>
          <Checkbox
            label="Background summaries"
            checked={settings.data.background_summary_enabled}
            onChange={(e) => {
              save.mutate({ background_summary_enabled: e.target.checked });
            }}
            help="Off: no model calls in the background; the summary is written when you switch models."
          />
        </div>
      ) : (
        <Skeleton label="Loading model settings" />
      )}
      {save.isError ? <Banner kind="danger">{errorMessage(save.error)}</Banner> : null}

      {info.isLoading ? <Skeleton label="Loading models" /> : null}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Model catalog</caption>
          <thead>
            <tr className="eyebrow">
              <th scope="col">Model</th>
              <th scope="col">Kind</th>
              <th scope="col">Context</th>
              <th scope="col">$ / M tokens in, out</th>
              <th scope="col">Key</th>
              <th scope="col">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {[...info.byId.values()].map((m) => (
              <tr key={m.id}>
                <td>{m.display_name}</td>
                <td>{m.kind}</td>
                <td>{formatTokens(m.context_window)}</td>
                <td>
                  {formatCost(m.input_cost_per_mtok)}, {formatCost(m.output_cost_per_mtok)}
                </td>
                <td>{info.hasKey(m) ? <Badge kind="success">yes</Badge> : <Badge>no</Badge>}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Enable ${m.display_name}`}
                    checked={m.enabled}
                    disabled={toggle.isPending}
                    onChange={(e) => {
                      toggle.mutate({ id: m.id, enabled: e.target.checked });
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {toggle.isError ? <Banner kind="danger">{errorMessage(toggle.error)}</Banner> : null}
    </section>
  );
}
