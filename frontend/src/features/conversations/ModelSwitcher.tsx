import { useId, useState } from "react";

import { useConversation } from "../../hooks/queries";
import { useModelInfo } from "../../hooks/useModelInfo";
import { CONTROL } from "../../components/ui/Field";
import { formatTokens } from "../../lib/format";
import { SwitchDialog } from "./switching";

/** The model dropdown in the top bar. Picking a model opens the switch preview first. */
export function ModelSwitcher({ conversationId }: { conversationId: string }) {
  const id = useId();
  const conversation = useConversation(conversationId);
  const models = useModelInfo();
  const [target, setTarget] = useState<string | null>(null);
  const current = conversation.data?.current_model_id ?? "";

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm font-normal text-muted">
        Model
      </label>
      <select
        id={id}
        value={current}
        disabled={!conversation.data || conversation.data.generating}
        onChange={(e) => {
          if (e.target.value !== current) setTarget(e.target.value);
        }}
        className={`${CONTROL} h-8 max-w-64`}
      >
        {models.chatModels.map((m) => (
          <option key={m.id} value={m.id}>
            {m.display_name} · {formatTokens(m.context_window)}
            {models.hasKey(m) ? "" : " · no key"}
          </option>
        ))}
      </select>
      <SwitchDialog
        key={target ?? "none"}
        conversationId={conversationId}
        targetModelId={target}
        onClose={() => {
          setTarget(null);
        }}
      />
    </div>
  );
}
