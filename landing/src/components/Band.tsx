import type { ReactNode } from "react";

const TONES = {
  paper: "bg-paper",
  linen: "bg-linen",
} as const;

/** One full-width band of the page: an eyebrow, a serif title, then the content. */
export function Band({
  id,
  tone = "paper",
  eyebrow,
  title,
  children,
}: {
  id: string;
  tone?: keyof typeof TONES;
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`${TONES[tone]} py-12 md:py-16`}>
      <div className="mx-auto max-w-page px-4 md:px-6">
        <p className="text-label text-muted">{eyebrow}</p>
        <h2 id={`${id}-title`} className="mt-3 max-w-[22ch] font-serif text-display">
          {title}
        </h2>
        <div className="mt-8 md:mt-10">{children}</div>
      </div>
    </section>
  );
}

/** A text link styled as a button. Solid is the page's main call to action. */
export function ButtonLink({
  href,
  children,
  variant = "outline",
}: {
  href: string;
  children: ReactNode;
  variant?: "solid" | "outline";
}) {
  const look =
    variant === "solid"
      ? "border-ink bg-ink text-on-ink hover:border-ink-2 hover:bg-ink-2 active:translate-y-px"
      : "border-ink bg-transparent text-ink hover:bg-ink hover:text-on-ink active:bg-ink active:text-on-ink";
  return (
    <a
      href={href}
      className={`inline-flex h-12 items-center justify-center rounded-[4px] border px-5 text-label no-underline transition-colors duration-150 ease-out ${look}`}
    >
      {children}
    </a>
  );
}
