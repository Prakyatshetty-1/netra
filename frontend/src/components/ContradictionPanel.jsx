import { useEffect, useState } from "react";
import { getContradictions } from "../api";

export default function ContradictionPanel({ caseId, personId }) {
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (caseId == null || personId == null) {
      setItems([]);
      return undefined;
    }
    let cancelled = false;
    getContradictions(caseId, personId).then((data) => {
      if (!cancelled) setItems(data.contradictions || []);
    });
    return () => {
      cancelled = true;
    };
  }, [caseId, personId]);

  return (
    <article className="panel-card contra">
      <h2>Contradictions</h2>
      <div className="stack">
        {personId == null && <div className="muted">Select a person to search conflicts.</div>}
        {personId != null &&
          items.map((c, i) => (
            <div className="item" key={i}>
              {c.description}
              <div className="muted">
                {c.distance_km} km · {c.minutes_apart} min
              </div>
            </div>
          ))}
        {personId != null && !items.length && (
          <div className="muted">No spatial-temporal contradictions.</div>
        )}
      </div>
    </article>
  );
}
