import { ButtonLink } from "../components/Band";
import { FlowDiagram } from "../components/FlowDiagram";
import { HERO, PROBLEM, REPO } from "../content";

export function Hero() {
  return (
    <section aria-labelledby="hero-title" className="bg-paper py-16 md:py-24">
      <div className="mx-auto grid max-w-page items-center gap-12 px-4 md:px-6 min-[900px]:grid-cols-[1.15fr_1fr]">
        <div>
          <p className="text-label text-muted">{HERO.eyebrow}</p>
          <h1 id="hero-title" className="mt-4 max-w-[16ch] font-serif text-hero">
            {HERO.title}
          </h1>
          <p className="mt-6 max-w-[56ch] text-lead text-ink-2">{HERO.lead}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href={REPO} variant="solid">
              View on GitHub
            </ButtonLink>
            <ButtonLink href="#setup">Quick start</ButtonLink>
          </div>
          <p className="mt-4 text-caption text-muted">{HERO.note}</p>
        </div>
        <FlowDiagram />
      </div>
    </section>
  );
}

export function Problem() {
  return (
    <section id="problem" aria-labelledby="problem-title" className="bg-linen py-12 md:py-16">
      <div className="mx-auto max-w-page px-4 md:px-6">
        <p className="text-label text-muted">The problem</p>
        <h2 id="problem-title" className="mt-3 max-w-[22ch] font-serif text-display">
          {PROBLEM.title}
        </h2>
        <div className="mt-8 max-w-[68ch] space-y-4 text-lead text-ink-2">
          {PROBLEM.paragraphs.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </div>
      </div>
    </section>
  );
}
