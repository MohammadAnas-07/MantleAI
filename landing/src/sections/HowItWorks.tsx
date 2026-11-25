import { Band } from "../components/Band";
import { FEATURES, STEPS } from "../content";
import { SCREENSHOTS } from "../screenshots";

export function HowItWorks() {
  return (
    <Band id="how-it-works" eyebrow="How it works" title="What Mantle does with a project">
      {/* The steps are an ordered list; the numbered line above them is the diagram. */}
      <ol className="grid gap-0 md:grid-cols-4 md:gap-6">
        {STEPS.map((step, i) => (
          <li key={step.title} className="border-t border-rule py-6 md:border-t-0 md:py-0">
            <div aria-hidden="true" className="mb-4 hidden items-center md:flex">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-ink font-serif text-title">
                {i + 1}
              </span>
              {i < STEPS.length - 1 ? <span className="ml-3 h-px flex-1 bg-ink" /> : null}
            </div>
            <p className="font-serif text-display-sm text-muted md:hidden">{i + 1}</p>
            <h3 className="mt-1 text-title">{step.title}</h3>
            <p className="mt-2 text-ink-2">{step.text}</p>
          </li>
        ))}
      </ol>
    </Band>
  );
}

export function Features() {
  return (
    <Band
      id="features"
      tone="linen"
      eyebrow="What it does today"
      title="Works today, in the API and the web app"
    >
      <ul className="grid gap-x-12 md:grid-cols-2">
        {FEATURES.map((f) => (
          <li key={f.title} className="border-t border-rule py-5">
            <h3 className="text-title">{f.title}</h3>
            <p className="mt-1 max-w-[56ch] text-ink-2">{f.detail}</p>
          </li>
        ))}
      </ul>
      {SCREENSHOTS.length > 0 ? (
        <div className="mt-12 grid gap-8 md:grid-cols-2">
          {SCREENSHOTS.map((s) => (
            <figure key={s.src}>
              <img
                src={s.src}
                alt={s.alt}
                width={s.width}
                height={s.height}
                loading="lazy"
                className="h-auto w-full rounded-[8px] border border-rule"
              />
              <figcaption className="mt-2 text-caption text-muted">{s.alt}</figcaption>
            </figure>
          ))}
        </div>
      ) : null}
    </Band>
  );
}
