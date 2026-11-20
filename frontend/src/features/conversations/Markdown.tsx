import { Check, Copy } from "lucide-react";
import { isValidElement, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { displayTarget, safeLinkHref } from "../../lib/safeUrl";

/** Plain text of a React tree (the code inside <pre>), for the copy button. */
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(textOf(children).replace(/\n$/, "")).then(() => {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 1500);
    });
  };
  return (
    <div className="group relative my-2">
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute top-1 right-1 rounded-sm border border-line bg-surface p-1 text-muted hover:text-text"
      >
        {copied ? (
          <Check aria-hidden className="size-4" />
        ) : (
          <Copy aria-hidden className="size-4" />
        )}
      </button>
      <pre
        className="overflow-x-auto rounded-sm border-2 border-solid border-line bg-bg p-3"
        dir="ltr"
      >
        {children}
      </pre>
    </div>
  );
}

/**
 * Model output is untrusted. A safe link opens in a new tab without access to this page, and
 * its real address is shown when the text says something else. Any other link is plain text.
 */
function SafeLink({ href, children }: { href: string | undefined; children?: ReactNode }) {
  const safe = safeLinkHref(href);
  if (!safe) {
    return (
      <span>
        {children}{" "}
        <span className="text-xs text-muted">
          (link blocked: {(href ?? "").slice(0, 80) || "no address"})
        </span>
      </span>
    );
  }
  const shown = displayTarget(safe);
  const textIsTarget = textOf(children).trim().replace(/\/$/, "").endsWith(shown);
  return (
    <span>
      <a href={safe} target="_blank" rel="noopener noreferrer" title={safe}>
        {children}
      </a>
      {textIsTarget ? null : <span className="text-xs text-muted"> ({shown})</span>}
    </span>
  );
}

/** Images in model output are never loaded: fetching one could send data to its server. */
function BlockedImage({ src, alt }: { src?: string | undefined; alt?: string | undefined }) {
  return (
    <span className="rounded-sm border border-dashed border-line px-1 text-xs text-muted">
      [image not loaded: {alt?.trim() || "no description"} — {src ?? "no address"}]
    </span>
  );
}

const components: Components = {
  a: ({ href, children }) => <SafeLink href={href}>{children}</SafeLink>,
  img: ({ src, alt }) => <BlockedImage src={typeof src === "string" ? src : undefined} alt={alt} />,
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse text-sm [&_td]:border [&_td]:border-line [&_td]:px-2 [&_th]:border [&_th]:border-line [&_th]:px-2">
        {children}
      </table>
    </div>
  ),
};

// URLs reach the components unchanged, so a blocked one can be shown as text; the components
// decide what may become an href (SafeLink) and never render an <img> (BlockedImage).
const keepUrl = (url: string) => url;

/**
 * Renders model output as Markdown. Raw HTML is dropped (skipHtml), links are checked by
 * SafeLink, images are never loaded, and nothing uses dangerouslySetInnerHTML.
 */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-mantle space-y-2 break-words [&_code]:rounded-sm [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={keepUrl}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
