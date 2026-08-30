import { useRef, useState } from "react";
import { askCopilot } from "../api";

export default function CopilotPanel({ caseId }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const logRef = useRef(null);

  async function submit(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || caseId == null) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "user", text: q }]);
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
    requestAnimationFrame(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    });
  }

  return (
    <section className="copilot-pane">
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
      </div>
      <form className="copilot-form" onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask: why is Vijay Joshi flagged?  /  related cases?  /  identity?"
        />
        <button className="btn amber" type="submit">
          Ask
        </button>
      </form>
    </section>
  );
}
