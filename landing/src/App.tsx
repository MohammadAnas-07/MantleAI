import { Nav } from "./components/Nav";
import { Hero, Problem } from "./sections/Hero";

export function App() {
  return (
    <>
      <div id="top" />
      <Nav />
      <main id="main" tabIndex={-1} className="focus:outline-none">
        <Hero />
        <Problem />
      </main>
    </>
  );
}
