"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="error-shell"><div className="error-card"><div className="brand"><span>N</span>NEXUS</div><h1>We couldn’t load your feed.</h1><p>Make sure the NEXUS API is running on port 8000, then try again.</p><button className="primary" onClick={reset}>Retry</button></div></main>;
}
