import { useEffect, useRef, useState } from "react";

type CopyState = "idle" | "copied" | "failed";

const LABEL: Record<CopyState, string> = { idle: "Copy", copied: "Copied", failed: "Copy failed" };
const ANNOUNCE: Record<CopyState, string> = {
  idle: "",
  copied: "Copied to the clipboard.",
  failed: "Copy failed. Select the text and copy it by hand.",
};

/** Commands in a dark block, with a copy button that copies exactly the text shown. */
export function CodeBlock({ code, label }: { code: string; label: string }) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
    },
    [],
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setState("copied");
    } catch {
      setState("failed");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setState("idle");
    }, 2000);
  };

  return (
    <figure className="min-w-0">
      <div className="flex items-center justify-between gap-2 rounded-t-[4px] bg-charcoal pl-4">
        <figcaption className="text-caption text-pebble">{label}</figcaption>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={`${LABEL[state]}: ${label}`}
          className="h-11 min-w-11 rounded-[4px] px-3 text-label text-on-ink transition-colors duration-150 ease-out hover:bg-ink focus-visible:outline-accent-on-ink"
        >
          {LABEL[state]}
        </button>
      </div>
      <pre
        dir="ltr"
        className="overflow-x-auto rounded-b-[4px] bg-charcoal px-4 pt-1 pb-4 leading-relaxed text-code"
      >
        <code>{code}</code>
      </pre>
      <p aria-live="polite" className="sr-only">
        {ANNOUNCE[state]}
      </p>
    </figure>
  );
}
