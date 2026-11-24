import { Info, Play, Sparkles } from "lucide-react";
import { Content } from "@/lib/types";

export default function Hero({ item }: { item: Content }) {
  return (
    <section className={`hero poster-${item.accent}`} id="top">
      <div className="hero-grid" />
      <div className="orb orb-one"/><div className="orb orb-two"/>
      <div className="hero-content">
        <div className="eyebrow"><Sparkles size={14}/> NEXUS ORIGINAL • #1 FOR YOU TODAY</div>
        <h1>{item.title}</h1>
        <div className="metadata"><strong>{Math.round(item.match_score * 100)}% Match</strong><span>{item.year}</span><span>{item.maturity_rating}</span><span>{item.duration_minutes} min</span><span>{item.genre}</span></div>
        <p>{item.synopsis}</p>
        <div className="hero-actions"><button className="primary"><Play fill="currentColor" size={18}/> Play</button><button className="secondary"><Info size={19}/> More Info</button></div>
        <div className="because"><span>✦</span><div><small>WHY NEXUS PICKED THIS</small><p>You gravitate toward intelligent sci-fi, technology-driven mysteries, and high-concept stories.</p></div></div>
      </div>
      <div className="hero-mark"><span>NX</span><small>PERSONALIZED PREMIERE</small></div>
    </section>
  );
}
