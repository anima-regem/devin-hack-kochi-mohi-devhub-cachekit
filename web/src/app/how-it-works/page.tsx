import Link from "next/link";

export default function Method() {
  return (
    <article className="method">
      <Link className="text-link" href="/">Back to workspace</Link>
      <h1>Follow the shared prefix.</h1>
      <p className="lede">
        Prefix caching lets a server reuse earlier work when the beginning of a
        request matches one it has already processed.
      </p>
      <h2>Find the changing content</h2>
      <p>
        The deterministic engine groups rendered requests by call site, aligns their
        content, and identifies changing spans before stable instructions. Its
        analysis runs locally with a fixed tokenizer and configuration.
      </p>
      <h2>Verify a proposed fix</h2>
      <p>
        Findings become a redacted task for a coding agent. The verifier can
        render the recorded inputs again, check that content is preserved, and
        run the project tests. A required behavioral guard checks golden outputs; missing evidence blocks approval. A human approves the exact diff.
      </p>
      <h2>Measure the difference</h2>
      <p>
        Cache estimates are simulated. Latency and serving cost require a measured
        replay on vLLM before and after the fix. Every published result must link
        to a saved run and its metadata.
      </p>
      <h2>Current limitations</h2>
      <ul>
        <li>The local analysis and fix-review workflow is implemented. An actual application fix, live golden inference and a BEFORE/AFTER performance replay are still pending.</li>
        <li>GPU smoke testing confirms prefix reuse, but establishes no speedup or savings.</li>
        <li>Moving instructions can change model behavior even when every word is preserved.</li>
        <li>Concurrent requests, eviction, and routing can affect real cache reuse.</li>
        <li>Raw logs must remain on the local machine or Modal; agent tasks use redacted evidence.</li>
      </ul>
    </article>
  );
}
