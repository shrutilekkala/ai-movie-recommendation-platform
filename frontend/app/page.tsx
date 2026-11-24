"use client";

import {
  Clock,
  LogOut,
  Play,
  Plus,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";

import {
  useEffect,
  useState,
} from "react";

import AIPanel from "@/components/AIPanel";

import {
  getHomeFeed,
  getLibrary,
  getMyRecommendations,
  getRecommendationStatus,
  getRealtimeSession,
  login,
  me,
  patchState,
  recordEvent,
  register,
} from "@/lib/api";

import {
  AgentResponse,
  AgentResult,
  Content,
  HomeFeed,
  LibraryItem,
  Recommendation,
  RecommendationStatus,
  User,
} from "@/lib/types";


const genreLabel = (genre: string) => {
  const normalized = genre.trim().toLowerCase();

  if (normalized === "sci-fi" || normalized === "science fiction") {
    return "Sci-Fi";
  }

  return normalized
    .split(/[\s_-]+/)
    .map((part) => part ? part[0].toUpperCase() + part.slice(1) : "")
    .join(" ");
};

const languageLabel = (language: string | null | undefined) => {
  if (language === "te") return "Telugu";
  if (language === "en") return "English";
  return language ? language.toUpperCase() : "Any language";
};

const cleanAgentReason = (reason: string) => {
  const fragments = reason
    .split(/[;,]/)
    .map((part) => part.trim())
    .filter(Boolean);

  const seen = new Set<string>();
  const unique: string[] = [];

  for (const fragment of fragments) {
    const key = fragment
      .toLowerCase()
      .replace(/[.;:]/g, "")
      .replace(/\s+/g, " ")
      .trim();

    if (!seen.has(key)) {
      seen.add(key);
      unique.push(fragment);
    }
  }

  if (!unique.length) {
    return "Selected after semantic retrieval and NEXUS constraint validation.";
  }

  return unique
    .map((fragment) =>
      fragment.charAt(0).toUpperCase() + fragment.slice(1)
    )
    .join(". ")
    .replace(/\.\.+/g, ".")
    .replace(/\.$/, "") + ".";
};

const verificationCopy = (result: AgentResult) => {
  const verification =
    result.agent_signals.content_genre_verification;

  if (!verification) {
    return {
      status: "RANKED",
      detail: "Selected by the NEXUS agent after constraint-aware ranking.",
    };
  }

  const status = verification.status || "RANKED";
  const verified = verification.verified_supported || verification.supported || [];
  const catalog = verification.catalog_backed || [];

  if (status === "VERIFIED") {
    return {
      status,
      detail: verified.length
        ? `Synopsis/content evidence supports ${verified.map(genreLabel).join(", ")}.`
        : "Synopsis/content evidence supports the requested genre match.",
    };
  }

  if (status === "CATALOG_BACKED") {
    return {
      status,
      detail: catalog.length
        ? `Catalog metadata supports ${catalog.map(genreLabel).join(", ")}; synopsis evidence is inconclusive.`
        : "Catalog metadata supports the match; synopsis evidence is inconclusive.",
    };
  }

  return {
    status,
    detail: verification.reason || "NEXUS applied content-aware genre verification.",
  };
};

const percent = (value: number) =>
  `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;


const resultGenreSummary = (
  result: AgentResult,
  requestedGenres: string[]
) => {
  const matched =
    result.matched_genres ??
    requestedGenres.filter((genre) => {
      const normalized = genre.toLowerCase();
      const movieGenres = (result.content.genres || result.content.genre || "")
        .split("|")
        .map((value) => value.trim().toLowerCase());

      if (normalized === "sci-fi") {
        return movieGenres.includes("sci-fi") ||
          movieGenres.includes("science fiction");
      }

      return movieGenres.includes(normalized);
    });

  const missing =
    result.missing_genres ??
    requestedGenres.filter(
      (genre) => !matched.includes(genre)
    );

  const coverage =
    result.genre_coverage ??
    (
      requestedGenres.length
        ? matched.length / requestedGenres.length
        : 0
    );

  return {
    matched,
    missing,
    coverage,
  };
};


export default function Home() {
  const [feed, setFeed] =
    useState<HomeFeed | null>(null);

  const [selected, setSelected] =
    useState<Content | null>(null);

  const [authOpen, setAuthOpen] =
    useState(false);

  const [user, setUser] =
    useState<User | null>(null);

  const [token, setToken] =
    useState("");

  const [library, setLibrary] =
    useState<LibraryItem[]>([]);

  const [
    recommendations,
    setRecommendations,
  ] =
    useState<Recommendation[]>([]);

  const [
    modelStatus,
    setModelStatus,
  ] =
    useState<RecommendationStatus | null>(
      null
    );

  const [tab, setTab] =
    useState<"login" | "register">(
      "login"
    );

  const [error, setError] =
    useState("");

  /*
   * Phase 6 agent response.
   * This replaces the old DiscoveryResponse.
   */
  const [agent, setAgent] =
    useState<AgentResponse | null>(
      null
    );


  useEffect(() => {
    getHomeFeed()
      .then(setFeed)
      .catch(() => {});

    getRecommendationStatus()
      .then(setModelStatus)
      .catch(() => {});

    const storedToken =
      localStorage.getItem(
        "nexus_token"
      );

    if (!storedToken) {
      return;
    }

    me(storedToken)
      .then((validUser) => {
        setToken(storedToken);
        setUser(validUser);

        localStorage.setItem(
          "nexus_user",
          JSON.stringify(
            validUser
          )
        );

        getLibrary(storedToken)
          .then(setLibrary)
          .catch(() => {});

        getMyRecommendations(
          storedToken
        )
          .then(
            setRecommendations
          )
          .catch(() => {});

        getRealtimeSession(
          storedToken
        ).catch(() => {});
      })
      .catch(() => {
        localStorage.removeItem(
          "nexus_token"
        );

        localStorage.removeItem(
          "nexus_user"
        );

        setToken("");
        setUser(null);
        setLibrary([]);
        setRecommendations([]);
      });
  }, []);


  useEffect(() => {
    const interval =
      setInterval(
        () =>
          getHomeFeed()
            .then(setFeed)
            .catch(() => {}),
        15000
      );

    return () =>
      clearInterval(interval);
  }, []);


  const stateFor = (
    id: number
  ) =>
    library.find(
      (entry) =>
        entry.content.id === id
    );


  const refresh = async (
    activeToken = token
  ) => {
    if (!activeToken) {
      return;
    }

    setLibrary(
      await getLibrary(
        activeToken
      )
    );

    await new Promise(
      (resolve) =>
        setTimeout(
          resolve,
          350
        )
    );

    getMyRecommendations(
      activeToken
    )
      .then(
        setRecommendations
      )
      .catch(() => {});

    getRealtimeSession(
      activeToken
    ).catch(() => {});
  };


  const requireAuth = () => {
    if (!token) {
      setAuthOpen(true);
      return false;
    }

    return true;
  };


  const update = async (
    item: Content,
    data: object
  ) => {
    if (!requireAuth()) {
      return;
    }

    await patchState(
      token,
      item.id,
      data
    );

    await refresh();
  };


  const play = async (
    item: Content
  ) => {
    setSelected(item);

    if (!token) {
      return;
    }

    await recordEvent(
      token,
      {
        content_id: item.id,
        event_type: "play",
        event_value:
          "detail_modal",
      }
    );

    await refresh();
  };


  const submitAuth = async (
    event:
      React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    setError("");

    const form =
      new FormData(
        event.currentTarget
      );

    try {
      const auth =
        tab === "login"
          ? await login(
              String(
                form.get(
                  "email"
                )
              ),
              String(
                form.get(
                  "password"
                )
              )
            )
          : await register(
              String(
                form.get(
                  "email"
                )
              ),
              String(
                form.get(
                  "name"
                )
              ),
              String(
                form.get(
                  "password"
                )
              )
            );

      localStorage.setItem(
        "nexus_token",
        auth.token
      );

      localStorage.setItem(
        "nexus_user",
        JSON.stringify(
          auth.user
        )
      );

      setToken(auth.token);
      setUser(auth.user);
      setAuthOpen(false);

      await refresh(
        auth.token
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Authentication failed"
      );
    }
  };


  const logout = () => {
    localStorage.removeItem(
      "nexus_token"
    );

    localStorage.removeItem(
      "nexus_user"
    );

    setToken("");
    setUser(null);
    setLibrary([]);
    setRecommendations([]);
  };


  if (!feed) {
    return (
      <div className="loading">
        NEXUS is loading your
        feed…
      </div>
    );
  }


  return (
    <main>
      {/* NAV */}

      <nav className="nav-shell">
        <a
          className="brand"
          href="#"
        >
          <span>N</span>
          NEXUS
        </a>

        <div className="nav-links">
          <a href="#discover">
            Discover
          </a>

          <a href="#foryou">
            For You
          </a>

          <a href="#mylist">
            My List
          </a>

          <a href="/system-lab">
            System Lab
          </a>
        </div>

        <div className="nav-actions">
          {user ? (
            <>
              <span className="welcome">
                Hi,{" "}
                {
                  user.display_name
                }
              </span>

              <button
                className="avatar"
                title="Sign out"
                onClick={logout}
              >
                <LogOut
                  size={14}
                />
              </button>
            </>
          ) : (
            <button
              className="ai-button"
              onClick={() =>
                setAuthOpen(
                  true
                )
              }
            >
              Sign in
            </button>
          )}
        </div>
      </nav>


      {/* HERO */}

      <section className="hero poster-neon">
        <div className="hero-grid" />

        <div className="orb orb-one" />

        <div className="orb orb-two" />

        <div className="hero-content">
          <div className="eyebrow">
            ✦ NEXUS ORIGINAL
          </div>

          <h1>
            {feed.hero.title}
          </h1>

          <div className="metadata">
            <strong>
              {Math.round(
                feed.hero
                  .match_score *
                  100
              )}
              %{" "}
              {feed.hero
                .catalog_source ===
              "movielens"
                ? "Viewer Score"
                : "Match"}
            </strong>

            <span>
              {feed.hero.year}
            </span>

            <span>
              {
                feed.hero
                  .maturity_rating
              }
            </span>

            <span>
              {
                feed.hero
                  .duration_minutes
              }
              m
            </span>
          </div>

          <p>
            {feed.hero.synopsis}
          </p>

          <div className="hero-actions">
            <button
              className="primary"
              onClick={() =>
                play(
                  feed.hero
                )
              }
            >
              <Play
                size={17}
                fill="currentColor"
              />
              Play
            </button>

            <button
              className="secondary"
              onClick={() =>
                update(
                  feed.hero,
                  {
                    in_my_list:
                      !stateFor(
                        feed.hero
                          .id
                      )
                        ?.in_my_list,
                  }
                )
              }
            >
              <Plus size={17} />
              My List
            </button>
          </div>

          <div className="because">
            <span>✦</span>

            <div>
              <small>
                WHY NEXUS PICKED
                THIS
              </small>

              <p>
                {feed.hero
                  .catalog_source ===
                "movielens"
                  ? "Selected from real MovieLens popularity and rating signals."
                  : "High affinity with your current entertainment signals."}
              </p>
            </div>
          </div>
        </div>
      </section>


      <div
        className="page-content"
        id="discover"
      >
        {/* PHASE 6 INPUT */}

        <AIPanel
          token={token}
          onResults={
            setAgent
          }
        />


        {/* PHASE 6 AGENT OUTPUT */}

        {agent && (
          <section className="rail semantic-results">
            <div className="rail-heading">
              <div>
                <div className="eyebrow">
                  ✦ PHASE 7.1 / EXACT + SIMILAR NEXUS WATCH AGENT
                </div>

                <h2>
                  NEXUS picks for
                  “{agent.query}”
                </h2>

                <p className="semantic-message">
                  NEXUS evaluated{" "}
                  {
                    agent
                      .candidate_summary
                      .semantic_candidates
                  }{" "}
                  semantic candidates and found{" "}
                  {
                    agent
                      .exact_match_count ??
                    agent
                      .candidate_summary
                      .returned_candidates
                  }{" "}
                  exact match
                  {
                    (
                      agent.exact_match_count ??
                      agent.candidate_summary.returned_candidates
                    ) === 1
                      ? ""
                      : "es"
                  }
                  {agent.similar_results?.length
                    ? ` plus ${agent.similar_results.length} similar alternative${agent.similar_results.length === 1 ? "" : "s"}.`
                    : "."}
                </p>
              </div>

              <span className="phase-badge">
                AGENT v
                {
                  agent.agent_version
                }
              </span>
            </div>


            {/* INTENT */}

            <div className="intent-note">
              <strong>
                NEXUS understood:
              </strong>{" "}

              {agent.intent
                .language === "te" &&
                "TELUGU ✓  "}

              {agent.intent
                .language === "en" &&
                "ENGLISH ✓  "}

              {agent.intent.genres.map(
                (genre) =>
                  `${genre.toUpperCase()} ✓  `
              )}

              {agent.intent.genres.length > 1 && (
                agent.intent.genre_match_mode === "any"
                  ? "ANY GENRE ✓  "
                  : agent.intent.genre_match_mode === "coverage"
                  ? "BEST GENRE COVERAGE ✓  "
                  : "ALL GENRES ✓  "
              )}

              {agent.intent
                .max_minutes &&
                `≤ ${agent.intent.max_minutes} MIN ✓  `}

              {agent.intent
                .session_budget_minutes &&
                `${agent.intent.session_budget_minutes} MIN VIEWING WINDOW ✓  `}

              {agent.intent
                .watch_context &&
                `${agent.intent.watch_context.toUpperCase()} ✓  `}

              {agent.intent
                .excluded_genres.map(
                  (genre) =>
                    `NO ${genre.toUpperCase()} ✓  `
                )}

              <span>
                Confidence{" "}
                {Math.round(
                  agent.intent
                    .parser_confidence *
                    100
                )}
                %
              </span>
            </div>


            {/* EXECUTION TRACE */}

            <div className="rec-explanations">
              {agent.trace.map(
                (step) => (
                  <div
                    className="rec-explanation"
                    key={`${step.step}-${step.tool}`}
                  >
                    <strong>
                      {step.step}.{" "}
                      {step.tool
                        .replaceAll(
                          "_",
                          " "
                        )
                        .toUpperCase()}
                    </strong>

                    <p>
                      {step.detail}
                    </p>

                    <div className="signal-row">
                      <span>
                        Status{" "}
                        <b>
                          {
                            step.status
                          }
                        </b>
                      </span>
                    </div>
                  </div>
                )
              )}
            </div>


            {/* EXACT MATCHES */}

            <div className="rail-heading">
              <div>
                <div className="eyebrow">
                  ✦ EXACT COMBINATION MATCHES
                </div>

                <h2>
                  Exact matches
                </h2>

                <p className="semantic-message">
                  {agent.results.length > 0
                    ? `These titles satisfy the full requested language + genre combination.`
                    : `No exact titles in the current NEXUS catalog satisfy the complete requested combination.`}
                </p>
              </div>

              <span className="phase-badge">
                {agent.results.length} EXACT
              </span>
            </div>

            {agent.results.length > 0 ? (
              <div className="rail-track">
                {agent.results.map(
                  (
                    result,
                    index
                  ) => (
                    <Card
                      key={`agent-exact-${result.content.id}`}
                      item={{
                        ...result.content,
                        match_score:
                          result.score,
                        catalog_source:
                          "nexus-agent",
                      }}
                      index={index}
                      state={stateFor(
                        result.content.id
                      )}
                      onOpen={() =>
                        setSelected(
                          result.content
                        )
                      }
                      onPlay={() =>
                        play(
                          result.content
                        )
                      }
                      onList={() =>
                        update(
                          result.content,
                          {
                            in_my_list:
                              !stateFor(
                                result.content.id
                              )?.in_my_list,
                          }
                        )
                      }
                    />
                  )
                )}
              </div>
            ) : (
              <div className="empty-state">
                No exact combination was found. NEXUS is showing the closest
                same-language alternatives below instead of pretending they are exact matches.
              </div>
            )}


            {/* EXACT EXPLANATIONS */}

            {agent.results.length > 0 && (
              <div className="rec-explanations">
                {agent.results.map(
                  (result) => {
                    const verification =
                      verificationCopy(result);

                    const summary =
                      resultGenreSummary(
                        result,
                        agent.intent.genres
                      );

                    const runtime =
                      result.content.duration_minutes;

                    const runtimeCopy =
                      runtime > 0
                        ? agent.intent.max_minutes
                          ? `${runtime} min • ${runtime <= agent.intent.max_minutes ? "within" : "outside"} ${agent.intent.max_minutes}-min limit`
                          : agent.intent.session_budget_minutes
                          ? `${runtime} min • ${runtime <= agent.intent.session_budget_minutes ? "fits" : "exceeds"} ${agent.intent.session_budget_minutes}-min viewing window`
                          : `${runtime} min`
                        : "Runtime unavailable";

                    return (
                      <div
                        className="rec-explanation"
                        key={`agent-exact-why-${result.content.id}`}
                      >
                        <div className="card-title-row">
                          <strong>
                            Why NEXUS picked{" "}
                            {result.content.title}
                          </strong>

                          <span className="phase-badge">
                            EXACT
                          </span>
                        </div>

                        <p>
                          {cleanAgentReason(result.reason)}
                        </p>

                        <p className="muted">
                          {verification.detail}
                        </p>

                        <div className="signal-row">
                          <span>
                            Genre combination{" "}
                            <b>
                              {summary.matched.length}/{agent.intent.genres.length || summary.matched.length} matched
                            </b>
                          </span>

                          <span>
                            Runtime{" "}
                            <b>{runtimeCopy}</b>
                          </span>

                          <span>
                            Verification{" "}
                            <b>{verification.status.replaceAll("_", " ")}</b>
                          </span>
                        </div>

                        {agent.intent.genres.length > 0 && (
                          <div className="signal-row">
                            {agent.intent.genres.map((genre) => (
                              <span key={`exact-${result.content.id}-${genre}`}>
                                ✓ <b>{genreLabel(genre)}</b>
                              </span>
                            ))}
                          </div>
                        )}

                        <div className="signal-row">
                          <span>
                            Agent fit{" "}
                            <b>{percent(result.agent_signals.final_score)}</b>
                          </span>

                          <span>
                            Semantic{" "}
                            <b>{percent(result.agent_signals.semantic)}</b>
                          </span>

                          <span>
                            Genre{" "}
                            <b>{percent(result.agent_signals.requested_genre)}</b>
                          </span>
                        </div>
                      </div>
                    );
                  }
                )}
              </div>
            )}


            {/* SIMILAR MOVIES */}

            {(agent.similar_results?.length ?? 0) > 0 && (
              <>
                <div className="rail-heading">
                  <div>
                    <div className="eyebrow">
                      ✦ CLOSEST ALTERNATIVES
                    </div>

                    <h2>
                      Similar movies you may also like
                    </h2>

                    <p className="semantic-message">
                      These movies do not satisfy the full genre combination.
                      They are ranked by same-language genre overlap and agent relevance.
                    </p>
                  </div>

                  <span className="phase-badge">
                    {agent.similar_results?.length ?? 0} SIMILAR
                  </span>
                </div>

                <div className="rail-track">
                  {agent.similar_results!.map(
                    (
                      result,
                      index
                    ) => (
                      <Card
                        key={`agent-similar-${result.content.id}`}
                        item={{
                          ...result.content,
                          match_score:
                            result.score,
                          catalog_source:
                            "nexus-agent",
                        }}
                        index={index}
                        state={stateFor(
                          result.content.id
                        )}
                        onOpen={() =>
                          setSelected(
                            result.content
                          )
                        }
                        onPlay={() =>
                          play(
                            result.content
                          )
                        }
                        onList={() =>
                          update(
                            result.content,
                            {
                              in_my_list:
                                !stateFor(
                                  result.content.id
                                )?.in_my_list,
                            }
                          )
                        }
                      />
                    )
                  )}
                </div>

                <div className="rec-explanations">
                  {agent.similar_results!.map(
                    (result) => {
                      const verification =
                        verificationCopy(result);

                      const summary =
                        resultGenreSummary(
                          result,
                          agent.intent.genres
                        );

                      return (
                        <div
                          className="rec-explanation"
                          key={`agent-similar-why-${result.content.id}`}
                        >
                          <div className="card-title-row">
                            <strong>
                              Similar because{" "}
                              {result.content.title}
                            </strong>

                            <span className="phase-badge">
                              {Math.round(summary.coverage * 100)}% GENRE OVERLAP
                            </span>
                          </div>

                          <p>
                            Matches{" "}
                            <b>
                              {summary.matched.length}/{agent.intent.genres.length}
                            </b>{" "}
                            requested genres.
                          </p>

                          <p className="muted">
                            {verification.detail}
                          </p>

                          <div className="signal-row">
                            {summary.matched.map((genre) => (
                              <span key={`matched-${result.content.id}-${genre}`}>
                                ✓ <b>{genreLabel(genre)}</b>
                              </span>
                            ))}

                            {summary.missing.map((genre) => (
                              <span key={`missing-${result.content.id}-${genre}`}>
                                ○ <b>{genreLabel(genre)}</b>
                              </span>
                            ))}
                          </div>

                          <div className="signal-row">
                            <span>
                              Agent fit{" "}
                              <b>{percent(result.agent_signals.final_score)}</b>
                            </span>

                            <span>
                              Semantic{" "}
                              <b>{percent(result.agent_signals.semantic)}</b>
                            </span>

                            <span>
                              Genre coverage{" "}
                              <b>{Math.round(summary.coverage * 100)}%</b>
                            </span>

                            <span>
                              Verification{" "}
                              <b>{verification.status.replaceAll("_", " ")}</b>
                            </span>
                          </div>
                        </div>
                      );
                    }
                  )}
                </div>
              </>
            )}




            {agent.rejected_count >
              0 && (
              <div className="intent-note">
                NEXUS filtered{" "}
                {
                  agent.rejected_count
                }{" "}
                candidates that failed language, genre, exclusion, runtime
                or content-verification rules. Exact and similar matches are
                shown separately above.
              </div>
            )}


            {!user && (
              <div className="intent-note">
                Sign in to activate
                PostgreSQL taste
                profile + MovieLens
                hybrid recommender +
                Redis live-session
                personalization.
              </div>
            )}
          </section>
        )}


        {/* PERSONALIZED RECOMMENDATIONS */}

        {!agent && recommendations.length >
          0 && (
          <section className="rail">
            <div className="rail-heading">
              <h2>
                Behavior-Personalized
                Recommendations
              </h2>

              <span className="phase-badge">
                SESSION-AWARE
                HYBRID RANKER
              </span>
            </div>

            <div className="rail-track">
              {recommendations.map(
                (
                  recommendation,
                  index
                ) => (
                  <Card
                    key={`rec-${recommendation.content.id}`}
                    item={{
                      ...recommendation.content,
                      match_score:
                        recommendation.score,
                      catalog_source:
                        "nexus-recommendation",
                    }}
                    index={index}
                    state={stateFor(
                      recommendation
                        .content.id
                    )}
                    onOpen={() =>
                      setSelected(
                        recommendation
                          .content
                      )
                    }
                    onPlay={() =>
                      play(
                        recommendation
                          .content
                      )
                    }
                    onList={() =>
                      update(
                        recommendation
                          .content,
                        {
                          in_my_list:
                            !stateFor(
                              recommendation
                                .content
                                .id
                            )
                              ?.in_my_list,
                        }
                      )
                    }
                  />
                )
              )}
            </div>

            <div className="rec-explanations">
              {recommendations
                .slice(0, 3)
                .map(
                  (
                    recommendation
                  ) => (
                    <div
                      className="rec-explanation"
                      key={`why-${recommendation.content.id}`}
                    >
                      <strong>
                        Why{" "}
                        {
                          recommendation
                            .content
                            .title
                        }
                      </strong>

                      <p>
                        {
                          recommendation.reason
                        }
                      </p>

                      {recommendation.signals && (
                        <div className="signal-row">
                          <span>
                            CF{" "}
                            <b>
                              {recommendation.signals.collaborative.toFixed(
                                2
                              )}
                            </b>
                          </span>

                          <span>
                            Content{" "}
                            <b>
                              {recommendation.signals.content.toFixed(
                                2
                              )}
                            </b>
                          </span>

                          <span>
                            Popularity{" "}
                            <b>
                              {recommendation.signals.popularity.toFixed(
                                2
                              )}
                            </b>
                          </span>
                        </div>
                      )}
                    </div>
                  )
                )}
            </div>
          </section>
        )}


        {/* STANDARD HOME FEED */}

        {feed.sections.map(
          (section) => (
            <section
              className="rail"
              id={
                section.key ===
                  "top-picks" ||
                section.key ===
                  "real-popular"
                  ? "foryou"
                  : undefined
              }
              key={section.key}
            >
              <div className="rail-heading">
                <h2>
                  {section.title}
                </h2>
              </div>

              <div className="rail-track">
                {section.items.map(
                  (
                    item,
                    index
                  ) => (
                    <Card
                      key={`${section.key}-${item.id}`}
                      item={item}
                      index={index}
                      state={stateFor(
                        item.id
                      )}
                      onOpen={() =>
                        setSelected(
                          item
                        )
                      }
                      onPlay={() =>
                        play(item)
                      }
                      onList={() =>
                        update(
                          item,
                          {
                            in_my_list:
                              !stateFor(
                                item.id
                              )
                                ?.in_my_list,
                          }
                        )
                      }
                    />
                  )
                )}
              </div>
            </section>
          )
        )}


        {/* MY LIST */}

        {user && (
          <section
            className="rail"
            id="mylist"
          >
            <div className="rail-heading">
              <h2>
                My List
              </h2>

              <span className="phase-badge">
                LIVE USER DATA
              </span>
            </div>

            {library.filter(
              (entry) =>
                entry.in_my_list
            ).length ? (
              <div className="rail-track">
                {library
                  .filter(
                    (entry) =>
                      entry.in_my_list
                  )
                  .map(
                    (
                      entry,
                      index
                    ) => (
                      <Card
                        key={
                          entry
                            .content
                            .id
                        }
                        item={
                          entry.content
                        }
                        index={
                          index
                        }
                        state={
                          entry
                        }
                        onOpen={() =>
                          setSelected(
                            entry
                              .content
                          )
                        }
                        onPlay={() =>
                          play(
                            entry
                              .content
                          )
                        }
                        onList={() =>
                          update(
                            entry
                              .content,
                            {
                              in_my_list:
                                false,
                            }
                          )
                        }
                      />
                    )
                  )}
              </div>
            ) : (
              <div className="empty-state">
                Add titles with the
                + button. Your list
                is persisted in
                PostgreSQL.
              </div>
            )}
          </section>
        )}


        <footer>
          <div className="brand">
            <span>N</span>
            NEXUS
          </div>

          <p>
            Phase 7.1 • Exact + Similar Explainable Agentic
            Entertainment Intelligence
          </p>

          <small>
            Intent parser + Qdrant
            retrieval + MovieLens
            hybrid ranking +
            PostgreSQL profile +
            Kafka/Redis session
            intelligence.
          </small>
        </footer>
      </div>


      {selected && (
        <Detail
          item={selected}
          state={stateFor(
            selected.id
          )}
          onClose={() =>
            setSelected(null)
          }
          onList={() =>
            update(
              selected,
              {
                in_my_list:
                  !stateFor(
                    selected.id
                  )?.in_my_list,
              }
            )
          }
          onReact={(reaction) =>
            update(
              selected,
              {
                reaction,
              }
            )
          }
          onProgress={(seconds) =>
            update(
              selected,
              {
                progress_seconds:
                  seconds,
              }
            )
          }
        />
      )}


      {authOpen && (
        <div className="modal-backdrop">
          <div className="auth-card">
            <button
              className="modal-x"
              onClick={() =>
                setAuthOpen(
                  false
                )
              }
            >
              <X />
            </button>

            <div className="brand">
              <span>N</span>
              NEXUS
            </div>

            <h2>
              {tab === "login"
                ? "Welcome back"
                : "Create your profile"}
            </h2>

            <p className="muted">
              Demo login:{" "}
              <b>
                demo@nexus.ai
              </b>{" "}
              /{" "}
              <b>
                nexus123
              </b>
            </p>

            <form
              onSubmit={
                submitAuth
              }
            >
              {tab ===
                "register" && (
                <input
                  name="name"
                  placeholder="Display name"
                  required
                />
              )}

              <input
                name="email"
                type="email"
                placeholder="Email"
                defaultValue={
                  tab ===
                  "login"
                    ? "demo@nexus.ai"
                    : ""
                }
                required
              />

              <input
                name="password"
                type="password"
                placeholder="Password"
                defaultValue={
                  tab ===
                  "login"
                    ? "nexus123"
                    : ""
                }
                required
              />

              {error && (
                <p className="form-error">
                  {error}
                </p>
              )}

              <button className="auth-submit">
                {tab ===
                "login"
                  ? "Sign in"
                  : "Create account"}
              </button>
            </form>

            <button
              className="auth-switch"
              onClick={() =>
                setTab(
                  tab ===
                    "login"
                    ? "register"
                    : "login"
                )
              }
            >
              {tab ===
                "login"
                ? "New to NEXUS? Create account"
                : "Already have an account? Sign in"}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}


function Card({
  item,
  index,
  state,
  onOpen,
  onPlay,
  onList,
}: {
  item: Content;
  index: number;
  state?: LibraryItem;
  onOpen: () => void;
  onPlay: () => void;
  onList: () => void;
}) {
  const posterUrl =
    item.poster_path
      ? `https://image.tmdb.org/t/p/w500${item.poster_path}`
      : null;

  return (
    <article className="content-card">
      <div
        className={`poster poster-${item.accent} ${
          posterUrl
            ? "has-catalog-image"
            : ""
        }`}
        style={
          posterUrl
            ? {
                backgroundImage: `linear-gradient(0deg,rgba(2,3,5,.18),rgba(2,3,5,.05)),url(${posterUrl})`,
                backgroundSize:
                  "cover",
                backgroundPosition:
                  "center",
              }
            : undefined
        }
        onClick={onOpen}
      >
        <span className="poster-index">
          {String(
            index + 1
          ).padStart(2, "0")}
        </span>

        {!posterUrl && (
          <div className="poster-word">
            {item.title
              .split(" ")
              .slice(0, 2)
              .join(" ")}
          </div>
        )}

        <button
          className="poster-play"
          onClick={(event) => {
            event.stopPropagation();
            onPlay();
          }}
        >
          <Play
            size={16}
            fill="currentColor"
          />
        </button>

        {state?.progress_seconds ? (
          <div className="progress">
            <i
              style={{
                width: `${Math.min(
                  100,
                  (state.progress_seconds /
                    Math.max(
                      1,
                      item.duration_minutes *
                        60
                    )) *
                    100
                )}%`,
              }}
            />
          </div>
        ) : null}
      </div>

      <div className="card-copy">
        <div className="card-title-row">
          <h3
            onClick={onOpen}
          >
            {item.title}
          </h3>

          <button
            className={
              state?.in_my_list
                ? "active-action"
                : ""
            }
            onClick={onList}
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="card-meta">
          <strong>
            {Math.round(
              item.match_score *
                100
            )}
            %{" "}
            {item.catalog_source ===
            "nexus-agent"
              ? "agent fit"
              : item.catalog_source ===
                "movielens"
              ? "rating"
              : "match"}
          </strong>

          <span>
            {item.original_language ===
            "te"
              ? "తెలుగు"
              : item.content_type}
          </span>

          <span>
            {item.year || "—"}
          </span>
        </div>
      </div>
    </article>
  );
}


function Detail({
  item,
  state,
  onClose,
  onList,
  onReact,
  onProgress,
}: {
  item: Content;
  state?: LibraryItem;
  onClose: () => void;
  onList: () => void;
  onReact: (
    reaction: string
  ) => void;
  onProgress: (
    seconds: number
  ) => void;
}) {
  const [
    seconds,
    setSeconds,
  ] =
    useState(
      state?.progress_seconds ??
        0
    );

  const backdrop =
    item.backdrop_path
      ? `https://image.tmdb.org/t/p/original${item.backdrop_path}`
      : null;

  return (
    <div className="modal-backdrop">
      <div className="detail-card">
        <div
          className={`detail-visual poster-${item.accent} ${
            backdrop
              ? "has-catalog-image"
              : ""
          }`}
          style={
            backdrop
              ? {
                  backgroundImage: `linear-gradient(0deg,#11131a 0%,rgba(17,19,26,.05) 75%),url(${backdrop})`,
                  backgroundSize:
                    "cover",
                  backgroundPosition:
                    "center",
                }
              : undefined
          }
        >
          <button
            className="modal-x"
            onClick={onClose}
          >
            <X />
          </button>

          <div className="detail-title">
            {item.title}
          </div>
        </div>

        <div className="detail-body">
          <div className="metadata">
            <strong>
              {Math.round(
                item.match_score *
                  100
              )}
              %{" "}
              {item.catalog_source ===
              "nexus-agent"
                ? "Agent Fit"
                : item.catalog_source ===
                  "movielens"
                ? "Viewer Score"
                : "Match"}
            </strong>

            <span>
              {item.year}
            </span>

            <span>
              {item.original_language ===
              "te"
                ? "తెలుగు / Telugu"
                : item.maturity_rating}
            </span>

            <span>
              {item.catalog_source.toUpperCase()}
            </span>
          </div>

          <p>
            {item.synopsis}
          </p>

          <div className="detail-actions">
            <button
              className="primary"
              onClick={() => {
                const next =
                  Math.min(
                    item.duration_minutes *
                      60,
                    seconds +
                      300
                  );

                setSeconds(next);

                onProgress(next);
              }}
            >
              <Play size={16} />
              Simulate +5 min
              watch
            </button>

            <button
              className={
                state?.in_my_list
                  ? "round active-action"
                  : "round"
              }
              onClick={onList}
            >
              <Plus />
            </button>

            <button
              className={
                state?.reaction ===
                "like"
                  ? "round active-action"
                  : "round"
              }
              onClick={() =>
                onReact(
                  state?.reaction ===
                    "like"
                    ? "none"
                    : "like"
                )
              }
            >
              <ThumbsUp />
            </button>

            <button
              className={
                state?.reaction ===
                "dislike"
                  ? "round active-action"
                  : "round"
              }
              onClick={() =>
                onReact(
                  state?.reaction ===
                    "dislike"
                    ? "none"
                    : "dislike"
                )
              }
            >
              <ThumbsDown />
            </button>
          </div>

          <div className="watch-status">
            <Clock size={15} />

            Watched{" "}
            {Math.floor(
              seconds / 60
            )}
            m of{" "}
            {
              item.duration_minutes
            }
            m
          </div>
        </div>
      </div>
    </div>
  );
}