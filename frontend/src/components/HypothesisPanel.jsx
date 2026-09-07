import { useEffect, useState } from "react";
import { apiError, getHypotheses } from "../api";

export default function HypothesisPanel({ caseId, personId, personLabel }) {
  const [hypotheses, setHypotheses] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (caseId == null || personId == null) {
      setHypotheses([]);
      setErr(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    getHypotheses(caseId, personId)
      .then((data) => {
        if (cancelled) return;
        const list = [...(data.hypotheses || [])].sort((a, b) => b.score - a.score);
        setHypotheses(list);
        setErr(null);
      })
      .catch((e) => {
        if (!cancelled) {
          setHypotheses([]);
          setErr(apiError(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, personId]);

  return (
    <article className="panel-card hyp" id="hypCard">
      <h2>Competing Hypotheses</h2>
      <p className="muted">
        {personId == null
          ? "Select a PERSON node on the graph to score H1–H4."
          : `${personLabel || "Person"} (${personId})`}
      </p>
      {loading && <p className="muted">Loading hypotheses…</p>}
      {err && <p className="error-inline">{err}</p>}
      <div className="hyp-grid">
        {hypotheses.map((h, i) => (
          <div className={`hyp-card ${i === 0 ? "lead" : ""}`} key={h.type}>
            <span className="badge">{h.type}</span>
            <span className="score">{Number(h.score).toFixed(3)}</span>
            {h.ground_truth ? <span className="badge ok">GT</span> : null}
            {h.generated ? <span className="badge">heuristic</span> : null}
            <div className="muted" style={{ margin: "6px 0 0" }}>
              {h.narrative}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
