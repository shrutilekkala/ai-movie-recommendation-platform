"use client";

import { Bell, Search, Sparkles } from "lucide-react";
import { useState } from "react";

export default function NavBar() {
  const [searchOpen, setSearchOpen] = useState(false);
  return (
    <header className="nav-shell">
      <a className="brand" href="#top" aria-label="NEXUS home"><span>N</span>NEXUS</a>
      <nav className="nav-links" aria-label="Primary navigation">
        <a href="#discover">Discover</a><a href="#foryou">For You</a><a href="#new">New & Hot</a>
      </nav>
      <div className="nav-actions">
        <div className={`search-box ${searchOpen ? "open" : ""}`}>
          {searchOpen && <input autoFocus placeholder="Search stories, moods, ideas..." aria-label="Search" />}
          <button onClick={() => setSearchOpen(!searchOpen)} aria-label="Toggle search"><Search size={19}/></button>
        </div>
        <button className="icon-button" aria-label="Notifications"><Bell size={19}/></button>
        <button className="ai-button"><Sparkles size={16}/> Ask NEXUS</button>
        <div className="avatar">ST</div>
      </div>
    </header>
  );
}
