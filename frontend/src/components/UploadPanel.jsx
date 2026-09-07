import { useMemo, useState } from "react";
import { apiError, confirmExtraction, createCase, uploadCctvVideo, uploadOcrDocument, uploadPdf, verifyOcrLines } from "../api";
import GraphCanvas from "./GraphCanvas";

const REL_TYPES = [
  "NAMED_TOGETHER",
  "HAS_PHONE",
  "ASSOCIATED_WITH_VEHICLE",
  "MENTIONED_AT_LOCATION",
  "MENTIONED_ON_DATE",
];

function toFullUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) return url;
  const base = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
}

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

export default function UploadPanel({ caseId, onConfirmed, panelMode = "all" }) {
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
  const [useGemini, setUseGemini] = useState(true);
  const [geminiKey, setGeminiKey] = useState(() => localStorage.getItem("gemini_api_key") || "");
  const [showKeyInput, setShowKeyInput] = useState(false);

  const handleKeyChange = (val) => {
    setGeminiKey(val);
    localStorage.setItem("gemini_api_key", val);
  };

  const previewGraph = useMemo(
    () => draftToGraph(entities.filter(e => e.included), relations.filter(r => r.included), draft?.filename || ocrDoc?.filename),
    [entities, relations, draft, ocrDoc]
  );

  const [cctvResult, setCctvResult] = useState(null);
  const [selectedFrameIdx, setSelectedFrameIdx] = useState(0);
  const [sampleRateSec, setSampleRateSec] = useState(1.0);
  const [confThreshold, setConfThreshold] = useState(0.50);

  const isImageFile = useMemo(() => {
    if (!file?.name) return false;
    const n = file.name.toLowerCase();
    return n.endsWith(".png") || n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".webp") || n.endsWith(".bmp") || n.endsWith(".tiff");
  }, [file]);

  const isVideoFile = useMemo(() => {
    if (!file?.name) return false;
    const n = file.name.toLowerCase();
    return n.endsWith(".mp4") || n.endsWith(".avi") || n.endsWith(".mov") || n.endsWith(".mkv") || n.endsWith(".webm");
  }, [file]);

  async function handleCctvExtract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    setDraft(null);
    setOcrDoc(null);
    setCctvResult(null);
    try {
      setInfo("Uploading CCTV video & extracting frames with YOLO object detection…");
      const data = await uploadCctvVideo(caseId, file, sampleRateSec, confThreshold);
      setCctvResult(data);
      setSelectedFrameIdx(0);
      setInfo(`CCTV Object Detection complete (${data.device}). ${data.total_detections} objects detected across ${data.frames?.length || 0} sampled frames.`);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

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
        setInfo("Scanned document detected — no digital text found. Recommended: Run Gemini Vision OCR below.");
      }
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleOcrExtract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    setDraft(null);
    setOcrVerified(false);
    try {
      setInfo("Running Google Gemini Vision AI text & entity extraction…");
      const data = await uploadOcrDocument(caseId, file, true, geminiKey);
      setOcrDoc(data);
      setOcrLines(data.lines || []);
      setSelectedPageIdx(0);
      setEntities((data.entities || []).map((e, i) => ({ ...e, included: true, _id: i })));
      setRelations((data.relations || []).map((r, i) => ({ ...r, included: true, _id: i })));
      setShowPreview(true);
      const engineName = data.summary?.ocr_engine || "Gemini Vision AI";
      setInfo(`${engineName} complete! ${data.lines?.length || 0} text lines and ${data.entities?.length || 0} entities extracted.`);
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
        const engineTag = ocrDoc?.summary?.ocr_engine || "Document Extract";
        const newCase = await createCase({
          brief_facts: `Extracted from ${sourceName} via ${engineTag}.`,
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

  const isDocOnly = panelMode === "document";
  const isCctvOnly = panelMode === "cctv";

  return (
    <article className="panel-card upload" id="uploadCard">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h2>
          {isDocOnly
            ? "Document & Handwritten OCR Ingestion"
            : isCctvOnly
            ? "Evidence & CCTV Video Ingestion"
            : "Evidence, Document & CCTV Video Ingestion"}{" "}
          <span className="badge-new">INGEST</span>
        </h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {isDocOnly
            ? "Gemini Vision AI & Digital OCR Supported"
            : isCctvOnly
            ? "YOLOv8 CCTV Detection Supported"
            : "YOLOv8 CCTV Detection & Gemini AI Supported"}
        </span>
      </div>
      <p className="muted" style={{ marginTop: 2, marginBottom: 12 }}>
        {isDocOnly
          ? "Upload typed or handwritten documents (PDF, PNG, JPG, WEBP) for Gemini Vision AI OCR and Digital PDF extraction into the case graph."
          : isCctvOnly
          ? "Upload CCTV video clips (MP4, AVI, MOV, MKV, WEBM) for YOLO object detection (people, vehicles) with timestamped frame analysis."
          : "Upload CCTV video clips (MP4, AVI, MOV, MKV) for YOLO object detection (people, vehicles), or upload typed/handwritten documents (PDF, images) for Gemini Vision AI OCR."}
      </p>

      {/* File Selection */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="file"
          accept={
            isDocOnly
              ? "application/pdf,image/*"
              : isCctvOnly
              ? "video/*,.mp4,.avi,.mov,.mkv,.webm"
              : "application/pdf,image/*,video/*,.mp4,.avi,.mov,.mkv,.webm"
          }
          onChange={(e) => {
            const f = e.target.files?.[0] || null;
            setFile(f);
            setDraft(null);
            setOcrDoc(null);
            setCctvResult(null);
            setOcrLines([]);
            setErr(null);
            setInfo(null);
          }}
        />
        {file && (
          <span className="muted" style={{ fontSize: 13 }}>
            Selected: <strong>{file.name}</strong> ({(file.size / 1024 / 1024).toFixed(2)} MB)
          </span>
        )}
      </div>

      {/* Gemini API Key Toggle Input */}
      <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          style={{ padding: "3px 8px", fontSize: 12, background: "rgba(255, 255, 255, 0.06)", border: "1px solid rgba(255,255,255,0.15)" }}
          onClick={() => setShowKeyInput(p => !p)}
        >
          🔑 {showKeyInput ? "Hide Gemini Key" : "Gemini API Key Settings"}
        </button>
        {showKeyInput && (
          <input
            type="password"
            placeholder="Paste GEMINI_API_KEY (optional if set in server .env)"
            value={geminiKey}
            onChange={(e) => handleKeyChange(e.target.value)}
            style={{ padding: "4px 8px", fontSize: 12, width: 280, borderRadius: 4, background: "#132338", color: "#fff", border: "1px solid #334e68" }}
          />
        )}
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
        {isVideoFile ? (
          <button
            className="btn amber"
            type="button"
            disabled={!file || busy}
            onClick={handleCctvExtract}
            title="Run OpenCV Frame Extractor & Ultralytics YOLO Object Detection"
            style={{ display: "flex", alignItems: "center", gap: 6, background: "linear-gradient(135deg, #00d2ff 0%, #0072ff 100%)", color: "#fff" }}
          >
            <span>📹</span> {busy && cctvResult == null ? "Running YOLO Detection…" : "Detect CCTV Objects (YOLO)"}
          </button>
        ) : (
          <button
            className="btn amber"
            type="button"
            disabled={!file || busy}
            onClick={() => handleOcrExtract()}
            title="Extract text and entities using Google Gemini Vision AI"
            style={{ display: "flex", alignItems: "center", gap: 6, background: "linear-gradient(135deg, #e8952e 0%, #ff6b4a 100%)", color: "#fff" }}
          >
            <span>✨</span> {busy && ocrDoc == null && !draft ? "Running Gemini Vision AI…" : "Gemini Vision OCR"}
          </button>
        )}

        {!isImageFile && !isVideoFile && (
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

        {(draft || ocrDoc || cctvResult) && (
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

      {/* CCTV Video Analysis View */}
      {cctvResult && (
        <section className="cctv-analysis-section" style={{ marginTop: 16, background: "#0a1320", border: "1px solid #1c2e47", borderRadius: 8, padding: 14 }}>
          {/* Video Metadata Banner */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, borderBottom: "1px solid #1c2e47", paddingBottom: 10 }}>
            <div>
              <h3 style={{ color: "#00d2ff", margin: 0, fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
                <span>📹</span> {cctvResult.filename}
              </h3>
              <span className="muted" style={{ fontSize: 11, fontFamily: "monospace" }}>
                SHA-256: {cctvResult.file_hash_sha256}
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="badge" style={{ background: "#132338", color: "#00d2ff", border: "1px solid #0072ff" }}>
                Duration: {cctvResult.duration_formatted}
              </span>
              <span className="badge" style={{ background: "#132338", color: "#00d2ff", border: "1px solid #0072ff" }}>
                Resolution: {cctvResult.resolution}
              </span>
              <span className="badge" style={{ background: "#132338", color: "#00d2ff", border: "1px solid #0072ff" }}>
                FPS: {cctvResult.fps}
              </span>
              <span className="badge" style={{ background: "#132338", color: "#00d2ff", border: "1px solid #0072ff" }}>
                Frames: {cctvResult.total_frames}
              </span>
              <span className="badge" style={{ background: "rgba(0,210,255,0.15)", color: "#00d2ff", border: "1px solid #00d2ff" }}>
                Device: {cctvResult.device.toUpperCase()}
              </span>
            </div>
          </div>

          {/* Detections Summary Chips */}
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
            <span className="muted" style={{ fontSize: 12 }}>Detected Objects:</span>
            {Object.entries(cctvResult.summary_counts || {}).map(([cls, count]) => (
              <span key={cls} className="badge-chip" style={{ background: cls === "person" ? "rgba(0, 210, 255, 0.2)" : "rgba(255, 149, 0, 0.2)", color: cls === "person" ? "#00d2ff" : "#ff9500", border: `1px solid ${cls === "person" ? "#00d2ff" : "#ff9500"}` }}>
                {cls.toUpperCase()}: {count}
              </span>
            ))}
            <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
              Total Detections: <strong>{cctvResult.total_detections}</strong>
            </span>
          </div>

          {/* Interactive Frame Detection Viewer & Overlay */}
          {cctvResult.frames && cctvResult.frames.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 14, marginTop: 14 }}>
              {/* Frame Image Overlay */}
              <div style={{ background: "#050a12", border: "1px solid #1c2e47", borderRadius: 6, padding: 8, textAlign: "center" }}>
                <img
                  src={toFullUrl(cctvResult.frames[selectedFrameIdx]?.overlay_url)}
                  alt={`Frame ${cctvResult.frames[selectedFrameIdx]?.frame_number}`}
                  style={{ maxWidth: "100%", maxHeight: 420, borderRadius: 4, objectFit: "contain" }}
                />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8, padding: "0 6px" }}>
                  <span className="muted" style={{ fontSize: 12 }}>
                    Frame #{cctvResult.frames[selectedFrameIdx]?.frame_number}
                  </span>
                  <span style={{ color: "#00d2ff", fontWeight: "bold", fontSize: 13 }}>
                    Timestamp: {cctvResult.frames[selectedFrameIdx]?.timestamp}
                  </span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    Detections: {cctvResult.frames[selectedFrameIdx]?.detections?.length || 0}
                  </span>
                </div>
              </div>

              {/* Detections List for Selected Frame */}
              <div style={{ background: "#050a12", border: "1px solid #1c2e47", borderRadius: 6, padding: 10 }}>
                <h4 style={{ color: "#e8952e", margin: "0 0 8px 0", fontSize: 13 }}>
                  Frame Detections ({cctvResult.frames[selectedFrameIdx]?.timestamp})
                </h4>
                {(!cctvResult.frames[selectedFrameIdx]?.detections || cctvResult.frames[selectedFrameIdx].detections.length === 0) ? (
                  <p className="muted" style={{ fontSize: 12 }}>No objects detected in this frame above confidence threshold (≥0.50).</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 360, overflowY: "auto" }}>
                    {cctvResult.frames[selectedFrameIdx].detections.map((det, dIdx) => (
                      <div key={dIdx} style={{ background: "#101b2b", border: "1px solid #233b5c", borderRadius: 4, padding: "6px 8px", fontSize: 12 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontWeight: "bold", color: det.class === "person" ? "#00d2ff" : "#ff9500" }}>
                          <span>{det.class.toUpperCase()}</span>
                          <span>Confidence: {(det.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="muted" style={{ fontSize: 11, marginTop: 2, fontFamily: "monospace" }}>
                          BBox: [{det.bbox.join(", ")}]
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Interactive Video Timeline Bar */}
          {cctvResult.frames && cctvResult.frames.length > 0 && (
            <div style={{ marginTop: 16, background: "#050a12", border: "1px solid #1c2e47", borderRadius: 6, padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
                <span style={{ color: "#00d2ff", fontWeight: "bold" }}>Video Timeline Markers</span>
                <span className="muted">Click any frame marker to view bounding boxes</span>
              </div>

              {/* Timeline Track */}
              <div style={{ display: "flex", gap: 4, overflowX: "auto", paddingBottom: 6 }}>
                {cctvResult.frames.map((f, idx) => {
                  const hasObjects = f.detections && f.detections.length > 0;
                  const isSelected = idx === selectedFrameIdx;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setSelectedFrameIdx(idx)}
                      style={{
                        padding: "6px 8px",
                        fontSize: 11,
                        borderRadius: 4,
                        cursor: "pointer",
                        border: isSelected ? "2px solid #00d2ff" : "1px solid #233b5c",
                        background: isSelected ? "#0072ff" : hasObjects ? "rgba(0, 210, 255, 0.15)" : "#101b2b",
                        color: isSelected ? "#fff" : hasObjects ? "#00d2ff" : "#666",
                        minWidth: 70,
                        textAlign: "center",
                      }}
                      title={`Timestamp: ${f.timestamp} — ${f.detections?.length || 0} objects`}
                    >
                      <div>{f.timestamp}</div>
                      <div style={{ fontSize: 10, marginTop: 2 }}>
                        {hasObjects ? `● ${f.detections.length}` : "—"}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

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

          {/* Reconstructed TrOCR Text Transcript Box (BEFORE NER processing) */}
          <div style={{ marginTop: 12, marginBottom: 12, background: "#101b2b", border: "1px solid #233b5c", borderRadius: 8, padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <strong style={{ color: "#e8952e", fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                <span>📄</span> Reconstructed OCR Transcript (In Reading Order — Before NER)
              </strong>
              <span className="muted" style={{ fontSize: 11 }}>
                {ocrDoc.raw_text ? `${ocrDoc.raw_text.split('\n').length} Lines Transcribed` : "No Text Transcribed"}
              </span>
            </div>
            <pre style={{
              background: "#0a1320",
              color: "#d0e1f9",
              padding: 10,
              borderRadius: 6,
              fontSize: 12,
              lineHeight: 1.5,
              maxHeight: 180,
              overflowY: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              border: "1px solid #1c2e47"
            }}>
              {ocrDoc.raw_text || "(No transcript text available)"}
            </pre>
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
                    src={toFullUrl(ocrDoc.overlay_urls[selectedPageIdx])}
                    alt="Document page with line segmentation bounding boxes"
                    style={{ maxWidth: "100%", height: "auto", objectFit: "contain", borderRadius: 4 }}
                  />
                ) : ocrDoc.page_urls?.[selectedPageIdx] ? (
                  <img
                    src={toFullUrl(ocrDoc.page_urls[selectedPageIdx])}
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
