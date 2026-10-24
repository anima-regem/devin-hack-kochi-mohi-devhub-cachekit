import Link from "next/link";

export default function Home() {
  return (
    <>
      <section className="page-intro">
        <h1>Find where reuse stops.</h1>
        <p className="lede">
          Small changes at the start of a prompt can make a server process the same
          instructions again. cachekit traces those changes back to their cause.
        </p>
      </section>

      <section className="empty-state" aria-labelledby="empty-title">
        <div className="prompt-sample" aria-label="Illustrative prompt structure, not an analyzed request">
          <span className="sample-label">Illustrative prompt</span>
          <div className="prompt-line dynamic"><span>Current time</span><span>changes</span></div>
          <div className="prompt-line dynamic"><span>Customer context</span><span>changes</span></div>
          <div className="prompt-line stable"><span>Company policies</span><span>stays the same</span></div>
          <div className="prompt-line"><span>User question</span><span>changes</span></div>
        </div>
        <div className="empty-copy">
          <h2 id="empty-title">No report loaded yet.</h2>
          <p>
            Start with a request log from the demo app. The analysis pipeline is
            being connected; findings and cache estimates will appear here when
            a real report is available.
          </p>
          <Link className="text-link" href="/how-it-works">Read the method and limitations</Link>
        </div>
      </section>

      <section className="prepare" aria-labelledby="prepare-title">
        <h2 id="prepare-title">Prepare a local request log</h2>
        <p>
          The helpdesk demo generates fictional traffic and saves its inputs so
          the same requests can be rendered again after a fix.
        </p>
        <pre><code>uv run python -m demo_app.traffic --out data/demo</code></pre>
        <p className="supporting-text">
          Run from the repository root. Generated traffic is a test fixture;
          performance results require a separate measured replay.
        </p>
      </section>
    </>
  );
}
