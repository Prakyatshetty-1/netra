import { useMemo, useState } from "react";
import { apiError, confirmExtraction, createCase, uploadPdf } from "../api";
import GraphCanvas from "./GraphCanvas";

const REL_TYPES = [
  "NAMED_TOGETHER",
  "HAS_PHONE",
  "ASSOCIATED_WITH_VEHICLE",
  "MENTIONED_AT_LOCATION",
  "MENTIONED_ON_DATE",
];

function draftToGraph(entities, relations, filename) {
  const labelType = (lab) => {
    const u = (lab || "").toUpperCase();
    if (u === "PERSON" || u === "LOC" || u === "LOCATION" || u === "DATE" ||
        u === "ORG" || u === "PHONE" || u === "VEHICLE") return u === "LOCATION" ? "LOC" : u;
    return u || "PERSON";
  };

  const nodeMap = new Map();
  const nodes = [];
  let idx = 1;

  for (const e of entities) {
    const text = (e.text || "").trim();
    const t = labelType(e.label);
    const key = `${t}|${text.toLowerCase()}`;
    if (!text || nodeMap.has(key)) continue;
    const id = `DRAFT-${t}:${idx++}`;
    nodeMap.set(key, id);
    nodes.push({ id, type: t, label: text, centrality: 0.3 });
  }

  const edges = [];
  let eid = 1;
  for (const r of relations) {
    const src = (r.source || "").trim();
    const tgt = (r.target || "").trim();
    if (!src || !tgt) continue;
    let srcId = null;
    let tgtId = null;
    for (const [k, v] of nodeMap) {
      const [lab, name] = k.split("|");
      if (name === src.toLowerCase()) srcId = v;
      if (name === tgt.toLowerCase()) tgtId = v;
    }
    if (!srcId || !tgtId) continue;
    edges.push({
      id: eid++,
      source: srcId,
      target: tgtId,
      relation: r.type || "NAMED_TOGETHER",
      source_type: "PDF_UPLOAD",
      confidence: r.confidence ?? 0.6,
      burst: true,
    });
  }

  return { case_id: 0, nodes, edges, matched_node: null, _filename: filename };
}

export default function UploadPanel({ caseId, onConfirmed }) {
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [entities, setEntities] = useState([]);
  const [relations, setRelations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);
  const [createNew, setCreateNew] = useState(true);
  const [showPreview, setShowPreview] = useState(false);

  const previewGraph = useMemo(
    () => draftToGraph(entities.filter(e => e.included), relations.filter(r => r.included), draft?.filename),
    [entities, relations, draft]
  );

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
      setShowPreview(true);
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

      let targetCaseId = caseId;
      if (createNew) {
        const newCase = await createCase({
          brief_facts: `Extracted from ${draft?.filename || "PDF upload"}.`,
        });
        targetCaseId = newCase.case_id;
        setInfo(`Created new case #${targetCaseId} for this document…`);
      }

      const data = await confirmExtraction(targetCaseId, payload);

      if (onConfirmed) {
        await onConfirmed(data.graph, {
          newCaseId: createNew ? targetCaseId : null,
          edgesAdded: data.edges_added || 0,
        });
      }

      if (!createNew) {
        setInfo(`Added ${data.edges_added || 0} PDF_UPLOAD edges. Graph refreshed.`);
      }
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
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn amber" type="button" disabled={!file || busy} onClick={extract}>
          {busy && !draft ? "Extracting…" : "Extract"}
        </button>
        {draft && (
          <label style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", fontSize: 13 }} className="muted">
            <input
              type="checkbox"
              checked={createNew}
              onChange={(e) => setCreateNew(e.target.checked)}
            />
            <span title="When ON, extraction is saved to a brand new case (isolated canvas). When OFF, it merges into the currently selected case.">
              {createNew ? "🆕 Save to NEW case (separate canvas)" : "➕ Merge into current case"}
            </span>
          </label>
        )}
      </div>
      {err && <div className="error-inline">{err}</div>}
      {info && <div className="muted">{info}</div>}
      {draft && (
        <>
          <div className="muted" style={{ marginTop: 8 }}>
            {draft.filename} — {(draft.raw_text_preview || "").slice(0, 160)}
          </div>

          {showPreview && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <h3 className="subhead" style={{ margin: 0 }}>Preview — New Canvas</h3>
                <button
                  type="button"
                  className="linkish"
                  onClick={() => setShowPreview(v => !v)}
                  style={{ fontSize: 12 }}
                >
                  {showPreview ? "Hide preview" : "Show preview"}
                </button>
              </div>
              <div
                className="graph-canvas preview-canvas"
                style={{ height: 280, border: "1px dashed #3a3a3a", borderRadius: 8, background: "#0f0f0f" }}
              >
                {previewGraph.nodes.length ? (
                  <GraphCanvas graphData={previewGraph} onNodeClick={() => {}} selectedPersonId={null} />
                ) : (
                  <div className="muted" style={{ padding: 20, textAlign: "center" }}>
                    No nodes to preview yet — check some entities below.
                  </div>
                )}
              </div>
            </div>
          )}

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
            {busy ? "Writing…" : (createNew ? "Confirm → New Canvas" : "Confirm & Add to Graph")}
          </button>
        </>
      )}
    </article>
  );
}
