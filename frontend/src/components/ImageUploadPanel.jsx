import { useEffect, useMemo, useState } from "react";
import { BASE, apiError, confirmImageExtraction, getCase, uploadImage } from "../api";

function resolveUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:")) {
    return url;
  }
  return `${BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

export default function ImageUploadPanel({ caseId, onConfirmed }) {
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [crops, setCrops] = useState([]);
  const [location, setLocation] = useState({ exif_present: false, included: false });
  const [casePersons, setCasePersons] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);
  const [originalSrc, setOriginalSrc] = useState(null);
  const [showOriginal, setShowOriginal] = useState(true);

  // Fetch case persons so investigator can link crops to existing suspects/persons
  useEffect(() => {
    if (caseId != null) {
      getCase(caseId)
        .then((c) => setCasePersons(c.persons || []))
        .catch(() => {});
    }
  }, [caseId]);

  const includedCropsCount = useMemo(
    () => crops.filter((c) => c.included).length,
    [crops]
  );

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

      const rawDets = data.detections || [];
      setCrops(
        rawDets.map((d, i) => {
          const isPerson = d.entity_type === "PERSON";
          return {
            ...d,
            _id: d.crop_id || `crop_${i}`,
            included: true,
            linked_person_id: d.matched_person_id || null,
            force_create_new: false,
            provisional_name: isPerson && !d.matched_person_id ? `Unresolved Person ${i + 1}` : "",
          };
        })
      );

      setLocation({
        ...(data.location || {}),
        included: !!(data.location && data.location.exif_present),
      });

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

  // Pre-confirmation visual relationship mapping
  const previewEdges = useMemo(() => {
    const included = crops.filter((c) => c.included);
    const persons = included.filter((c) => c.entity_type === "PERSON");
    const weapons = included.filter((c) => c.entity_type === "WEAPON");
    const objects = included.filter((c) => c.entity_type === "OBJECT");
    const edges = [];

    const getPersonDisplayName = (p, idx) => {
      if (p.force_create_new) {
        return p.provisional_name || `New Person #${idx + 1}`;
      }
      if (p.linked_person_id) {
        const found = casePersons.find((cp) => cp.person_id === Number(p.linked_person_id));
        if (found) return `${found.full_name} (#${found.person_id})`;
        if (p.matched_person_name) return `${p.matched_person_name} (#${p.linked_person_id})`;
        return `Person #${p.linked_person_id}`;
      }
      return p.provisional_name || `New Person #${idx + 1}`;
    };

    // 1. PERSON <-> PERSON (CO_APPEARS_IN_PHOTO)
    for (let i = 0; i < persons.length; i++) {
      for (let j = i + 1; j < persons.length; j++) {
        edges.push({
          id: `pp_${i}_${j}`,
          source: getPersonDisplayName(persons[i], i),
          sourceType: "PERSON",
          target: getPersonDisplayName(persons[j], j),
          targetType: "PERSON",
          relation: "CO_APPEARS_IN_PHOTO",
          badgeColor: "#ff6b00",
          desc: "Co-appears in same photo",
        });
      }
    }

    // 2. PERSON <-> WEAPON (NEAR_WEAPON_IN_PHOTO)
    for (let i = 0; i < persons.length; i++) {
      for (let w of weapons) {
        const confPct = Math.round((w.confidence || 0) * 100);
        const wName = `${w.label} (${confPct}%${w.is_low_confidence ? ", low conf" : ""})`;
        edges.push({
          id: `pw_${i}_${w.crop_id}`,
          source: getPersonDisplayName(persons[i], i),
          sourceType: "PERSON",
          target: wName,
          targetType: "WEAPON",
          relation: "NEAR_WEAPON_IN_PHOTO",
          badgeColor: "#ff5050",
          desc: `Near ${w.label} in photo`,
        });
      }
    }

    // 3. WEAPON <-> PHOTO (DEPICTS_OBJECT)
    for (let w of weapons) {
      const confPct = Math.round((w.confidence || 0) * 100);
      const wName = `${w.label} (${confPct}%)`;
      edges.push({
        id: `wp_${w.crop_id}`,
        source: wName,
        sourceType: "WEAPON",
        target: `Photo (${draft?.filename || file?.name || "image"})`,
        targetType: "PHOTO",
        relation: "DEPICTS_OBJECT",
        badgeColor: "#ffa3e6",
        desc: "Weapon depicted in image",
      });
    }

    // 4. PERSON <-> PHOTO (DEPICTED_IN_PHOTO)
    for (let i = 0; i < persons.length; i++) {
      edges.push({
        id: `ph_${i}`,
        source: getPersonDisplayName(persons[i], i),
        sourceType: "PERSON",
        target: `Photo (${draft?.filename || file?.name || "image"})`,
        targetType: "PHOTO",
        relation: "DEPICTED_IN_PHOTO",
        badgeColor: "#ffa3e6",
        desc: "Person depicted in image",
      });
    }

    // 5. OBJECT <-> PHOTO & PERSON <-> OBJECT
    for (let o of objects) {
      const confPct = Math.round((o.confidence || 0) * 100);
      const oName = `${o.label} (${confPct}%)`;
      edges.push({
        id: `op_${o.crop_id}`,
        source: oName,
        sourceType: "OBJECT",
        target: `Photo (${draft?.filename || file?.name || "image"})`,
        targetType: "PHOTO",
        relation: "DEPICTS_OBJECT",
        badgeColor: "#5b8def",
        desc: "Object depicted in image",
      });
      for (let i = 0; i < persons.length; i++) {
        edges.push({
          id: `po_${i}_${o.crop_id}`,
          source: getPersonDisplayName(persons[i], i),
          sourceType: "PERSON",
          target: oName,
          targetType: "OBJECT",
          relation: "NEAR_OBJECT_IN_PHOTO",
          badgeColor: "#5b8def",
          desc: `Near ${o.label} in photo`,
        });
      }
    }

    // 6. PHOTO <-> LOCATION (PHOTOGRAPHED_AT)
    if (location?.included && location?.latitude != null) {
      edges.push({
        id: "ploc",
        source: `Photo (${draft?.filename || file?.name || "image"})`,
        sourceType: "PHOTO",
        target: `Location (${location.latitude}, ${location.longitude})`,
        targetType: "LOCATION",
        relation: "PHOTOGRAPHED_AT",
        badgeColor: "#f2f2f2",
        desc: "From image EXIF GPS",
      });
    }

    return edges;
  }, [crops, draft, file, location, casePersons]);

  async function confirm() {
    if (caseId == null) return;
    setBusy(true);
    setErr(null);
    try {
      const payload = {
        photo_id: draft?.photo_id,
        filename: draft?.filename || file?.name || "image",
        confirmed_crops: crops.filter((c) => c.included),
        location: location,
      };
      const data = await confirmImageExtraction(caseId, payload);
      setInfo(
        `✓ Mapped ${data.edges_added || 0} edges under Independence Group #${data.independence_group_id || ""}. Graph updated.`
      );
      if (onConfirmed) {
        await onConfirmed(data.graph, { edgesAdded: data.edges_added || 0 });
      }
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  const previewUrl = draft?.annotated_preview_url ? draft.annotated_preview_url : originalSrc;

  return (
    <article className="panel-card upload" id="uploadCard" style={{ maxWidth: 1040, margin: "0 auto" }}>
      <h2>
        Upload Photo / Visual Evidence <span className="badge-new">IMAGE EXTRACTION</span>
      </h2>
      <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
        Each detected person, weapon, and object is cropped out into an individual reviewable sub-image.
        Confirming maps co-occurring entities under a <strong>single Evidence Independence Group</strong> so photo co-occurrences never falsely multiply hypothesis weights.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            if (originalSrc) URL.revokeObjectURL(originalSrc);
            setOriginalSrc(null);
            setDraft(null);
            setCrops([]);
          }}
          style={{ flex: 1, minWidth: 260 }}
        />
        <button
          className="btn amber"
          type="button"
          disabled={!file || busy}
          onClick={extract}
          style={{ minWidth: 140 }}
        >
          {busy && !draft ? "Analyzing & Cropping…" : "Extract & Crop"}
        </button>
      </div>

      {err && <div className="error-inline">{err}</div>}
      {info && (
        <div style={{ padding: "8px 12px", background: "rgba(74,210,158,0.12)", border: "1px solid #4ad29e40", borderRadius: 6, color: "#4ad29e", fontSize: 13, marginBottom: 12 }}>
          {info}
        </div>
      )}

      {draft && (
        <>
          {/* 1. TOP: Context Annotated Image */}
          <div style={{ marginTop: 14, border: "1px solid #282828", borderRadius: 8, background: "#111", overflow: "hidden" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "10px 14px",
                background: "#181818",
                borderBottom: showOriginal ? "1px solid #262626" : "none",
                cursor: "pointer",
              }}
              onClick={() => setShowOriginal((v) => !v)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 700, color: "#ffb77a", fontSize: 13 }}>
                  📷 Source Photo & Detection Context
                </span>
                <span className="badge" style={{ background: "#222", color: "#bbb" }}>
                  {draft.filename}
                </span>
                {draft.weapon_model && (
                  <span className="muted" style={{ fontSize: 11 }}>
                    model: {draft.weapon_model}
                  </span>
                )}
              </div>
              <button
                type="button"
                style={{ background: "transparent", border: "none", color: "#888", fontSize: 12, cursor: "pointer" }}
              >
                {showOriginal ? "▾ hide context" : "▸ view original"}
              </button>
            </div>

            {showOriginal && (
              <div style={{ padding: 12, textAlign: "center", background: "#0b0b0b" }}>
                {previewUrl ? (
                  <img
                    src={resolveUrl(previewUrl)}
                    alt="Original annotated context"
                    style={{ maxWidth: "100%", maxHeight: 220, borderRadius: 6, objectFit: "contain", border: "1px solid #333" }}
                  />
                ) : (
                  <div className="muted" style={{ padding: 20 }}>No preview available</div>
                )}
                <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                  Original photo with bounding boxes. Individual detections are cropped below for independent review.
                </div>
              </div>
            )}
          </div>

          {/* 2. CROP GALLERY */}
          <div style={{ marginTop: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <h3 className="subhead" style={{ margin: 0, fontSize: 15, color: "#fafafa" }}>
                ✂️ Cropped Entity Gallery ({includedCropsCount} / {crops.length} selected)
              </h3>
              <span className="muted" style={{ fontSize: 12 }}>
                Review, correct matches, and select entities to map into the case graph
              </span>
            </div>

            {crops.length === 0 ? (
              <div style={{ padding: 24, background: "#141414", borderRadius: 8, textAlign: "center", color: "#888" }}>
                No entities detected in this image.
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                  gap: 14,
                }}
              >
                {crops.map((c, idx) => {
                  const isPerson = c.entity_type === "PERSON";
                  const isWeapon = c.entity_type === "WEAPON";
                  const isLowConf = !!c.is_low_confidence;

                  const badgeBg = isPerson
                    ? "rgba(255, 107, 0, 0.2)"
                    : isWeapon
                    ? "rgba(255, 80, 80, 0.2)"
                    : "rgba(91, 141, 239, 0.2)";
                  const badgeColor = isPerson ? "#ff8c3a" : isWeapon ? "#ff6b6b" : "#8db3ff";

                  return (
                    <div
                      key={c._id}
                      style={{
                        background: isLowConf ? "#1a160d" : c.included ? "#161616" : "#0f0f0f",
                        border: isLowConf
                          ? "2px dashed #f5a623"
                          : c.included
                          ? "1px solid #3d3d3d"
                          : "1px solid #222",
                        borderRadius: 10,
                        padding: 12,
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                        opacity: c.included ? 1 : 0.65,
                        transition: "all 0.15s ease",
                        boxShadow: c.included ? "0 4px 12px rgba(0,0,0,0.4)" : "none",
                      }}
                    >
                      {/* Card Header */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={c.included}
                            onChange={() =>
                              setCrops((list) =>
                                list.map((x) =>
                                  x._id === c._id ? { ...x, included: !x.included } : x
                                )
                              )
                            }
                          />
                          <span
                            className="badge"
                            style={{ background: badgeBg, color: badgeColor, fontWeight: 700, textTransform: "uppercase", fontSize: 11 }}
                          >
                            {c.entity_type}
                          </span>
                        </label>
                        <span
                          className="badge"
                          style={{
                            background: isLowConf ? "rgba(245, 166, 35, 0.2)" : "#262626",
                            color: isLowConf ? "#ffc86b" : "#ccc",
                            border: isLowConf ? "1px solid rgba(245, 166, 35, 0.4)" : "none",
                            fontSize: 11,
                          }}
                        >
                          {Math.round((c.confidence || 0) * 100)}% conf
                        </span>
                      </div>

                      {/* Cropped Image Thumbnail */}
                      <div
                        style={{
                          width: "100%",
                          height: 140,
                          borderRadius: 6,
                          overflow: "hidden",
                          background: "#080808",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          border: "1px solid #262626",
                        }}
                      >
                        {c.crop_image_url ? (
                          <img
                            src={resolveUrl(c.crop_image_url)}
                            alt={c.label}
                            style={{
                              width: "100%",
                              height: "100%",
                              objectFit: "contain",
                              imageRendering: "auto",
                            }}
                          />
                        ) : (
                          <span className="muted" style={{ fontSize: 11 }}>No crop image</span>
                        )}
                      </div>

                      {/* Label & Low-Confidence Warning */}
                      <div>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <span style={{ fontWeight: 700, textTransform: "capitalize", fontSize: 13.5, color: "#eee" }}>
                            {c.label}
                          </span>
                          <span className="muted" style={{ fontSize: 11 }}>
                            ID: {c.crop_id}
                          </span>
                        </div>
                        {isLowConf && (
                          <div
                            style={{
                              marginTop: 4,
                              fontSize: 11,
                              color: "#f5a623",
                              fontWeight: 600,
                              background: "rgba(245,166,35,0.12)",
                              padding: "2px 6px",
                              borderRadius: 4,
                            }}
                          >
                            ⚠️ Low confidence detection — please review
                          </div>
                        )}
                      </div>

                      {/* Person Identification Dropdown & Options */}
                      {isPerson && (
                        <div style={{ marginTop: "auto", borderTop: "1px solid #262626", paddingTop: 8 }}>
                          {c.matched_person_id && !c.force_create_new ? (
                            <div
                              style={{
                                fontSize: 11,
                                color: "#4ad29e",
                                background: "rgba(74,210,158,0.12)",
                                padding: "4px 8px",
                                borderRadius: 4,
                                marginBottom: 6,
                                display: "flex",
                                justifyContent: "space-between",
                              }}
                            >
                              <span>Candidate match: #{c.matched_person_id} {c.matched_person_name}</span>
                              <span>{Math.round((c.match_confidence || 0) * 100)}%</span>
                            </div>
                          ) : (
                            <div
                              style={{
                                fontSize: 11,
                                color: "#8db3ff",
                                background: "rgba(91,141,239,0.12)",
                                padding: "4px 8px",
                                borderRadius: 4,
                                marginBottom: 6,
                              }}
                            >
                              🆕 Unresolved Face / Person
                            </div>
                          )}

                          <label style={{ fontSize: 11, color: "#999", display: "block", marginBottom: 3 }}>
                            Assign Person Identity:
                          </label>
                          <select
                            value={c.force_create_new ? "" : c.linked_person_id ?? ""}
                            onChange={(e) => {
                              const val = e.target.value ? Number(e.target.value) : null;
                              setCrops((list) =>
                                list.map((x) =>
                                  x._id === c._id
                                    ? {
                                        ...x,
                                        linked_person_id: val,
                                        force_create_new: !val,
                                      }
                                    : x
                                )
                              );
                            }}
                            style={{
                              width: "100%",
                              padding: "5px 6px",
                              borderRadius: 4,
                              background: "#222",
                              color: "#eee",
                              border: "1px solid #3a3a3a",
                              fontSize: 12,
                              marginBottom: 6,
                            }}
                          >
                            <option value="">— Mark as NEW Person —</option>
                            {c.matched_person_id && (
                              <option value={c.matched_person_id}>
                                ★ Suggested: #{c.matched_person_id} {c.matched_person_name || "Match"}
                              </option>
                            )}
                            {casePersons
                              .filter((cp) => cp.person_id !== c.matched_person_id)
                              .map((cp) => (
                                <option key={cp.person_id} value={cp.person_id}>
                                  #{cp.person_id} · {cp.full_name} ({cp.source_role || "Person"})
                                </option>
                              ))}
                          </select>

                          {(!c.linked_person_id || c.force_create_new) && (
                            <input
                              type="text"
                              placeholder="Provisional name (e.g. Suspect 1)"
                              value={c.provisional_name || ""}
                              onChange={(e) =>
                                setCrops((list) =>
                                  list.map((x) =>
                                    x._id === c._id ? { ...x, provisional_name: e.target.value } : x
                                  )
                                )
                              }
                              style={{
                                width: "100%",
                                padding: "4px 6px",
                                borderRadius: 4,
                                background: "#1d1d1d",
                                color: "#eee",
                                border: "1px solid #333",
                                fontSize: 12,
                              }}
                            />
                          )}

                          {c.matched_person_id && (
                            <label
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 4,
                                fontSize: 11,
                                color: "#aaa",
                                marginTop: 6,
                                cursor: "pointer",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={!!c.force_create_new}
                                onChange={(e) =>
                                  setCrops((list) =>
                                    list.map((x) =>
                                      x._id === c._id
                                        ? {
                                            ...x,
                                            force_create_new: e.target.checked,
                                            linked_person_id: e.target.checked ? null : x.matched_person_id,
                                          }
                                        : x
                                    )
                                  )
                                }
                              />
                              Force create new (ignore suggested match)
                            </label>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 3. VISUAL MAPPING PREVIEW (BEFORE CONFIRMING) */}
          <div
            style={{
              marginTop: 24,
              padding: 16,
              background: "#111418",
              border: "1px solid #23344d",
              borderRadius: 8,
              boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 16 }}>🕸️</span>
                <h4 style={{ margin: 0, color: "#8db3ff", fontSize: 14.5, fontWeight: 700 }}>
                  Visual Relationship Mapping Preview (Pre-Confirmation)
                </h4>
              </div>
              <span className="badge" style={{ background: "rgba(91,141,239,0.2)", color: "#8db3ff" }}>
                {previewEdges.length} graph edge{previewEdges.length === 1 ? "" : "s"} ready to map
              </span>
            </div>

            <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
              The following graph relationships will be created between confirmed entities in this photo.
              Notice that all of them share <strong>ONE Evidence Independence Group</strong> (one observation event), preventing artificial inflation of hypothesis scores.
            </p>

            {previewEdges.length === 0 ? (
              <div className="muted" style={{ padding: 12, textAlign: "center", background: "#0b0d10", borderRadius: 6 }}>
                Select at least one entity card above to see proposed graph edges.
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  maxHeight: 280,
                  overflowY: "auto",
                  paddingRight: 4,
                }}
              >
                {previewEdges.map((e) => (
                  <div
                    key={e.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 12px",
                      background: "#0c0e12",
                      border: "1px solid #1c2330",
                      borderRadius: 6,
                      fontSize: 12.5,
                      gap: 10,
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 280 }}>
                      <span style={{ fontWeight: 600, color: "#eee" }}>{e.source}</span>
                      <span style={{ color: "#666" }}>──────</span>
                      <span
                        className="badge"
                        style={{
                          background: `${e.badgeColor}22`,
                          color: e.badgeColor,
                          border: `1px solid ${e.badgeColor}55`,
                          fontWeight: 700,
                          fontSize: 11,
                        }}
                      >
                        {e.relation}
                      </span>
                      <span style={{ color: "#666" }}>──────</span>
                      <span style={{ fontWeight: 600, color: "#eee" }}>{e.target}</span>
                    </div>
                    <span className="muted" style={{ fontSize: 11 }}>
                      {e.desc}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 4. EXIF LOCATION METADATA */}
          <div style={{ marginTop: 16, border: "1px solid #262626", borderRadius: 8, padding: 12, background: "#111" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 600, fontSize: 13, color: "#eee" }}>
                <input
                  type="checkbox"
                  checked={!!location.included}
                  disabled={!location.exif_present}
                  onChange={(e) => setLocation({ ...location, included: e.target.checked })}
                />
                📍 EXIF Metadata & Geolocation
              </label>
              {location.exif_present ? (
                <span className="badge" style={{ background: "rgba(74,210,158,0.15)", color: "#4ad29e" }}>
                  EXIF Found
                </span>
              ) : (
                <span className="badge" style={{ background: "#222", color: "#888" }}>
                  No EXIF in image
                </span>
              )}
            </div>

            {location.exif_present && location.included && (
              <div style={{ marginTop: 8, padding: "8px 12px", background: "#161616", borderRadius: 6, fontSize: 12.5 }}>
                {location.timestamp && (
                  <div>
                    <span style={{ color: "#ffd257" }}>🕒 Taken:</span> {location.timestamp}
                  </div>
                )}
                {location.latitude != null && (
                  <div>
                    <span style={{ color: "#4ad29e" }}>📍 Coordinates:</span> {location.latitude}, {location.longitude}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 5. CONFIRM BUTTON */}
          <div style={{ marginTop: 20, display: "flex", gap: 12, alignItems: "center" }}>
            <button
              className="btn ok"
              type="button"
              disabled={busy || includedCropsCount === 0}
              onClick={confirm}
              style={{ minWidth: 240, padding: "10px 20px", fontSize: 14, fontWeight: 700 }}
            >
              {busy ? "Mapping to Graph…" : `Confirm & Map to Graph (${previewEdges.length} edges)`}
            </button>
            <span className="muted" style={{ fontSize: 12 }}>
              Writes {includedCropsCount} cropped entities and {previewEdges.length} edges into GraphEdge with shared IndependenceGroupID.
            </span>
          </div>
        </>
      )}
    </article>
  );
}
