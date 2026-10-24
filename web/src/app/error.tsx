"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <section className="page-intro" role="alert">
      <h1>The workspace could not load.</h1>
      <p>Try loading it again. Your local request logs have not been changed.</p>
      <button type="button" onClick={reset}>Try again</button>
    </section>
  );
}
