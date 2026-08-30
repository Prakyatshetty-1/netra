import { useEffect, useState } from "react";
import { runCounterfactual } from "../api";

export default function CounterfactualPanel({ caseId, personId, personLabel }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setResult(null);
  }, [caseId, personId]);

  async function run() {
    if (caseId == null || personId == null) return;
    setBusy(true);
    try {
      setResult(await runCounterfactual(caseId, personId));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel-card cf">
      <h2>Counterfactual</h2>
      <button className="btn amber" disabled={personId == null || busy} onClick={run}>
        {busy ? "Computing…" : `Remove ${personLabel || "selected person"}`}
      </button>
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
