import type { ReactNode } from "react";

/** The one serif title of a page, with an optional line under it and actions on the right. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start gap-x-4 gap-y-2 border-b border-line pb-4">
      <div className="min-w-0 flex-1 space-y-1">
        <h1 className="font-serif text-title font-normal break-words" dir="auto">
          {title}
        </h1>
        {description ? <div className="max-w-prose text-base text-muted">{description}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** A titled section of a page: sans heading, hairline above when it is not the first. */
export function Section({
  id,
  title,
  children,
  actions,
}: {
  id: string;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={id} className="text-lg">
          {title}
        </h2>
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
