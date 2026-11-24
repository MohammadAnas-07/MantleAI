import { Band } from "../components/Band";
import { CodeBlock } from "../components/CodeBlock";
import {
  BACKEND_COMMANDS,
  blob,
  FRONTEND_COMMANDS,
  NUMBERS,
  PREREQUISITES,
  PRIVACY,
  STATUS,
} from "../content";

export function Privacy() {
  return (
    <Band id="privacy" eyebrow="Privacy and security" title={PRIVACY.title}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left">
          <caption className="sr-only">What Mantle sends, to whom and when</caption>
          <thead>
            <tr className="text-label text-muted">
              <th scope="col" className="py-3 pr-6 font-medium">
                What
              </th>
              <th scope="col" className="py-3 pr-6 font-medium">
                Goes to
              </th>
              <th scope="col" className="py-3 font-medium">
                When
              </th>
            </tr>
          </thead>
          <tbody>
            {PRIVACY.rows.map((r) => (
              <tr key={r.what} className="border-t border-rule align-top">
                <th scope="row" className="py-3 pr-6 font-normal">
                  {r.what}
                </th>
                <td className="py-3 pr-6 text-ink-2">{r.to}</td>
                <td className="py-3 text-ink-2">{r.when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-12 grid gap-10 md:grid-cols-2">
        <div>
          <h3 className="text-title">What stays on your machine</h3>
          <ul className="mt-3 space-y-2 text-ink-2">
            {PRIVACY.local.map((line) => (
              <li key={line} className="border-t border-rule pt-2">
                {line}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-title">Before you index a project</h3>
          <p className="mt-3 border-l-2 border-ink pl-4 text-ink">{PRIVACY.warning}</p>
          <p className="mt-4 text-ink-2">{PRIVACY.skipped}</p>
          <p className="mt-4">
            <a href={blob("docs/security.md")}>Read the security notes on GitHub</a>
          </p>
        </div>
      </div>
    </Band>
  );
}

export function Setup() {
  return (
    <Band id="setup" tone="linen" eyebrow="Setup" title="Run it on your own machine">
      <div className="grid gap-10 min-[900px]:grid-cols-[1fr_2fr]">
        <div className="space-y-6">
          <div>
            <h3 className="text-title">You need</h3>
            <ul className="mt-3 space-y-2 text-ink-2">
              {PREREQUISITES.map((p) => (
                <li key={p} className="border-t border-rule pt-2">
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <p className="text-ink-2">
            The commands are for Windows PowerShell. Paste the generated key after{" "}
            <code>MASTER_ENCRYPTION_KEY=</code> in <code>backend\.env</code>. Without it the API
            won&apos;t start, and if you lose it, saved provider keys can&apos;t be read.
          </p>
        </div>
        <div className="min-w-0 space-y-6">
          <CodeBlock label="1. Database and API" code={BACKEND_COMMANDS} />
          <CodeBlock label="2. Web app, in a second terminal" code={FRONTEND_COMMANDS} />
          <div>
            <h3 className="text-title">3. Add a provider key</h3>
            <p className="mt-2 max-w-[60ch] text-ink-2">
              Open <code>http://127.0.0.1:5173</code> and add a provider key in the settings. A free
              Google AI Studio key is enough for chat and for indexing.
            </p>
          </div>
          <p>
            <a href={blob("docs/setup.md")}>Every step explained, with common errors, on GitHub</a>
          </p>
        </div>
      </div>
    </Band>
  );
}

const COLUMNS = [
  { title: "Works today", items: STATUS.works },
  { title: "Planned, not built", items: STATUS.planned },
  { title: "Known limits", items: STATUS.limits },
];

export function Status() {
  return (
    <Band id="status" eyebrow="Status and limits" title="Version 0.1 is not finished">
      <div className="grid gap-10 md:grid-cols-3">
        {COLUMNS.map((c) => (
          <div key={c.title}>
            <h3 className="text-title">{c.title}</h3>
            <ul className="mt-3 text-ink-2">
              {c.items.map((item) => (
                <li key={item} className="border-t border-rule py-2">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-8">
        <a href={blob("docs/roadmap.md")}>The roadmap on GitHub</a>
      </p>
    </Band>
  );
}

export function Numbers() {
  return (
    <Band id="numbers" tone="linen" eyebrow="Measured numbers" title="What was measured, and how">
      <p className="max-w-[68ch] text-ink-2">
        {NUMBERS.date} Each number keeps its conditions. There is no real-use evaluation yet.
      </p>
      <dl className="mt-6">
        {NUMBERS.items.map((n) => (
          <div
            key={n.label}
            className="grid gap-2 border-t border-rule py-5 md:grid-cols-[1fr_auto] md:gap-8"
          >
            <dt className="md:order-1">
              <span className="block text-title">{n.label}</span>
              <span className="mt-1 block max-w-[60ch] text-caption text-muted">{n.condition}</span>
            </dt>
            <dd className="font-serif text-display md:order-2 md:text-right">{n.value}</dd>
          </div>
        ))}
      </dl>
    </Band>
  );
}
