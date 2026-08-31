import { useEffect, useState } from "react";
import { apiError, runCounterfactual } from "../api";

export default function CounterfactualPanel({ caseId, personId, personLabel }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setResult(null);
    setErr(null);
  }, [caseId, personId]);

  async function run() {
    if (caseId == null || personId == null) return;
    setBusy(true);
    setErr(null);
    try {
      const data = await runCounterfactual(caseId, personId);
      setResult(data);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  const disabled = personId == null || busy;

  return (
    <article className="panel-card cf" id="cfCard">
      <h2>Counterfactual</h2>
      <button
        className="btn amber"
        disabled={disabled}
        title={personId == null ? "Select a PERSON node on the graph first" : ""}
        onClick={run}
      >
        {busy ? "Computing…" : `Remove ${personLabel || "selected person"}`}
      </button>
      {err && <div className="error-inline">{err}</div>}
      {result && (
        <div className="item" style={{ marginTop: 8 }}>
          Removed <strong>{result.person_label}</strong>
          <div className="muted">
            reachable pairs {result.before.reachable_pairs} → {result.after.reachable_pairs} (
            {result.percent_change.reachable_pairs}%)
          </div>
          <div className="muted">
            components {result.before.components} → {result.after.components} · avg path{" "}
            {result.before.avg_shortest_path} → {result.after.avg_shortest_path}
          </div>
        </div>
      )}
    </article>
  );
}
