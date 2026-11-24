"use client";

import { Play, Plus } from "lucide-react";
import { Content } from "@/lib/types";

export default function ContentCard({ item, index }: { item: Content; index: number }) {
  return (
    <article className="content-card">
      <div className={`poster poster-${item.accent}`}>
        <span className="poster-index">{String(index + 1).padStart(2, "0")}</span>
        <div className="poster-word">{item.title.split(" ").slice(0,2).join(" ")}</div>
        <button className="poster-play" aria-label={`Play ${item.title}`}><Play size={16} fill="currentColor"/></button>
      </div>
      <div className="card-copy">
        <div className="card-title-row"><h3>{item.title}</h3><button aria-label={`Add ${item.title} to list`}><Plus size={16}/></button></div>
        <div className="card-meta"><strong>{Math.round(item.match_score * 100)}%</strong><span>{item.content_type}</span><span>{item.duration_minutes}m</span></div>
      </div>
    </article>
  );
}
