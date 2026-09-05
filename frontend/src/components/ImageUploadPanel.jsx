import { useMemo, useState } from "react";
import { apiError, confirmImageExtraction, uploadImage } from "../api";

function Section({ title, count, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: 14, border: "1px solid #262626", borderRadius: 8, overflow: "hidden" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 12px",
          background: "#161616",
          border: "none",
          color: "#ffb77a",
          fontWeight: 700,
          fontSize: 13.5,
          letterSpacing: 0.2,
          cursor: "pointer",
        }}
      >
        <span>
          {title}
          {typeof count === "number" && (
            <span className="badge" style={{ marginLeft: 8, background: "#2a2a2a", color: "#ddd" }}>
              {count}
            </span>
          )}
        </span>
        <span style={{ fontSize: 11, color: "#888" }}>{open ? "▾ hide" : "▸ show"}</span>
      </button>
      {open && <div style={{ padding: 12, background: "#101010" }}>{children}</div>}
    </div>
  );
}

function FaceThumb({ bbox, src }) {
  const [x1, y1, x2, y2] = bbox || [0, 0, 0, 0];
  const w = Math.max(1, x2 - x1);
  const h = Math.max(1, y2 - y1);
  return (
    <div
      style={{
        width: 56,
        height: 56,
        flexShrink: 0,
        borderRadius: 6,
        background: "#1a1a1a",
        backgroundImage: `url(${src})`,
        backgroundSize: "cover",
        backgroundPosition: `-${x1}px -${y1}px`,
        backgroundRepeat: "no-repeat",
        border: "1px solid #333",
        imageRendering: "pixelated",
      }}
      title="Face crop (uses annotated preview coordinates)"
    />
  );
}

export default function ImageUploadPanel({ caseId, onConfirmed }) {
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [objects, setObjects] = useState([]);
  const [lowConfObjects, setLowConfObjects] = useState([]);
  const [faces, setFaces] = useState([]);
  const [location, setLocation] = useState({ exif_present: false, included: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);
  const [originalSrc, setOriginalSrc] = useState(null);

  const includedObjs = useMemo(() => objects.filter((o) => o.included).length, [objects]);
  const includedFaces = useMemo(() => faces.filter((f) => f.included).length, [faces]);

  async function extract() {
    if (!file || caseId == null) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const url = URL.createObjectURL(file);
      setOriginalSrc(url);
      const data = await uploadImage(caseId, file);
      setDraft(data);
      setObjects((data.objects || []).map((o, i) => ({ ...o, included: o.label !== "person", _id: i })));
      setLowConfObjects(
        (data.low_confidence_flagged || []).map((o, i) => ({
          ...o,
          included: false,
          _id: `low_${i}`,
        }))
      );
      setFaces(
        (data.faces || []).map((f, i) => ({
          ...f,
          included: true,
          _id: i,
          force_create_new: false,
          provisional_name: "",
        }))
      );
      setLocation({ ...(data.location || {}), included: !!(data.location && data.location.exif_present) });
      if ((data.warnings || []).length) {
        setInfo("ℹ️ " + data.warnings.join("  "));
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
      const selectedLowConf = lowConfObjects
        .filter((o) => o.included)
        .map(({ _id, note, ...o }) => ({ ...o, included: true }));
      const payload = {
        filename: draft?.filename || file?.name || "image",
        objects: [
          ...objects.filter((o) => o.included).map(({ _id, ...o }) => o),
          ...selectedLowConf,
        ],
        faces: faces.map(({ _id, ...f }) => f),
        location: location,
      };
      const data = await confirmImageExtraction(caseId, payload);
      setInfo(`Added ${data.edges_added || 0} IMAGE_UPLOAD edges. Graph refreshed.`);
      if (onConfirmed) await onConfirmed(data.graph, { edgesAdded: data.edges_added || 0 });
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  const previewUrl = draft?.annotated_preview_url ? draft.annotated_preview_url : originalSrc;

  return (
    <article className="panel-card upload" id="uploadCard">
      <h2>
        Upload Photo / Evidence <span className="badge-new">IMAGE</span>
      </h2>
      <p className="muted">
        Visual extraction: YOLOv8 objects, face recognition, and EXIF metadata. Everything is a draft — NOTHING is written to the graph until you confirm.
      </p>
      <input
        type="file"
        accept="image/*"
        onChange={(e) => {
          setFile(e.target.files?.[0] || null);
          if (originalSrc) URL.revokeObjectURL(originalSrc);
          setOriginalSrc(null);
          setDraft(null);
          setLowConfObjects([]);
        }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn amber" type="button" disabled={!file || busy} onClick={extract}>
          {busy && !draft ? "Analyzing image…" : "Extract"}
        </button>
      </div>
      {err && <div className="error-inline">{err}</div>}
      {info && <div className="muted">{info}</div>}

      {draft && (
        <>
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <h3 className="subhead" style={{ margin: 0 }}>
                Annotated Preview — Review before confirming
              </h3>
              {draft.weapon_model && (
                <span className="muted" style={{ fontSize: 12 }} title="Weapon model used for detection">
                  detector: {draft.weapon_model}
                </span>
              )}
            </div>
            <div
              style={{
                border: "1px dashed #3a3a3a",
                borderRadius: 10,
                background: "#0b0b0b",
                padding: 6,
                maxHeight: 520,
                overflow: "auto",
                textAlign: "center",
              }}
            >
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt="Annotated preview"
                  style={{ maxWidth: "100%", maxHeight: 500, borderRadius: 6 }}
                />
              ) : (
                <div className="muted" style={{ padding: 30 }}>
                  (annotated preview not yet rendered — check backend dependencies)
                </div>
              )}
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              {draft.filename} · boxes show detections + confidences · green = face match, blue = new face, orange = weapon/person
            </div>
          </div>

          <Section
            title={`Objects / Weapons Detected`}
            count={includedObjs + " / " + objects.length}
          >
            {objects.length === 0 ? (
              <div className="muted">No weapon/object detections.</div>
            ) : (
              <div className="review-table">
                {objects.map((o) => (
                  <label key={o._id} className="review-row">
                    <input
                      type="checkbox"
                      checked={o.included}
                      onChange={() =>
                        setObjects((list) =>
                          list.map((x) => (x._id === o._id ? { ...x, included: !x.included } : x))
                        )
                      }
                    />
                    <span
                      style={{
                        display: "inline-block",
                        width: 10,
                        height: 10,
                        borderRadius: 3,
                        background:
                          o.label === "person"
                            ? "#ff6b00"
                            : ["knife", "scissors", "gun", "pistol", "rifle", "baseball bat"].includes(o.label)
                            ? "#ff5050"
                            : "#5b8def",
                      }}
                    />
                    <span style={{ textTransform: "capitalize" }}>{o.label}</span>
                    <span className="badge">
                      {typeof o.confidence === "number"
                        ? Math.round(o.confidence * 100) + "%"
                        : "—"}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </Section>

          {lowConfObjects.length > 0 && (
            <Section
              title="Possible additional objects (low confidence, please verify)"
              count={`${lowConfObjects.filter((o) => o.included).length} / ${lowConfObjects.length}`}
              defaultOpen={false}
            >
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                These detections were below the standard display confidence threshold. Review manually and check to include them in the case graph:
              </div>
              <div className="review-table">
                {lowConfObjects.map((o) => (
                  <label
                    key={o._id}
                    className="review-row"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "6px 8px",
                      background: o.included ? "#221c10" : "#141414",
                      border: o.included ? "1px solid rgba(245, 166, 35, 0.4)" : "1px solid #222",
                      borderRadius: 6,
                      marginBottom: 4,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={o.included}
                      onChange={() =>
                        setLowConfObjects((list) =>
                          list.map((x) => (x._id === o._id ? { ...x, included: !x.included } : x))
                        )
                      }
                    />
                    <span
                      style={{
                        display: "inline-block",
                        width: 10,
                        height: 10,
                        borderRadius: 3,
                        background: "#f5a623",
                      }}
                    />
                    <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{o.label}</span>
                    <span
                      className="badge"
                      style={{
                        background: "rgba(245, 166, 35, 0.15)",
                        color: "#ffc86b",
                        border: "1px solid rgba(245, 166, 35, 0.3)",
                      }}
                    >
                      {typeof o.confidence === "number" ? Math.round(o.confidence * 100) + "%" : "—"}
                    </span>
                    <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
                      {o.note || "below display threshold — review manually"}
                    </span>
                  </label>
                ))}
              </div>
            </Section>
          )}

          <Section title={`Faces Detected`} count={includedFaces + " / " + faces.length}>
            {faces.length === 0 ? (
              <div className="muted">
                No faces detected. (Install <code>face_recognition</code> / dlib to enable.)
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {faces.map((f) => (
                  <div
                    key={f._id}
                    className="review-row"
                    style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "flex-start",
                      padding: 10,
                      background: "#161616",
                      borderRadius: 8,
                      border:
                        f.status === "CANDIDATE_MATCH"
                          ? "1px solid rgba(74,210,158,0.4)"
                          : "1px solid rgba(91,141,239,0.3)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={f.included}
                      onChange={() =>
                        setFaces((list) =>
                          list.map((x) => (x._id === f._id ? { ...x, included: !x.included } : x))
                        )
                      }
                      style={{ marginTop: 18 }}
                    />
                    {previewUrl && <FaceThumb bbox={f.bbox} src={previewUrl} />}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span
                          className="badge"
                          style={{
                            background:
                              f.status === "CANDIDATE_MATCH"
                                ? "rgba(74,210,158,0.18)"
                                : "rgba(91,141,239,0.18)",
                            color:
                              f.status === "CANDIDATE_MATCH" ? "#4ad29e" : "#8db3ff",
                            border: "none",
                          }}
                        >
                          {f.status === "CANDIDATE_MATCH" ? "⚠️ CANDIDATE MATCH" : "🆕 NEW FACE — no match"}
                        </span>
                        {typeof f.match_confidence === "number" && (
                          <span className="muted" style={{ fontSize: 12 }}>
                            conf {Math.round(f.match_confidence * 100)}%
                          </span>
                        )}
                      </div>
                      {f.status === "CANDIDATE_MATCH" ? (
                        <div style={{ marginTop: 8 }}>
                          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
                            Suggested person (investigator-reviewed, NOT auto-merged):
                          </div>
                          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                            <select
                              value={f.matched_person_id ?? ""}
                              onChange={(e) => {
                                const pid = e.target.value ? Number(e.target.value) : null;
                                setFaces((list) =>
                                  list.map((x) =>
                                    x._id === f._id
                                      ? {
                                          ...x,
                                          matched_person_id: pid,
                                          status: pid ? "CANDIDATE_MATCH" : "NEW_FACE_NO_MATCH",
                                          force_create_new: false,
                                        }
                                      : x
                                  )
                                );
                              }}
                              style={{ padding: "6px 8px", borderRadius: 6, background: "#1f1f1f", color: "#eee", border: "1px solid #333" }}
                            >
                              <option value="">— Mark as NEW person —</option>
                              <option value={f.matched_person_id ?? ""}>
                                #{f.matched_person_id} · {f.matched_person_name || "Suggested match"}
                              </option>
                            </select>
                            <label style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 12, color: "#bbb" }}>
                              <input
                                type="checkbox"
                                checked={!!f.force_create_new}
                                onChange={(e) =>
                                  setFaces((list) =>
                                    list.map((x) =>
                                      x._id === f._id
                                        ? {
                                            ...x,
                                            force_create_new: e.target.checked,
                                            status: e.target.checked
                                              ? "NEW_FACE_NO_MATCH"
                                              : x.matched_person_id
                                              ? "CANDIDATE_MATCH"
                                              : "NEW_FACE_NO_MATCH",
                                          }
                                        : x
                                    )
                                  )
                                }
                              />
                              Force create new (ignore match)
                            </label>
                          </div>
                        </div>
                      ) : (
                        <div style={{ marginTop: 8 }}>
                          <input
                            type="text"
                            placeholder="Provisional name (optional — e.g. 'Suspect 1')"
                            value={f.provisional_name || ""}
                            onChange={(e) =>
                              setFaces((list) =>
                                list.map((x) =>
                                  x._id === f._id ? { ...x, provisional_name: e.target.value } : x
                                )
                              )
                            }
                            style={{
                              width: "100%",
                              padding: "6px 8px",
                              borderRadius: 6,
                              background: "#1f1f1f",
                              color: "#eee",
                              border: "1px solid #333",
                              fontSize: 13,
                            }}
                          />
                          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                            Creates a new unresolved Person record on confirm (embedding stored for future matches)
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Location & Timestamp (EXIF)">
            {location.exif_present ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label className="review-row" style={{ alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={!!location.included}
                    onChange={(e) => setLocation({ ...location, included: e.target.checked })}
                  />
                  <span className="muted">Include EXIF evidence in graph (high confidence — it's metadata, not inference)</span>
                </label>
                <div
                  style={{
                    marginLeft: 26,
                    padding: "8px 12px",
                    background: "#141414",
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                >
                  {location.timestamp && (
                    <div>
                      <span style={{ color: "#ffd257" }}>🕒 Taken:</span>{" "}
                      <span style={{ color: "#eee" }}>{location.timestamp}</span>
                    </div>
                  )}
                  {location.latitude != null && (
                    <div>
                      <span style={{ color: "#f2f2f2" }}>📍 GPS:</span>{" "}
                      <span style={{ color: "#eee" }}>
                        {location.latitude}, {location.longitude}
                      </span>
                    </div>
                  )}
                  {location.gps_error && (
                    <div className="error-inline">GPS EXIF error: {location.gps_error}</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="muted">
                ⚠️ No EXIF data found in this image (common when photos are shared via messaging apps — they strip metadata). Nothing to confirm here.
              </div>
            )}
          </Section>

          <button className="btn ok" type="button" disabled={busy} onClick={confirm} style={{ marginTop: 16 }}>
            {busy ? "Writing…" : "Confirm & Add to Graph"}
          </button>
        </>
      )}
    </article>
  );
}
