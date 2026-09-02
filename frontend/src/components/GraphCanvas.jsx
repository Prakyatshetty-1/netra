import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

function collapseEdges(edges) {
  const map = new Map();
  for (const e of edges || []) {
    const a = String(e.source);
    const b = String(e.target);
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    const conf = e.confidence ?? e.ConfidenceScore ?? 0.5;
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
          });
        } else {
          prev.burst = prev.burst || !!e.burst;
          prev.highlighted = prev.highlighted || !!e.highlighted;
          prev.confidence = Math.max(prev.confidence, conf);
          if ((e.source_type || "") === "PDF_UPLOAD") prev.source_type = "PDF_UPLOAD";
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

    const searchActive = (graphData.nodes || []).some((n) => n.highlighted);
    const collapsed = collapseEdges(graphData.edges);

    const elements = [];
    for (const n of graphData.nodes || []) {
      const label = n.label || n.id;
      elements.push({
        data: {
          id: n.id,
          label,
          type: n.type,
          centrality: n.centrality || 0,
          cardWidth: Math.min(220, Math.max(96, 18 + label.length * 7.2)),
          cardHeight: 28 + Math.round(22 * (n.centrality || 0)),
        },
        classes: n.highlighted ? "hl" : "",
      });
    }
    for (const e of collapsed) {
      const srcType = e.source_type || "";
      const dashed = srcType === "PDF_UPLOAD" || srcType === "TOWER_LOG";
      const classes = [
        e.burst ? "burst" : "",
        e.highlighted ? "hl" : "",
        dashed ? "pdf" : "",
      ]
        .filter(Boolean)
        .join(" ");
      elements.push({ data: e, classes });
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
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#4a4a4a",
            "curve-style": "haystack",
            "haystack-radius": 0,
            opacity: 0.9,
          },
        },
        {
          selector: "edge.burst, edge.hl",
          style: {
            width: 3.5,
            "line-color": "#ff6b00",
            "curve-style": "straight",
            opacity: 1,
            "line-cap": "round",
          },
        },
        {
          selector: "edge.pdf",
          style: {
            "line-style": "dashed",
            width: 2,
            "line-color": "#5b8def",
            "curve-style": "straight",
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
      cy.edges().not(".hl").style({ opacity: 0.12, width: 1, "line-color": "#444444" });
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

  return <div className="graph-canvas" ref={containerRef} />;
}
