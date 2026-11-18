import { Check, Copy } from "lucide-react";
import { isValidElement, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

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

const components: Components = {
  // Model output is untrusted: links open in a new tab without access to this page.
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse text-sm [&_td]:border [&_td]:border-line [&_td]:px-2 [&_th]:border [&_th]:border-line [&_th]:px-2">
        {children}
      </table>
    </div>
  ),
};

/**
 * Renders model output as Markdown. Raw HTML is dropped (skipHtml), react-markdown's default
 * URL filter removes javascript: links, and nothing uses dangerouslySetInnerHTML.
 */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-mantle space-y-2 break-words [&_code]:rounded-sm [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
