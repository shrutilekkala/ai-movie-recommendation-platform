import { ChevronRight } from "lucide-react";
import ContentCard from "./ContentCard";
import { FeedSection } from "@/lib/types";

export default function ContentRail({ section }: { section: FeedSection }) {
  return <section className="rail" id={section.key === "top-picks" ? "foryou" : undefined}>
    <div className="rail-heading"><h2>{section.title}</h2><button>Explore <ChevronRight size={16}/></button></div>
    <div className="rail-track">{section.items.map((item, index) => <ContentCard key={`${section.key}-${item.id}`} item={item} index={index}/>)}</div>
  </section>;
}
