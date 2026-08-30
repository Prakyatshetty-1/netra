export default function Sidebar({ cases, selectedCaseId, selectedCase, onSelectCase, error }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">N</div>
        <div>
          <div className="brand-name">NETRA</div>
          <div className="brand-sub">Evidence-centric analysis</div>
        </div>
      </div>
      <label className="field">
        <span>Case</span>
        <select
          value={selectedCaseId ?? ""}
          onChange={(e) => onSelectCase(Number(e.target.value))}
        >
          {cases.map((c) => (
            <option key={c.case_id} value={c.case_id}>
              #{c.case_id} · {c.crime_head || c.crime_no} ({c.edge_count}e)
            </option>
          ))}
        </select>
      </label>
      <div className="case-meta">
        {error && <div>{error}. Is the FastAPI backend running?</div>}
        {selectedCase && (
          <>
            <div>
              <strong>{selectedCase.crime_head || "—"}</strong> · {selectedCase.crime_group || ""}
            </div>
            <div>{selectedCase.crime_no}</div>
            <div>
              {selectedCase.person_count} persons · {selectedCase.edge_count} edges
            </div>
            <div>{(selectedCase.brief_facts || "").slice(0, 220)}</div>
          </>
        )}
      </div>
      <nav className="nav">
        <button type="button" className="nav-btn active">Graph</button>
        <button type="button" className="nav-btn">Identity</button>
        <button type="button" className="nav-btn">Case DNA</button>
        <button type="button" className="nav-btn">Hypotheses</button>
        <button type="button" className="nav-btn">Copilot</button>
      </nav>
    </aside>
  );
}
