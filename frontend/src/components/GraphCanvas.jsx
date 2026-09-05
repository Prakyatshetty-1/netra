import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { BASE } from "../api";

function resolveUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:")) {
    return url;
  }
  return `${BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}


export const EDGE_KIND_META = {
  pp:    { color: "#ff6b00", label: "Person ↔ Person (NAMED_TOGETHER, CO_ACCUSED, CO_APPEARS_IN_PHOTO)" },
  phone: { color: "#5b8def", label: "Phone / Mobile / OTP / Call (HAS_PHONE, CALLED)" },
  loc:   { color: "#f2f2f2", label: "Location / Place (MENTIONED_AT_LOCATION, CO_LOCATED, PHOTOGRAPHED_AT)" },
  veh:   { color: "#4ad29e", label: "Vehicle / Registration (ASSOCIATED_WITH_VEHICLE)" },
  org:   { color: "#c27bff", label: "Organisation / Company" },
  date:  { color: "#ffd257", label: "Date / Time (MENTIONED_ON_DATE)" },
  photo: { color: "#ffa3e6", label: "Photo evidence (DEPICTED_IN_PHOTO, DEPICTS_OBJECT)" },
  other: { color: "#6a6a6a", label: "Other / Uncategorised" },
};

function classifyEdge(edge, nodeTypeOf) {
  const rel = (edge.relation || "").toUpperCase();
  const src = edge.source_type || "";
  const st = nodeTypeOf(edge.source);
  const tt = nodeTypeOf(edge.target);
  const types = new Set([st, tt]);

  if (
    types.has("PHOTO") ||
    types.has("WEAPON") ||
    types.has("OBJECT") ||
    types.has("EVIDENCE_GROUP") ||
    src === "IMAGE_UPLOAD" ||
    src === "EXIF" ||
    rel === "DEPICTED_IN_PHOTO" ||
    rel === "DEPICTS_OBJECT" ||
    rel === "CO_APPEARS_IN_PHOTO" ||
    rel === "NEAR_WEAPON_IN_PHOTO" ||
    rel === "NEAR_OBJECT_IN_PHOTO" ||
    rel === "PHOTOGRAPHED_AT"
  ) {
    return "photo";
  }

  if (types.has("PHONE") || rel === "HAS_PHONE" || rel === "CALLED" || rel === "SMS" || rel === "OTP" || rel === "TOWER_LOG") {
    return "phone";
  }
  if (types.has("LOC") || types.has("LOCATION") || rel === "MENTIONED_AT_LOCATION" || rel === "CO_LOCATED" || rel === "AT_LOCATION") {
    return "loc";
  }
  if (types.has("VEHICLE") || rel === "ASSOCIATED_WITH_VEHICLE" || rel === "OWNED_VEHICLE" || rel === "ANPR_SEEN") {
    return "veh";
  }
  if (types.has("ORG") || rel === "WORKS_AT" || rel === "MEMBER_OF") {
    return "org";
  }
  if (types.has("DATE") || rel === "MENTIONED_ON_DATE" || rel === "ON_DATE" || rel === "OCCURRED_ON") {
    return "date";
  }
  if (st === "PERSON" && tt === "PERSON") {
    return "pp";
  }
  return "other";
}

function collapseEdges(edges, nodeTypeOf) {
  const map = new Map();
  for (const e of edges || []) {
    const a = String(e.source);
    const b = String(e.target);
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    const conf = e.confidence ?? e.ConfidenceScore ?? 0.5;
    const kind = classifyEdge(e, nodeTypeOf);
    const prev = map.get(key);
    if (!prev) {
      map.set(key, {
        id: "e" + e.id,
        source: e.source,
        target: e.target,
        relation: e.relation,
        burst: !!e.burst,
        highlighted: !!e.highlighted,
        confidence: conf,
        source_type: e.source_type || "",
        kind,
      });
    } else {
      prev.burst = prev.burst || !!e.burst;
      prev.highlighted = prev.highlighted || !!e.highlighted;
      prev.confidence = Math.max(prev.confidence, conf);
      if ((e.source_type || "") === "PDF_UPLOAD") prev.source_type = "PDF_UPLOAD";
      if (prev.kind === "other" && kind !== "other") prev.kind = kind;
      if (prev.kind === "pp" && (kind === "phone" || kind === "loc")) prev.kind = kind;
    }
  }
  return [...map.values()];
}

export default function GraphCanvas({ graphData, onNodeClick, selectedPersonId }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const clickRef = useRef(onNodeClick);
  clickRef.current = onNodeClick;

  useEffect(() => {
    if (!containerRef.current || !graphData) return undefined;

    const nodes = graphData.nodes || [];
    const typeById = new Map(nodes.map(n => [n.id, (n.type || "").toUpperCase()]));
    // Draft node IDs look like DRAFT-PERSON:1  or  DRAFT-LOC:1 — also handle Person:123 format
    const nodeTypeOf = (id) => {
      const s = String(id);
      if (typeById.has(s)) return typeById.get(s);
      const stripped = s.startsWith("DRAFT-") ? s.slice(6) : s;
      const head = stripped.split(":")[0] || "";
      const up = head.toUpperCase();
      if (up === "LOCATION") return "LOC";
      return up || "OTHER";
    };

    const searchActive = nodes.some((n) => n.highlighted);
    const collapsed = collapseEdges(graphData.edges, nodeTypeOf);

    const elements = [];
    for (const n of nodes) {
      const label = n.label || n.id;
      const imageUrl = n.image ? resolveUrl(n.image) : "";
      const hasImage = Boolean(imageUrl);

      const width = hasImage ? 84 : Math.min(220, Math.max(96, 18 + label.length * 7.2));
      const height = hasImage ? 84 : 28 + Math.round(22 * (n.centrality || 0));

      elements.push({
        data: {
          id: n.id,
          label,
          type: n.type,
          centrality: n.centrality || 0,
          cardWidth: width,
          cardHeight: height,
          nodeImage: imageUrl,
        },
        classes: [n.highlighted ? "hl" : "", hasImage ? "has-img" : ""].filter(Boolean).join(" "),
      });
    }

    for (const e of collapsed) {
      const srcType = e.source_type || "";
      const dashed =
        srcType === "PDF_UPLOAD" || srcType === "TOWER_LOG" || srcType === "IMAGE_UPLOAD" || srcType === "EXIF";
      const classes = [
        e.highlighted ? "hl" : "",
        dashed ? "pdf" : "",
        `kind-${e.kind}`,
      ]
        .filter(Boolean)
        .join(" ");
      elements.push({ data: { ...e, dashed: dashed ? 1 : 0 }, classes });
    }

    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      pixelRatio: "auto",
      minZoom: 0.25,
      maxZoom: 2.5,
      layout: {
        name: "cose",
        animate: false,
        randomize: false,
        nodeRepulsion: 14000,
        idealEdgeLength: 90,
        nodeOverlap: 48,
        gravity: 0.2,
        numIter: 1200,
        padding: 36,
      },
      style: [
        {
          selector: "node",
          style: {
            shape: "round-rectangle",
            label: "data(label)",
            "font-family": "Segoe UI, system-ui, sans-serif",
            "font-size": 10,
            "font-weight": 600,
            color: "#fafafa",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "ellipsis",
            "text-max-width": 200,
            padding: "8px",
            width: "data(cardWidth)",
            height: "data(cardHeight)",
            "background-color": "#1f1f1f",
            "border-width": 1.5,
            "border-color": "#3a3a3a",
            "text-outline-color": "#0a0a0a",
            "text-outline-width": 2,
            "text-outline-opacity": 1,
          },
        },
        {
          selector: "node.hl",
          style: {
            "border-width": 2.5,
            "border-color": "#ff3d3d",
            "background-color": "#2a1414",
            "border-opacity": 1,
          },
        },
        {
          selector: "node[type = 'WEAPON']",
          style: {
            "border-color": "#ff5050",
            "background-color": "#281212",
          },
        },
        {
          selector: "node[type = 'PHOTO']",
          style: {
            "border-color": "#ffa3e6",
            "background-color": "#281224",
          },
        },
        {
          selector: "node[type = 'OBJECT']",
          style: {
            "border-color": "#5b8def",
            "background-color": "#121b28",
          },
        },
        {
          selector: "node.has-img",
          style: {
            "background-image": "data(nodeImage)",
            "background-fit": "cover",
            "background-clip": "node",
            "background-color": "#141414",
            "border-width": 2.5,
            "border-color": "#ffb77a",
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 8,
            "font-size": 11,
            "font-weight": 700,
            "text-outline-color": "#0a0a0a",
            "text-outline-width": 2.5,
            "text-outline-opacity": 0.95,
            "text-max-width": 140,
            "width": "data(cardWidth)",
            "height": "data(cardHeight)",
          },
        },
        {
          selector: "node[type = 'WEAPON'].has-img",
          style: {
            "border-color": "#ff5050",
            "border-width": 3,
          },
        },
        {
          selector: "node[type = 'PHOTO'].has-img",
          style: {
            "border-color": "#ffa3e6",
            "border-width": 3,
          },
        },
        {
          selector: "node[type = 'PERSON'].has-img",
          style: {
            "border-color": "#ff6b00",
            "border-width": 3,
          },
        },
        {
          selector: "node[type = 'OBJECT'].has-img",
          style: {
            "border-color": "#5b8def",
            "border-width": 3,
          },
        },
        {
          selector: "node.hl.has-img",
          style: {
            "border-width": 4.5,
            "border-color": "#ff3d3d",
          },
        },

        {
          selector: "edge",

          style: {
            width: 1.8,
            "line-color": EDGE_KIND_META.other.color,
            "curve-style": "bezier",
            "bezier-curve-style": "unbundled-bezier",
            "control-point-distances": "0 -10 10",
            "control-point-weights": "0.25 0.5 0.75",
            opacity: 0.92,
            "line-cap": "round",
          },
        },
        {
          selector: "edge.kind-pp",
          style: { "line-color": EDGE_KIND_META.pp.color, width: 2.2 },
        },
        {
          selector: "edge.kind-phone",
          style: { "line-color": EDGE_KIND_META.phone.color, width: 2 },
        },
        {
          selector: "edge.kind-loc",
          style: { "line-color": EDGE_KIND_META.loc.color, width: 1.8 },
        },
        {
          selector: "edge.kind-veh",
          style: { "line-color": EDGE_KIND_META.veh.color, width: 1.8 },
        },
        {
          selector: "edge.kind-org",
          style: { "line-color": EDGE_KIND_META.org.color, width: 1.8 },
        },
        {
          selector: "edge.kind-date",
          style: { "line-color": EDGE_KIND_META.date.color, width: 1.8 },
        },
        {
          selector: "edge.kind-photo",
          style: { "line-color": EDGE_KIND_META.photo.color, width: 2 },
        },
        {
          selector: "edge.hl",
          style: {
            width: 4,
            opacity: 1,
            "z-index": 999,
          },
        },
        {
          selector: "edge.pdf",
          style: {
            "line-style": "dashed",
            width: 2,
          },
        },
        {
          selector: "node.picked",
          style: {
            "border-width": 3,
            "border-color": "#ff6b00",
            "background-color": "#261810",
            "shadow-color": "#ff6b00",
            "shadow-blur": 12,
            "shadow-opacity": 0.35,
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          },
        },
      ],
    });

    if (searchActive) {
      cy.nodes().not(".hl").style({ opacity: 0.22, "border-color": "#555555" });
      cy.edges().not(".hl").style({ opacity: 0.15, width: 1 });
    }

    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      cy.nodes().removeClass("picked");
      evt.target.addClass("picked");
      if (clickRef.current) clickRef.current(d.id);
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [graphData]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("picked");
    if (selectedPersonId != null) {
      const n = cy.getElementById(`PERSON:${selectedPersonId}`);
      if (n && n.length) n.addClass("picked");
    }
  }, [selectedPersonId]);

  const kindsPresent = new Set();
  if (graphData && graphData.nodes && graphData.nodes.length) {
    const nodes = graphData.nodes || [];
    const typeById = new Map(nodes.map(n => [n.id, (n.type || "").toUpperCase()]));
    const nodeTypeOf = (id) => {
      const s = String(id);
      if (typeById.has(s)) return typeById.get(s);
      const stripped = s.startsWith("DRAFT-") ? s.slice(6) : s;
      const head = stripped.split(":")[0] || "";
      const up = head.toUpperCase();
      return up === "LOCATION" ? "LOC" : (up || "OTHER");
    };
    for (const e of graphData.edges || []) {
      kindsPresent.add(classifyEdge(e, nodeTypeOf));
    }
  }

  const legendEntries = Object.entries(EDGE_KIND_META).filter(
    ([k]) => kindsPresent.size === 0 || kindsPresent.has(k) || k === "pp" || k === "phone" || k === "loc"
  );

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div className="graph-canvas" ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <div
        className="graph-legend"
        style={{
          position: "absolute",
          top: 12,
          right: 12,
          zIndex: 10,
          background: "rgba(17,17,17,0.92)",
          border: "1px solid #2a2a2a",
          borderRadius: 8,
          padding: "10px 12px",
          minWidth: 230,
          backdropFilter: "blur(4px)",
          fontFamily: "Segoe UI, system-ui, sans-serif",
          fontSize: 12,
          color: "#e0e0e0",
          boxShadow: "0 4px 14px rgba(0,0,0,0.45)",
          pointerEvents: "none",
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 12.5, letterSpacing: 0.2, color: "#ffb77a" }}>
          ⟡ EDGE LEGEND
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {legendEntries.map(([key, meta]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  width: 26,
                  height: 0,
                  borderTop: `${key === "pdf" ? "2px dashed" : "3px solid"} ${meta.color}`,
                  flexShrink: 0,
                  display: "inline-block",
                  borderRadius: 2,
                }}
              />
              <span style={{ lineHeight: "18px", color: "#c9c9c9" }}>{meta.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
