import { useMemo, useState } from "react";
import { apiError, confirmExtraction, createCase, uploadOcrDocument, uploadPdf, verifyOcrLines } from "../api";
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
  const [mode, setMode] = useState("auto"); // "auto", "digital", "trocr"
  const [draft, setDraft] = useState(null);
  const [ocrDoc, setOcrDoc] = useState(null);
  const [ocrLines, setOcrLines] = useState([]);
  const [selectedPageIdx, setSelectedPageIdx] = useState(0);
  const [filterReviewOnly, setFilterReviewOnly] = useState(false);
  const [entities, setEntities] = useState([]);
  const [relations, setRelations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);
  const [createNew, setCreateNew] = useState(true);
  const [showPreview, setShowPreview] = useState(false);
  const [ocrVerified, setOcrVerified] = useState(false);
  const [reviewerName, setReviewerName] = useState("investigator-1");
  const [docViewMode, setDocViewMode] = useState("original"); // "original" or "overlay"
  const [showDebug, setShowDebug] = useState(false);

  const previewGraph = useMemo(
    () => draftToGraph(entities.filter(e => e.included), relations.filter(r => r.included), draft?.filename || ocrDoc?.filename),
    [entities, relations, draft, ocrDoc]
  );

  const isImageFile = useMemo(() => {
    if (!file?.name) return false;
    const n = file.name.toLowerCase();
    return n.endsWith(".png") || n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".webp") || n.endsWith(".bmp") || n.endsWith(".tiff");
  }, [file]);

  async function handleDigitalExtract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    setOcrDoc(null);
    setOcrLines([]);
    try {
      const data = await uploadPdf(caseId, file);
      setDraft(data);
      setEntities((data.entities || []).map((e, i) => ({ ...e, included: true, _id: i })));
      setRelations((data.relations || []).map((r, i) => ({ ...r, included: true, _id: i })));
      setShowPreview(true);
      if (data.ocr_required) {
        setInfo("Scanned document detected — no digital text found. Recommended: Run TrOCR Handwritten OCR below.");
      }
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleTrOCRExtract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    setDraft(null);
    setOcrVerified(false);
    try {
      setInfo("Running Microsoft TrOCR handwritten line segmentation & inference…");
      const data = await uploadOcrDocument(caseId, file);
      setOcrDoc(data);
      setOcrLines(data.lines || []);
      setSelectedPageIdx(0);
      setEntities((data.entities || []).map((e, i) => ({ ...e, included: true, _id: i })));
      setRelations((data.relations || []).map((r, i) => ({ ...r, included: true, _id: i })));
      setShowPreview(true);
      setInfo(`TrOCR complete (${data.summary?.device || "cpu"}). ${data.lines?.length || 0} text lines detected.`);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  function handleLineTextChange(lineIdx, newText) {
    setOcrLines(prev =>
      prev.map(l =>
        l.line_index === lineIdx
          ? { ...l, corrected_text: newText, is_corrected: true, tier: "ACCEPTED" }
          : l
      )
    );
  }

  async function handleVerifyOcr() {
    if (!ocrDoc?.document_id || caseId == null) return;
    setBusy(true);
    setErr(null);
    try {
      const corrections = ocrLines.map(l => ({
        line_index: l.line_index,
        corrected_text: l.corrected_text,
        rationale: l.is_corrected ? "Investigator line edit" : "Verified line text",
      }));

      const res = await verifyOcrLines(caseId, {
        document_id: ocrDoc.document_id,
        lines: corrections,
        reviewer: reviewerName,
      });

      setOcrVerified(true);
      setOcrLines(res.lines || []);
      setEntities((res.entities || []).map((e, i) => ({ ...e, included: true, _id: i })));
      setRelations((res.relations || []).map((r, i) => ({ ...r, included: true, _id: i })));
      setInfo(`OCR Verified! ${res.corrections_logged} modification(s) logged to audit trail (SHA-256). Entity extraction updated.`);
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
        const sourceName = ocrDoc?.filename || draft?.filename || "Uploaded Document";
        const newCase = await createCase({
          brief_facts: `Extracted from ${sourceName} via ${ocrDoc ? "Microsoft TrOCR" : "PDF extract"}.`,
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

  const filteredLines = useMemo(() => {
    if (!filterReviewOnly) return ocrLines;
    return ocrLines.filter(l => l.tier !== "ACCEPTED");
  }, [ocrLines, filterReviewOnly]);

  const confidenceCounts = useMemo(() => {
    const accepted = ocrLines.filter(l => l.tier === "ACCEPTED").length;
    const review = ocrLines.filter(l => l.tier === "REVIEW_RECOMMENDED").length;
    const manual = ocrLines.filter(l => l.tier === "MANUAL_REVIEW_REQUIRED").length;
    return { accepted, review, manual, total: ocrLines.length };
  }, [ocrLines]);

  return (
    <article className="panel-card upload" id="uploadCard">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h2>
          Upload Document <span className="badge-new">INGEST</span>
        </h2>
        <span className="muted" style={{ fontSize: 12 }}>
          Microsoft TrOCR Base Handwritten Model Supported
        </span>
      </div>
      <p className="muted" style={{ marginTop: 2, marginBottom: 12 }}>
        Ingest typed or handwritten evidence (FIRs, field notes, statements). Handwritten documents run through Microsoft TrOCR with line detection and confidence tiers.
      </p>

      {/* File Selection */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="file"
          accept="application/pdf,image/*"
          onChange={(e) => {
            const f = e.target.files?.[0] || null;
            setFile(f);
            setDraft(null);
            setOcrDoc(null);
            setOcrLines([]);
            setErr(null);
            setInfo(null);
          }}
        />
        {file && (
          <span className="muted" style={{ fontSize: 13 }}>
            Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
          </span>
        )}
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
        <button
          className="btn amber"
          type="button"
          disabled={!file || busy}
          onClick={handleTrOCRExtract}
          title="Run Microsoft TrOCR on handwritten text lines"
          style={{ display: "flex", alignItems: "center", gap: 6 }}
        >
          <span>✍️</span> {busy && ocrDoc == null && !draft ? "Running TrOCR…" : "Transcribe Handwritten (TrOCR)"}
        </button>

        {!isImageFile && (
          <button
            className="btn"
            type="button"
            disabled={!file || busy}
            onClick={handleDigitalExtract}
            title="Fast digital text extraction for typed PDFs"
          >
            📄 Extract Digital PDF
          </button>
        )}

        {(draft || ocrDoc) && (
          <label style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", fontSize: 13 }} className="muted">
            <input
              type="checkbox"
              checked={createNew}
              onChange={(e) => setCreateNew(e.target.checked)}
            />
            <span title="When ON, extraction is saved to a brand new case. When OFF, it merges into current case.">
              {createNew ? "🆕 Save to NEW case" : "➕ Merge into current case"}
            </span>
          </label>
        )}
      </div>

      {err && <div className="error-inline" style={{ marginTop: 10 }}>{err}</div>}
      {info && <div className="info-inline" style={{ marginTop: 10, color: "#ffa366" }}>{info}</div>}

      {/* Handwritten OCR Review View: Side-by-Side */}
      {ocrDoc && (
        <section className="ocr-review-section" style={{ marginTop: 16 }}>
          {/* Warning banner for suspicious low line count */}
          {(ocrDoc.summary?.suspicious_low_line_count || ocrDoc.summary?.warning) && (
            <div
              className="ocr-warning-banner"
              style={{
                background: "rgba(255, 77, 77, 0.12)",
                border: "1px solid #ff4d4d",
                color: "#ff8585",
                padding: "10px 14px",
                borderRadius: 8,
                marginBottom: 12,
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 13,
              }}
            >
              <span style={{ fontSize: 20 }}>⚠️</span>
              <div>
                <strong>Document Flagged for Manual Review:</strong>{" "}
                {ocrDoc.summary?.warning || "Suspiciously few lines detected (<5) on a page containing substantial handwriting. Verification required."}
              </div>
            </div>
          )}

          {/* Header & Stats Banner */}
          <div className="ocr-header-bar" style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "10px 14px",
            background: "#181818",
            borderRadius: 8,
            border: "1px solid #333",
            flexWrap: "wrap",
            gap: 10,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 14 }}>{ocrDoc.filename}</strong>
              <span className="badge" style={{ background: "#252525", color: "#ff8533", border: "1px solid #444" }}>
                {ocrDoc.lines?.length || 0} Lines Detected
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                Device: <span style={{ color: "#ff8533" }}>{ocrDoc.summary?.device || "cpu"}</span>
              </span>
            </div>

            {/* Confidence Tiers Badges & Actions */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
              <span className="badge-chip chip-accepted" title="Confidence ≥ 90%">
                ● Accept: {confidenceCounts.accepted}
              </span>
              <span className="badge-chip chip-review" title="Confidence 70% – 89%">
                ▲ Review: {confidenceCounts.review}
              </span>
              <span className="badge-chip chip-manual" title="Confidence < 70%">
                ✕ Manual: {confidenceCounts.manual}
              </span>
              <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", marginLeft: 6 }}>
                <input
                  type="checkbox"
                  checked={filterReviewOnly}
                  onChange={(e) => setFilterReviewOnly(e.target.checked)}
                />
                <span className="muted">Review needed ({confidenceCounts.review + confidenceCounts.manual})</span>
              </label>
              <button
                type="button"
                className="btn-sm"
                onClick={() => setShowDebug((v) => !v)}
                style={{ marginLeft: 6, fontSize: 11 }}
                title="View line segmentation metrics and bounding boxes"
              >
                {showDebug ? "Hide Debug" : "🔍 Debug Info"}
              </button>
            </div>
          </div>

          {/* Collapsible Debug Panel */}
          {showDebug && (
            <div
              className="ocr-debug-panel"
              style={{
                background: "#0d0d0d",
                border: "1px dashed #444",
                borderRadius: 8,
                padding: "12px 14px",
                marginTop: 10,
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <strong style={{ color: "#00d2ff" }}>Line Segmentation & Detection Debug Info</strong>
                <span className="muted">
                  Total Lines: {ocrDoc.lines?.length || 0} | Deskew: {ocrDoc.summary?.skew_angle ?? 0}°
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10, marginBottom: 8 }}>
                <div style={{ background: "#161616", padding: 8, borderRadius: 4, border: "1px solid #282828" }}>
                  <span className="muted">Detected Lines:</span> <strong>{ocrDoc.lines?.length || 0}</strong>
                </div>
                <div style={{ background: "#161616", padding: 8, borderRadius: 4, border: "1px solid #282828" }}>
                  <span className="muted">Deskew Angle:</span> <strong>{ocrDoc.summary?.skew_angle ?? 0}°</strong>
                </div>
                <div style={{ background: "#161616", padding: 8, borderRadius: 4, border: "1px solid #282828" }}>
                  <span className="muted">Suspicious Low Count:</span>{" "}
                  <strong style={{ color: ocrDoc.summary?.suspicious_low_line_count ? "#ff4d4d" : "#00e676" }}>
                    {ocrDoc.summary?.suspicious_low_line_count ? "FLAGGED (YES)" : "NO"}
                  </strong>
                </div>
                <div style={{ background: "#161616", padding: 8, borderRadius: 4, border: "1px solid #282828" }}>
                  <span className="muted">Model:</span> <strong>microsoft/trocr-base-handwritten</strong>
                </div>
              </div>
              <details style={{ marginTop: 6, cursor: "pointer" }}>
                <summary className="muted" style={{ fontWeight: 600 }}>
                  View All Bounding Boxes ({ocrDoc.lines?.length || 0} boxes)
                </summary>
                <div style={{ maxHeight: 120, overflowY: "auto", marginTop: 6, background: "#111", padding: 8, borderRadius: 4, fontFamily: "monospace", fontSize: 11 }}>
                  {ocrDoc.lines?.map((l) => (
                    <div key={l.line_index} style={{ color: "#b8b8b8" }}>
                      Line #{l.line_index + 1}: x={l.bbox?.[0]}, y={l.bbox?.[1]}, w={l.bbox?.[2]}, h={l.bbox?.[3]} | Conf: {Number(l.confidence).toFixed(1)}% | Text: "{l.original_text}"
                    </div>
                  ))}
                </div>
              </details>
            </div>
          )}

          {/* Side by Side Split */}
          <div className="ocr-split-layout" style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.3fr",
            gap: 16,
            marginTop: 12,
            minHeight: 480,
          }}>
            {/* Left Column: Document Viewer (Original or Bounding Box Overlay) */}
            <div className="ocr-doc-viewer" style={{
              background: "#111",
              border: "1px solid #2a2a2a",
              borderRadius: 8,
              padding: 12,
              display: "flex",
              flexDirection: "column",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
                {/* View mode toggle */}
                <div style={{ display: "flex", gap: 4 }}>
                  <button
                    type="button"
                    className={docViewMode === "original" ? "btn-sm amber" : "btn-sm"}
                    onClick={() => setDocViewMode("original")}
                    style={{ fontSize: 11 }}
                  >
                    Original Page
                  </button>
                  <button
                    type="button"
                    className={docViewMode === "overlay" ? "btn-sm amber" : "btn-sm"}
                    onClick={() => setDocViewMode("overlay")}
                    style={{ fontSize: 11 }}
                    title="View page with detected cyan bounding boxes and line numbers"
                  >
                    🔲 Line Bounding Boxes
                  </button>
                </div>

                {ocrDoc.page_urls?.length > 1 && (
                  <div style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 12 }}>
                    <span className="muted">Page:</span>
                    {ocrDoc.page_urls.map((_, pIdx) => (
                      <button
                        key={pIdx}
                        type="button"
                        className={selectedPageIdx === pIdx ? "btn-sm amber" : "btn-sm"}
                        onClick={() => setSelectedPageIdx(pIdx)}
                      >
                        {pIdx + 1}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div style={{
                flex: 1,
                overflow: "auto",
                background: "#080808",
                borderRadius: 6,
                border: "1px solid #222",
                display: "flex",
                justifyContent: "center",
                alignItems: "flex-start",
                padding: 8,
                maxHeight: 520,
              }}>
                {docViewMode === "overlay" && ocrDoc.overlay_urls?.[selectedPageIdx] ? (
                  <img
                    src={ocrDoc.overlay_urls[selectedPageIdx]}
                    alt="Document page with line segmentation bounding boxes"
                    style={{ maxWidth: "100%", height: "auto", objectFit: "contain", borderRadius: 4 }}
                  />
                ) : ocrDoc.page_urls?.[selectedPageIdx] ? (
                  <img
                    src={ocrDoc.page_urls[selectedPageIdx]}
                    alt="Original document page"
                    style={{ maxWidth: "100%", height: "auto", objectFit: "contain", borderRadius: 4 }}
                  />
                ) : (
                  <div className="muted" style={{ padding: 40 }}>Document image not available.</div>
                )}
              </div>
              <div style={{ marginTop: 8, fontSize: 11 }} className="muted">
                Original file preserved unmodified at: <code style={{ color: "#ffa366" }}>{ocrDoc.original_file_url}</code>
              </div>
            </div>

            {/* Right Column: OCR Lines with Confidence & In-place Correction */}
            <div className="ocr-lines-editor" style={{
              background: "#111",
              border: "1px solid #2a2a2a",
              borderRadius: 8,
              padding: 12,
              display: "flex",
              flexDirection: "column",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h4 style={{ margin: 0, fontSize: 13, textTransform: "uppercase", color: "#b8b8b8" }}>
                  Detected Line Crops & Transcripts ({filteredLines.length} lines)
                </h4>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                  <span className="muted">Reviewer:</span>
                  <input
                    type="text"
                    value={reviewerName}
                    onChange={(e) => setReviewerName(e.target.value)}
                    style={{ width: 120, padding: "2px 6px", fontSize: 11, background: "#181818", border: "1px solid #3a3a3a", color: "#fff", borderRadius: 4 }}
                  />
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto", maxHeight: 460, display: "flex", flexDirection: "column", gap: 10, paddingRight: 4 }}>
                {filteredLines.map((line) => {
                  const isAccepted = line.tier === "ACCEPTED";
                  const isReview = line.tier === "REVIEW_RECOMMENDED";
                  const isManual = line.tier === "MANUAL_REVIEW_REQUIRED";

                  const badgeClass = isAccepted ? "badge-accepted" : isReview ? "badge-review" : "badge-manual";
                  const badgeLabel = isAccepted ? "≥90% Accept" : isReview ? "70-89% Review" : "<70% Manual";

                  return (
                    <div
                      key={line.line_index}
                      className={`ocr-line-card ${line.is_corrected ? "card-corrected" : ""}`}
                      style={{
                        background: isManual ? "#201010" : isReview ? "#221a0f" : "#161616",
                        border: `1px solid ${isManual ? "#662222" : isReview ? "#553810" : "#2e2e2e"}`,
                        borderRadius: 6,
                        padding: "8px 10px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      {/* Top bar: Line number, thumbnail crop, bbox, confidence badge */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 12, fontWeight: "bold", color: "#888" }}>
                            #{line.line_index + 1}
                          </span>
                          {line.image_data && (
                            <img
                              src={line.image_data}
                              alt={`Line crop #${line.line_index + 1}`}
                              style={{
                                maxHeight: 28,
                                maxWidth: 220,
                                border: "1px solid #444",
                                borderRadius: 3,
                                background: "#fff",
                                objectFit: "contain",
                              }}
                            />
                          )}
                          {line.bbox && (
                            <span className="muted" style={{ fontSize: 10, fontFamily: "monospace" }}>
                              [{line.bbox[0]},{line.bbox[1]},{line.bbox[2]},{line.bbox[3]}]
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span className={`confidence-badge ${badgeClass}`} style={{ fontSize: 11 }}>
                            {badgeLabel} ({Number(line.confidence).toFixed(1)}%)
                          </span>
                          {line.is_corrected && (
                            <span className="badge-edited" style={{ fontSize: 10 }}>EDITED</span>
                          )}
                        </div>
                      </div>

                      {/* Line transcription editable input */}
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <input
                          type="text"
                          value={line.corrected_text}
                          onChange={(e) => handleLineTextChange(line.line_index, e.target.value)}
                          placeholder="Line transcription..."
                          style={{
                            flex: 1,
                            background: "#0c0c0c",
                            color: "#fff",
                            border: `1px solid ${line.is_corrected ? "#ff8533" : "#383838"}`,
                            borderRadius: 4,
                            padding: "6px 8px",
                            fontSize: 13,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
                {!filteredLines.length && (
                  <div className="muted" style={{ padding: 20, textAlign: "center" }}>
                    No lines matching the current filter.
                  </div>
                )}
              </div>

              {/* Verify & Save OCR Button */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, paddingTop: 8, borderTop: "1px solid #222" }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  {ocrVerified ? "Verified ✅ (Hashed in audit log)" : "Unverified edits pending save"}
                </span>
                <button
                  className="btn ok"
                  type="button"
                  disabled={busy}
                  onClick={handleVerifyOcr}
                >
                  {busy ? "Saving…" : "Verify & Save OCR (Audit Log)"}
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Graph Preview & Entity / Relation Review Draft */}
      {(draft || ocrDoc) && (
        <>
          {showPreview && (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <h3 className="subhead" style={{ margin: 0 }}>Graph Preview — Extracted Entities</h3>
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
                    No nodes to preview yet — check some entities below or verify OCR text.
                  </div>
                )}
              </div>
            </div>
          )}

          <h3 className="subhead" style={{ marginTop: 16 }}>Extracted Entities</h3>
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
            {!entities.length && <div className="muted">No entities extracted yet.</div>}
          </div>

          <h3 className="subhead">Extracted Relations</h3>
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
            {!relations.length && <div className="muted">No relations extracted yet.</div>}
          </div>

          <button className="btn ok" type="button" disabled={busy} onClick={confirm} style={{ marginTop: 12 }}>
            {busy ? "Writing…" : (createNew ? "Confirm → New Canvas" : "Confirm & Add to Graph")}
          </button>
        </>
      )}
    </article>
  );
}
