/**
 * ChatPanel.jsx — Embedded RAG diagnostic chatbot in the React dashboard
 *
 * Engineers can ask natural language questions about transformer health
 * without leaving the dashboard (e.g. "Why is TRF045 in the Red band?").
 *
 * Security: This component sends only the question string to /api/chat.
 * All Azure OpenAI and Azure AI Search credentials stay in the FastAPI backend.
 * Inspecting browser DevTools network requests reveals no Azure keys.
 *
 * Architecture:
 *   ChatPanel → POST /api/chat { question } → FastAPI → Azure OpenAI + AI Search → answer
 */

import { useState, useRef, useEffect } from "react";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:5000";

const STARTER_QUESTIONS = [
  "Which transformers are in the Red band and why?",
  "What is the thermal aging factor for TRF045?",
  "Which assets have open emergency work orders?",
  "What does an FAA value above 4 mean?",
];

export default function ChatPanel() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Ask me anything about transformer health, risk scores, or maintenance history.",
    },
  ]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const bottomRef             = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ask = async (question) => {
    if (!question.trim() || loading) return;
    setError(null);

    const userMsg = { role: "user", text: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Only the question string is sent — no credentials, no Azure keys
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();

      const assistantMsg = {
        role: "assistant",
        text: data.answer,
        sources: data.sources || [],
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError("Failed to get a response. Please check the backend is running.");
      console.error("Chat error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => ask(input);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span className="chat-title">Asset Diagnostic Assistant</span>
        <span className="chat-subtitle">Powered by RAG · Azure OpenAI + AI Search</span>
      </div>

      {/* Starter question chips */}
      <div className="chat-starters">
        {STARTER_QUESTIONS.map((q) => (
          <button
            key={q}
            className="starter-chip"
            onClick={() => ask(q)}
            disabled={loading}
          >
            {q}
          </button>
        ))}
      </div>

      {/* Message history */}
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${msg.role}`}>
            <p className="chat-bubble__text">{msg.text}</p>
            {msg.sources?.length > 0 && (
              <div className="chat-sources">
                <span className="chat-sources__label">Sources: </span>
                {msg.sources.map((s, j) => (
                  <span key={j} className="chat-sources__item">{s}</span>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="chat-bubble chat-bubble--assistant">
            <span className="chat-typing">Retrieving context and generating answer…</span>
          </div>
        )}

        {error && (
          <div className="chat-error">{error}</div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          placeholder="Ask about a transformer, substation, or health metric…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="chat-send-btn"
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
        >
          {loading ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
