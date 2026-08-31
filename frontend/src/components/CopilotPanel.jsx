import { useRef, useState } from "react";
import { apiError, askCopilot } from "../api";

export default function CopilotPanel({ caseId, fullPage = false }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const logRef = useRef(null);

  async function submit(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || caseId == null || busy) return;
    setQuestion("");
    setErr(null);
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: q }]);
    try {
      const payload = await askCopilot(caseId, q);
      const claims = payload.claims || [];
      setMessages((m) => [
        ...m,
        ...claims.map((c) => ({
          role: "assistant",
          tag: c.tag,
          text: c.formatted || c.claim || payload.answer,
        })),
      ]);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
      });
    }
  }

  return (
    <section className={`copilot-pane ${fullPage ? "full" : ""}`} id="copilotPane">
      <div className="copilot-log" ref={logRef}>
        {messages.map((msg, i) => (
          <div className={`msg ${msg.role}`} key={i}>
            {msg.role === "user" ? (
              <>Q: {msg.text}</>
            ) : (
              <>
                <span className={`pill ${msg.tag === "DIRECTLY_OBSERVED" ? "observed" : "inferred"}`}>
                  {msg.tag}
                </span>
                {msg.text}
              </>
            )}
          </div>
        ))}
        {err && <div className="error-inline">{err}</div>}
      </div>
      <form className="copilot-form" onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask: why is Vijay Joshi flagged?  /  related cases?  /  identity?"
          disabled={busy}
        />
        <button className="btn amber" type="submit" disabled={busy || caseId == null}>
          {busy ? "Asking…" : "Ask"}
        </button>
      </form>
    </section>
  );
}
