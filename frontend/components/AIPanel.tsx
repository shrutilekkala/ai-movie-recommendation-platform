"use client";

import {
  ArrowUp,
  Languages,
  Loader2,
  Mic,
  MicOff,
  Sparkles,
  X,
} from "lucide-react";

import {
  FormEvent,
  useRef,
  useState,
} from "react";

import { runAgent } from "@/lib/api";
import { AgentResponse } from "@/lib/types";


const suggestions = [
  "Funny crime movies with dark humor",
  "Sci-fi, but not horror",
  "తెలుగు కామెడీ సినిమా",
  "Telugu action movie with friends under 2 hours, not horror",
];


type SearchLanguage =
  | "all"
  | "en"
  | "te";


export default function AIPanel({
  token,
  onResults,
}: {
  token?: string;

  onResults: (
    data: AgentResponse
  ) => void;
}) {
  const [
    value,
    setValue,
  ] = useState("");

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    listening,
    setListening,
  ] = useState(false);

  const [
    transcript,
    setTranscript,
  ] = useState("");

  const [
    language,
    setLanguage,
  ] =
    useState<SearchLanguage>("all");

  const recognitionRef =
    useRef<any>(null);


  const clearPrompt = () => {
    setValue("");
    setTranscript("");
  };


  const prepareAgentQuery = (
    query: string,
    selectedLanguage: SearchLanguage
  ) => {
    const cleaned =
      query.trim();

    if (!cleaned) {
      return cleaned;
    }

    if (
      selectedLanguage === "te" &&
      !cleaned
        .toLowerCase()
        .includes("telugu") &&
      !cleaned.includes("తెలుగు")
    ) {
      return `Telugu ${cleaned}`;
    }

    if (
      selectedLanguage === "en" &&
      !cleaned
        .toLowerCase()
        .includes("english")
    ) {
      return `English ${cleaned}`;
    }

    return cleaned;
  };


  const run = async (
    query = value,
    source:
      | "text"
      | "voice" = "text",
    selectedLanguage:
      SearchLanguage = language
  ) => {
    const raw =
      query.trim();

    if (!raw) {
      return;
    }

    const agentQuery =
      prepareAgentQuery(
        raw,
        selectedLanguage
      );

    setLoading(true);
    setError("");

    try {
      const data =
        await runAgent(
          agentQuery,
          token || undefined,
          12
        );

      onResults(data);

      clearPrompt();

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "NEXUS Agent failed"
      );

      setValue(raw);

    } finally {
      setLoading(false);
    }
  };


  const submit = (
    event: FormEvent
  ) => {
    event.preventDefault();

    void run(
      value,
      "text",
      language
    );
  };


  const toggleVoice = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }

    const browser =
      window as any;

    const SpeechRecognition =
      browser.SpeechRecognition ||
      browser.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError(
        "Voice recognition is not supported in this browser. Use Chrome/Edge or type your vibe."
      );

      return;
    }

    const recognition =
      new SpeechRecognition();

    recognitionRef.current =
      recognition;

    recognition.lang =
      language === "te"
        ? "te-IN"
        : "en-US";

    recognition.interimResults =
      true;

    recognition.continuous =
      false;


    recognition.onstart = () => {
      setListening(true);
      setError("");
      setTranscript("");
      setValue("");
    };


    recognition.onresult = (
      event: any
    ) => {
      let text = "";

      for (
        let index =
          event.resultIndex;
        index <
        event.results.length;
        index++
      ) {
        text +=
          event.results[index][0]
            .transcript;
      }

      const cleaned =
        text.trim();

      setTranscript(cleaned);
      setValue(cleaned);

      const finalResult =
        event.results[
          event.results.length - 1
        ];

      if (
        finalResult?.isFinal &&
        cleaned
      ) {
        void run(
          cleaned,
          "voice",
          language
        );
      }
    };


    recognition.onerror = (
      event: any
    ) => {
      setError(
        `Voice recognition failed: ${
          event.error ||
          "unknown error"
        }`
      );

      setListening(false);
    };


    recognition.onend =
      () => {
        setListening(false);
      };


    recognition.start();
  };


  return (
    <section
      className="ai-panel"
      id="discover"
    >
      <div className="ai-glow" />

      <div className="ai-copy">
        <div className="eyebrow">
          <Sparkles size={14} />

          PHASE 7.1 • EXACT + SIMILAR DISCOVERY
        </div>

        <h2>
          Don’t browse.{" "}
          <em>
            Tell NEXUS what you want.
          </em>
        </h2>

        <p>
          Type it or say it naturally.
          NEXUS understands your
          language, mood, genres,
          exclusions, viewing context
          and time budget, then calls
          semantic retrieval,
          personalization and real-time
          session tools before choosing
          the final movies.
        </p>
      </div>


      <div className="prompt-shell">
        <div className="discovery-toolbar">
          <Languages size={14} />

          <span>
            Agent language
          </span>

          <select
            value={language}
            onChange={(event) =>
              setLanguage(
                event.target.value as SearchLanguage
              )
            }
          >
            <option value="all">
              Auto detect
            </option>

            <option value="en">
              English
            </option>

            <option value="te">
              తెలుగు • Telugu
            </option>
          </select>

          <small>
            {language === "te"
              ? "Voice: te-IN"
              : "Voice: en-US"}
          </small>
        </div>


        <form
          className={`prompt-input ${
            listening
              ? "listening"
              : ""
          }`}
          onSubmit={submit}
        >
          <Sparkles size={20} />

          <input
            value={value}
            onChange={(event) =>
              setValue(
                event.target.value
              )
            }
            placeholder={
              listening
                ? "Listening… tell NEXUS how you feel"
                : language ===
                    "te"
                ? "ఉదా: తెలుగు యాక్షన్ సినిమా, హారర్ వద్దు"
                : "Try: Telugu action movie with friends under 2 hours, not horror"
            }
          />


          {value &&
            !listening && (
              <button
                type="button"
                className="clear-button"
                aria-label="Clear search"
                onClick={
                  clearPrompt
                }
              >
                <X size={16} />
              </button>
            )}


          <button
            type="button"
            className={`voice-button ${
              listening
                ? "voice-live"
                : ""
            }`}
            aria-label={
              listening
                ? "Stop listening"
                : "Ask NEXUS by voice"
            }
            onClick={
              toggleVoice
            }
          >
            {listening ? (
              <MicOff size={18} />
            ) : (
              <Mic size={18} />
            )}
          </button>


          <button
            type="submit"
            aria-label="Run NEXUS agent"
            disabled={loading}
          >
            {loading ? (
              <Loader2
                size={18}
                className="spin"
              />
            ) : (
              <ArrowUp
                size={18}
              />
            )}
          </button>
        </form>


        {listening && (
          <div className="voice-state">
            <span className="voice-pulse" />

            Listening
            {transcript
              ? ` — “${transcript}”`
              : "…"}
          </div>
        )}


        <div className="chips">
          {suggestions.map(
            (suggestion) => (
              <button
                key={suggestion}
                onClick={() =>
                  void run(
                    suggestion,
                    "text",
                    suggestion.includes(
                      "తెలుగు"
                    ) ||
                    suggestion
                      .toLowerCase()
                      .includes(
                        "telugu"
                      )
                      ? "te"
                      : language
                  )
                }
              >
                {suggestion}
              </button>
            )
          )}
        </div>


        {error && (
          <div className="semantic-error">
            {error}
          </div>
        )}
      </div>
    </section>
  );
}