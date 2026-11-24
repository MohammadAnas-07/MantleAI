import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { NAV, REPO } from "../content";

/** Which nav section is on screen. Without IntersectionObserver (tests, old browsers) none. */
function useCurrentSection(ids: readonly string[]): string | null {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    if (typeof IntersectionObserver !== "function") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        const top = visible.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setCurrent(top.target.id);
      },
      // A section counts as current while it crosses the band just under the header.
      { rootMargin: "-88px 0px -60% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => {
      observer.disconnect();
    };
  }, [ids]);
  return current;
}

const IDS = NAV.map((n) => n.id);

const LINK =
  "inline-flex h-11 items-center px-2 text-label no-underline transition-colors duration-150 ease-out";

export function Nav() {
  const current = useCurrentSection(IDS);
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const button = useRef<HTMLButtonElement>(null);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) button.current?.focus();
  };
  const onMenuKey = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    }
  };

  const linkClass = (id: string) =>
    `${LINK} ${current === id ? "text-ink underline decoration-accent decoration-2 underline-offset-8" : "text-ink-2 hover:text-ink hover:underline hover:decoration-rule hover:decoration-2 hover:underline-offset-8"}`;

  return (
    <header
      onKeyDown={open ? onMenuKey : undefined}
      className="sticky top-0 z-40 border-b border-rule bg-paper/85 backdrop-blur-[16px]"
    >
      <a
        href="#main"
        className="absolute top-2 left-2 z-50 -translate-y-24 rounded-[4px] bg-paper px-4 py-3 text-label text-ink focus:translate-y-0"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-16 max-w-page items-center gap-4 px-4 md:h-18 md:px-6">
        <a href="#top" className="font-serif text-wordmark text-ink no-underline">
          Mantle
        </a>
        <nav aria-label="Sections" className="ml-auto hidden items-center gap-1 min-[900px]:flex">
          <ul className="flex items-center gap-1">
            {NAV.map((n) => (
              <li key={n.id}>
                <a
                  href={`#${n.id}`}
                  aria-current={current === n.id ? "true" : undefined}
                  className={linkClass(n.id)}
                >
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
          <a
            href={REPO}
            className="ml-3 inline-flex h-11 items-center rounded-[4px] border border-ink px-4 text-label text-ink no-underline transition-colors duration-150 ease-out hover:bg-ink hover:text-on-ink"
          >
            GitHub
          </a>
        </nav>
        <button
          ref={button}
          type="button"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => {
            setOpen((v) => !v);
          }}
          className="ml-auto inline-flex h-11 items-center rounded-[4px] border border-field px-4 text-label text-ink min-[900px]:hidden"
        >
          {open ? "Close menu" : "Menu"}
        </button>
      </div>
      {open ? (
        <nav
          id={menuId}
          aria-label="Menu"
          className="border-t border-rule bg-paper shadow-overlay min-[900px]:hidden"
        >
          <ul className="mx-auto max-w-page divide-y divide-rule px-4">
            {NAV.map((n) => (
              <li key={n.id}>
                <a
                  href={`#${n.id}`}
                  aria-current={current === n.id ? "true" : undefined}
                  onClick={() => {
                    close(false);
                  }}
                  className="flex h-12 items-center text-body text-ink no-underline"
                >
                  {n.label}
                </a>
              </li>
            ))}
            <li>
              <a href={REPO} className="flex h-12 items-center text-body text-ink no-underline">
                GitHub
              </a>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
