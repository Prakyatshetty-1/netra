const NAV = [
  { id: "graph", label: "Graph" },
  { id: "identity", label: "Identity" },
  { id: "dna", label: "Case DNA" },
  { id: "hypotheses", label: "Hypotheses" },
  { id: "upload", label: "Upload Document" },
  { id: "copilot", label: "Copilot" },
];

export default function Sidebar({
  cases,
  selectedCaseId,
  selectedCase,
  onSelectCase,
  error,
  page,
  onNav,
}) {
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
        {error && <div className="error-inline">{error}. Is the FastAPI backend running?</div>}
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
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-btn ${page === item.id ? "active" : ""}`}
            onClick={() => onNav(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
