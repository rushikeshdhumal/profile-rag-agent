import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchAgent, sendChat, type AgentMeta, type ChatMessage } from "../api";

const STARTERS = ["Open to relocate?", "Notable projects?", "Preferred roles?"] as const;

export default function ChatPage() {
  const { agentId = "" } = useParams();
  const [agent, setAgent] = useState<AgentMeta | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!agentId) return;
    fetchAgent(agentId)
      .then((meta) => {
        setAgent(meta);
        requestAnimationFrame(() => inputRef.current?.focus());
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [agentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function focusComposer() {
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function ask(text: string, history: ChatMessage[] = messages) {
    const trimmed = text.trim();
    if (!trimmed || !agentId || busy) return;
    setInput("");
    setError("");
    const nextHistory = [...history, { role: "user" as const, content: trimmed }];
    setMessages(nextHistory);
    setBusy(true);
    focusComposer();
    try {
      const res = await sendChat(agentId, trimmed, history);
      setMessages([...nextHistory, { role: "assistant", content: res.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setMessages(nextHistory);
    } finally {
      setBusy(false);
      focusComposer();
    }
  }

  async function onSend(e: FormEvent) {
    e.preventDefault();
    await ask(input);
  }

  return (
    <main className="app-shell chat-layout">
      <header className="chat-hero">
        <p className="eyebrow">Profile RAG Agent</p>
        <h1>{agent?.display_name || "Loading…"}</h1>
        <p>{agent?.headline || "Ask about experience, projects, and availability."}</p>
      </header>

      <section className="thread" aria-live="polite">
        {messages.length === 0 && !error && (
          <>
            <div className="bubble assistant">
              Hi — I can answer questions grounded in {agent?.display_name || "this candidate"}
              &apos;s profile. Ask about roles, skills, projects, or logistics like relocation.
            </div>
            <div className="chips" role="group" aria-label="Suggested questions">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="chip"
                  disabled={!agent || busy}
                  onClick={() => ask(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </>
        )}
        {messages.map((m, i) => (
          <div key={`${m.role}-${i}`} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {busy && (
          <div className="bubble assistant" aria-label="Assistant is typing">
            <span className="typing">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </section>

      <div className="composer-wrap">
        <form className="composer" onSubmit={onSend}>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about experience, stack, relocation…"
            aria-label="Message"
            disabled={!agent}
          />
          <button className="btn" type="submit" disabled={!agent || busy || !input.trim()}>
            Send
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        <p className="disclaimer">
          Answers come from the candidate&apos;s uploaded profile. Verify critical details directly
          with them.
        </p>
      </div>
    </main>
  );
}
