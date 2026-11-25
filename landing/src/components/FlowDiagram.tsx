import { useId } from "react";

/**
 * The hero's picture of the flow: project data goes into the context builder, which writes a
 * prompt for whichever model you pick; a switch hands the same context to another model. It
 * repeats what the text says, so it is described for screen readers but carries nothing extra.
 */
export function FlowDiagram() {
  const titleId = useId();
  const descId = useId();
  return (
    <svg
      viewBox="0 0 480 360"
      role="img"
      aria-labelledby={`${titleId} ${descId}`}
      className="h-auto w-full max-w-[480px] text-ink"
    >
      <title id={titleId}>How Mantle builds a prompt</title>
      <desc id={descId}>
        Your project data, stored in your own PostgreSQL database, goes into the context builder.
        The builder writes a prompt that fits the chosen model. When you switch models, the next
        model gets the same context; the old model is not called.
      </desc>
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0 0 10 5 0 10z" fill="currentColor" />
        </marker>
      </defs>

      {/* Project data, on your machine */}
      <rect x="8" y="24" width="168" height="248" rx="8" className="fill-linen" />
      <text x="24" y="52" className="fill-muted text-[13px]">
        Your PostgreSQL
      </text>
      {[
        "Requirements",
        "Decisions",
        "Tasks",
        "Rolling summary",
        "Indexed code",
        "Project profile",
      ].map((item, i) => (
        <g key={item}>
          <line x1="24" x2="160" y1={70 + i * 32} y2={70 + i * 32} className="stroke-rule" />
          <text x="24" y={90 + i * 32} className="fill-ink text-[14px]">
            {item}
          </text>
        </g>
      ))}

      {/* Context builder */}
      <line
        x1="178"
        y1="148"
        x2="214"
        y2="148"
        stroke="currentColor"
        strokeWidth="1.5"
        markerEnd="url(#arrow)"
      />
      <rect x="216" y="108" width="112" height="80" rx="4" className="fill-ink" />
      <text x="272" y="142" textAnchor="middle" className="fill-on-ink text-[14px]">
        Context
      </text>
      <text x="272" y="162" textAnchor="middle" className="fill-on-ink text-[14px]">
        builder
      </text>

      {/* Models */}
      <line
        x1="330"
        y1="148"
        x2="366"
        y2="100"
        stroke="currentColor"
        strokeWidth="1.5"
        markerEnd="url(#arrow)"
      />
      <rect x="368" y="64" width="104" height="56" rx="4" fill="none" stroke="currentColor" />
      <text x="420" y="88" textAnchor="middle" className="fill-ink text-[14px]">
        Model A
      </text>
      <text x="420" y="106" textAnchor="middle" className="fill-muted text-[12px]">
        hits its limit
      </text>

      <line
        x1="330"
        y1="148"
        x2="366"
        y2="208"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="0"
        markerEnd="url(#arrow)"
      />
      <rect x="368" y="184" width="104" height="56" rx="4" fill="none" stroke="currentColor" />
      <text x="420" y="208" textAnchor="middle" className="fill-ink text-[14px]">
        Model B
      </text>
      <text x="420" y="226" textAnchor="middle" className="fill-muted text-[12px]">
        same context
      </text>

      {/* The switch */}
      <path
        d="M420 122 V182"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        markerEnd="url(#arrow)"
      />
      <text x="428" y="156" className="fill-muted text-[12px]">
        switch
      </text>

      <text x="8" y="312" className="fill-muted text-[13px]">
        OpenAI, Anthropic and Google through LiteLLM. Real runs: Gemini only.
      </text>
      <text x="8" y="334" className="fill-muted text-[13px]">
        The old model is not called during a switch.
      </text>
    </svg>
  );
}
