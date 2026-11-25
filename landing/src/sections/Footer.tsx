import { Band } from "../components/Band";
import { FAQ, FOOTER } from "../content";

export function Faq() {
  return (
    <Band id="faq" eyebrow="Questions" title="Before you try it">
      <div className="max-w-[68ch]">
        {FAQ.map((item) => (
          <details key={item.q} className="group border-t border-rule">
            <summary className="flex min-h-12 cursor-pointer items-center justify-between gap-4 py-3 text-title marker:content-none">
              <h3 className="text-title">{item.q}</h3>
              <span aria-hidden="true" className="text-muted group-open:rotate-45">
                +
              </span>
            </summary>
            <p className="pb-5 text-ink-2">{item.a}</p>
          </details>
        ))}
      </div>
    </Band>
  );
}

export function Footer() {
  return (
    <footer className="band-ink bg-ink py-16 text-on-ink">
      <div className="mx-auto max-w-page px-4 md:px-6">
        <p className="max-w-[24ch] font-serif text-display">{FOOTER.statement}</p>
        <div className="mt-12 grid grid-cols-2 gap-8 md:grid-cols-3">
          {FOOTER.columns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h2 className="text-label text-pebble">{col.title}</h2>
              <ul className="mt-3 space-y-1">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <a
                      href={l.href}
                      className="inline-flex min-h-11 items-center text-label text-on-ink no-underline hover:underline"
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="mt-12 border-t border-ink-rule pt-6 text-caption text-pebble">
          <p>{FOOTER.builder}</p>
          <p className="mt-1">{FOOTER.licence}</p>
        </div>
      </div>
    </footer>
  );
}
