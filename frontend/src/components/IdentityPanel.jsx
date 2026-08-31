export default function IdentityPanel({ identity }) {
  const candidates = identity?.candidates || [];
  return (
    <article className="panel-card identity" id="identityCard">
      <h2>
        Identity Candidates <span className="badge-new">THRESHOLD</span>
      </h2>
      <div className="stack">
        {candidates.slice(0, 8).map((c) => (
          <div className="item" key={c.candidate_id}>
            <span className={`badge ${c.status === "RESOLVED" ? "ok" : ""}`}>{c.status}</span>
            <div>
              {c.name_a} ↔ {c.name_b}
            </div>
            <div className="muted">
              conf {Number(c.model_confidence).toFixed(3)} · cases {c.case_a}/{c.case_b}
            </div>
          </div>
        ))}
        {!candidates.length && <div className="muted">No identity candidates.</div>}
      </div>
    </article>
  );
}
