import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { textOf } from "../../lib/textOf";

/** A block of code with a copy button. Code is always laid out left to right. */
export function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
    },
    [],
  );

  const copy = () => {
    void navigator.clipboard.writeText(textOf(children).replace(/\n$/, "")).then(() => {
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        setCopied(false);
      }, 1500);
    });
  };
  return (
    <div className="relative my-3">
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute top-1.5 right-1.5 inline-flex size-7 items-center justify-center rounded-sm border border-line bg-paper text-muted transition-colors duration-150 ease-out hover:text-text"
      >
        {copied ? (
          <Check aria-hidden className="size-4" />
        ) : (
          <Copy aria-hidden className="size-4" />
        )}
      </button>
      <pre className="overflow-x-auto rounded-lg bg-sunken p-3 pr-11 leading-5" dir="ltr">
        {children}
      </pre>
    </div>
  );
}
