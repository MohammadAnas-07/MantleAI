import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "../../components/ui/CodeBlock";
import { displayTarget, safeLinkHref } from "../../lib/safeUrl";
import { textOf } from "../../lib/textOf";

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
        <span className="text-sm text-muted">
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
      {textIsTarget ? null : <span className="text-sm text-muted"> ({shown})</span>}
    </span>
  );
}

/** Images in model output are never loaded: fetching one could send data to its server. */
function BlockedImage({ src, alt }: { src?: string | undefined; alt?: string | undefined }) {
  return (
    <span className="rounded-sm bg-sunken px-1 text-sm text-muted">
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
      <table className="border-collapse text-sm [&_td]:border [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-line [&_th]:bg-sunken [&_th]:px-2 [&_th]:py-1">
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
    <div className="space-y-3 break-words [&_:not(pre)>code]:rounded-sm [&_:not(pre)>code]:bg-sunken [&_:not(pre)>code]:px-1 [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-3 [&_blockquote]:text-text-2 [&_h1]:text-lg [&_h2]:text-lg [&_h3]:text-md [&_h3]:font-medium [&_li]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
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
