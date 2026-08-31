import { useEffect, useState } from "react";
import { apiError, getContradictions } from "../api";

export default function ContradictionPanel({ caseId, personId }) {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (caseId == null || personId == null) {
      setItems([]);
      setErr(null);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    getContradictions(caseId, personId)
      .then((data) => {
        if (!cancelled) {
          setItems(data.contradictions || []);
          setErr(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setItems([]);
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
    <article className="panel-card contra" id="contraCard">
      <h2>Contradictions</h2>
      <div className="stack">
        {personId == null && <div className="muted">Select a PERSON node to search conflicts.</div>}
        {loading && <div className="muted">Checking…</div>}
        {err && <div className="error-inline">{err}</div>}
        {personId != null &&
          !loading &&
          items.map((c, i) => (
            <div className="item" key={i}>
              {c.description}
              <div className="muted">
                {c.distance_km} km · {c.minutes_apart} min
              </div>
            </div>
          ))}
        {personId != null && !loading && !err && !items.length && (
          <div className="muted">No spatial-temporal contradictions.</div>
        )}
      </div>
    </article>
  );
}
