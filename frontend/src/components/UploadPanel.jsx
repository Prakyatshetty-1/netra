import { useState } from "react";
import { apiError, confirmExtraction, uploadPdf } from "../api";

const REL_TYPES = [
  "NAMED_TOGETHER",
  "HAS_PHONE",
  "ASSOCIATED_WITH_VEHICLE",
  "MENTIONED_AT_LOCATION",
  "MENTIONED_ON_DATE",
];

export default function UploadPanel({ caseId, onConfirmed }) {
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [entities, setEntities] = useState([]);
  const [relations, setRelations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);

  async function extract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const data = await uploadPdf(caseId, file);
      setDraft(data);
      setEntities((data.entities || []).map((e, i) => ({ ...e, included: true, _id: i })));
      setRelations((data.relations || []).map((r, i) => ({ ...r, included: true, _id: i })));
      if (data.ocr_required) {
        setInfo("No extractable text — scanned PDF needs OCR (not run in this prototype).");
      }
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (caseId == null) return;
    setBusy(true);
    setErr(null);
    try {
      const payload = {
        entities: entities.map(({ _id, ...e }) => e),
        relations: relations.map(({ _id, ...r }) => r),
      };
      const data = await confirmExtraction(caseId, payload);
      setInfo(`Added ${data.edges_added || 0} PDF_UPLOAD edges. Graph refreshed.`);
      if (onConfirmed) await onConfirmed(data.graph);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel-card upload" id="uploadCard">
      <h2>
        Upload Document <span className="badge-new">INGEST</span>
      </h2>
      <p className="muted">
        Extraction is a review draft (confidence 0.6 co-occurrence). Nothing is written until you confirm.
      </p>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn amber" type="button" disabled={!file || busy} onClick={extract}>
          {busy && !draft ? "Extracting…" : "Extract"}
        </button>
      </div>
      {err && <div className="error-inline">{err}</div>}
      {info && <div className="muted">{info}</div>}
      {draft && (
        <>
          <div className="muted" style={{ marginTop: 8 }}>
            {draft.filename} — {(draft.raw_text_preview || "").slice(0, 160)}
          </div>
          <h3 className="subhead">Entities</h3>
          <div className="review-table">
            {entities.map((e) => (
              <label key={e._id} className="review-row">
                <input
                  type="checkbox"
                  checked={e.included}
                  onChange={() =>
                    setEntities((list) =>
                      list.map((x) => (x._id === e._id ? { ...x, included: !x.included } : x))
                    )
                  }
                />
                <span>{e.text}</span>
                <span className="badge">{e.label}</span>
              </label>
            ))}
            {!entities.length && <div className="muted">No entities extracted.</div>}
          </div>
          <h3 className="subhead">Relations</h3>
          <div className="review-table">
            {relations.map((r) => (
              <label key={r._id} className="review-row">
                <input
                  type="checkbox"
                  checked={r.included}
                  onChange={() =>
                    setRelations((list) =>
                      list.map((x) => (x._id === r._id ? { ...x, included: !x.included } : x))
                    )
                  }
                />
                <span>
                  {r.source} → {r.target}
                </span>
                <select
                  value={r.type}
                  onChange={(e) =>
                    setRelations((list) =>
                      list.map((x) => (x._id === r._id ? { ...x, type: e.target.value } : x))
                    )
                  }
                >
                  {REL_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <span className="muted">{Number(r.confidence).toFixed(1)}</span>
              </label>
            ))}
            {!relations.length && <div className="muted">No relations extracted.</div>}
          </div>
          <button className="btn ok" type="button" disabled={busy} onClick={confirm} style={{ marginTop: 8 }}>
            {busy ? "Writing…" : "Confirm & Add to Graph"}
          </button>
        </>
      )}
    </article>
  );
}
