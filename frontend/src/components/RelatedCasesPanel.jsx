const CHANNELS = ["topology", "temporal", "financial", "roles"];

export default function RelatedCasesPanel({ relatedCases }) {
  const rows = relatedCases?.related || [];
  return (
    <article className="panel-card dna">
      <h2>
        Related Cases (Case DNA) <span className="badge-new">NEW</span>
      </h2>
      <div className="stack">
        {rows.map((r) => {
          const pct = Math.round((r.overall || 0) * 100);
          return (
            <div className="item" key={r.case_id}>
              <div>
                <strong>#{r.case_id}</strong> {r.crime_head || ""} · overall {pct}%
              </div>
              <div className="bars">
                {CHANNELS.map((ch) => {
                  const v = r.channels?.[ch] ?? 0;
                  return (
                    <span key={ch} style={{ display: "contents" }}>
                      <span>{ch}</span>
                      <div className="bar">
                        <i style={{ width: `${Math.max(4, v * 100)}%` }} />
                      </div>
                      <span>{Number(v).toFixed(2)}</span>
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
        {!rows.length && <div className="muted">No related cases.</div>}
      </div>
    </article>
  );
}
