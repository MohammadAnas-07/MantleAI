import { Nav } from "./components/Nav";
import { Details } from "./sections/DetailsGroup";
import { Hero, Problem } from "./sections/Hero";
import { Features, HowItWorks } from "./sections/HowItWorks";

export function App() {
  return (
    <>
      <div id="top" />
      <Nav />
      <main id="main" tabIndex={-1} className="focus:outline-none">
        <Hero />
        <Problem />
        <HowItWorks />
        <Features />
        <Details />
      </main>
    </>
  );
}
