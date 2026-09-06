import { useEffect, useState } from "react";
import { apiError, getCases, searchGraph } from "./api";

import { useCaseData } from "./useCaseData";

import Sidebar from "./components/Sidebar";
import SearchBar from "./components/SearchBar";
import GraphCanvas from "./components/GraphCanvas";
import IdentityPanel from "./components/IdentityPanel";
import RelatedCasesPanel from "./components/RelatedCasesPanel";
import HypothesisPanel from "./components/HypothesisPanel";
import ContradictionPanel from "./components/ContradictionPanel";
import CounterfactualPanel from "./components/CounterfactualPanel";
import UploadPanel from "./components/UploadPanel";
import CopilotPanel from "./components/CopilotPanel";
import DecisionBar from "./components/DecisionBar";
import EntityIntelligencePanel from "./components/EntityIntelligencePanel";

export default function App() {
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  const [selectedPersonId, setSelectedPersonId] = useState(null);

  // PERSON / PHONE / ACCOUNT
  const [selectedEntity, setSelectedEntity] = useState(null);

  const [highlightedGraph, setHighlightedGraph] = useState(null);

  const [casesError, setCasesError] = useState(null);
  const [searchError, setSearchError] = useState(null);

  const [searching, setSearching] = useState(false);

  const [page, setPage] = useState("graph");

  const [clickHint, setClickHint] = useState(null);

  const {
    graph,
    identity,
    relatedCases,
    loading,
    error,
    refetchGraph,
  } = useCaseData(selectedCaseId);

  // ------------------------------------------------------------
  // LOAD CASES
  // ------------------------------------------------------------

  useEffect(() => {
    let mounted = true;

    getCases()
      .then((list) => {
        if (!mounted) return;

        setCases(list || []);

        if (list?.length) {
          setSelectedCaseId(list[0].case_id);
        }
      })
      .catch((err) => {
        if (!mounted) return;

        setCasesError(
          apiError(err) || "Cannot reach NETRA backend."
        );
      });

    return () => {
      mounted = false;
    };
  }, []);

  // ------------------------------------------------------------
  // RESET ENTITY SELECTION WHEN CASE CHANGES
  // ------------------------------------------------------------

  useEffect(() => {
    setHighlightedGraph(null);
    setSelectedPersonId(null);
    setSelectedEntity(null);
    setSearchError(null);
    setClickHint(null);
  }, [selectedCaseId]);

  const selectedCase =
    cases.find(
      (c) => Number(c.case_id) === Number(selectedCaseId)
    ) || null;

  const graphData = highlightedGraph || graph;

  // ------------------------------------------------------------
  // SELECTED PERSON LABEL
  // ------------------------------------------------------------

  const personLabel =
    graphData?.nodes?.find(
      (n) =>
        n.id === `PERSON:${selectedPersonId}`
    )?.label || null;

  // ------------------------------------------------------------
  // GRAPH SEARCH
  // ------------------------------------------------------------

  async function handleSearch(name) {
    if (!name || selectedCaseId == null) {
      setSearchError(
        name ? null : "Enter a name to search."
      );
      return;
    }

    setSearching(true);
    setSearchError(null);

    try {
      const data = await searchGraph(
        selectedCaseId,
        name
      );

      setHighlightedGraph(data);

      if (
        data?.matched_node &&
        String(data.matched_node).startsWith("PERSON:")
      ) {
        const personId = Number(
          String(data.matched_node).split(":")[1]
        );

        setSelectedPersonId(personId);

        setSelectedEntity({
          type: "PERSON",
          entityId: personId,
        });
      } else {
        setSearchError(
          "No matching person found in this case graph."
        );
      }
    } catch (err) {
      console.error(err);
      setSearchError(
        apiError(err) || "Graph search failed."
      );
    } finally {
      setSearching(false);
    }
  }

  // ------------------------------------------------------------
  // RESET GRAPH
  // ------------------------------------------------------------

  async function handleResetGraph() {
    setHighlightedGraph(null);
    setSearchError(null);
    setSelectedEntity(null);
    setSelectedPersonId(null);

    try {
      await refetchGraph();
    } catch (err) {
      setSearchError(
        apiError(err) || "Could not reload graph."
      );
    }
  }

  // ------------------------------------------------------------
  // GRAPH NODE CLICK
  // ------------------------------------------------------------

  function handleNodeClick(nodeId) {
    const id = String(nodeId || "");

    const parts = id.split(":");

    const type = String(parts[0] || "").toUpperCase();

    const rawId = parts.slice(1).join(":");

    const entityId = Number(rawId);

    // We intentionally support only these three
    // entity types for Entity Intelligence.

    if (
      !["PERSON", "PHONE", "ACCOUNT"].includes(type)
    ) {
      setSelectedEntity(null);

      setClickHint(
        "Entity Intelligence is available for PERSON, PHONE and ACCOUNT nodes."
      );

      return;
    }

    if (!rawId || !Number.isFinite(entityId)) {
      setSelectedEntity(null);

      setClickHint(
        "Invalid entity identifier received from the graph."
      );

      return;
    }

    // IMPORTANT:
    // This is the state consumed by EntityIntelligencePanel.

    setSelectedEntity({
      type,
      entityId,
    });

    // Existing NETRA modules still use selectedPersonId.

    if (type === "PERSON") {
      setSelectedPersonId(entityId);
    }

    setClickHint(null);
  }

  // ------------------------------------------------------------
  // EXTRACTION CONFIRMATION
  // ------------------------------------------------------------

  async function handleExtractConfirmed(
    graph,
    meta = {}
  ) {
    setHighlightedGraph(null);
    setSelectedEntity(null);
    setSelectedPersonId(null);

    if (meta.newCaseId != null) {
      try {
        const list = await getCases();

        setCases(list || []);
      } catch (err) {
        setCasesError(
          apiError(err) ||
            "Could not refresh case list."
        );
      }

      setSelectedCaseId(meta.newCaseId);
      setPage("graph");
      return;
    }

    await refetchGraph();
    setPage("graph");
  }

  // ------------------------------------------------------------
  // OPEN HYPOTHESES
  // ------------------------------------------------------------

  function openHypotheses(personId) {
    if (personId == null) return;

    setSelectedPersonId(Number(personId));

    setSelectedEntity({
      type: "PERSON",
      entityId: Number(personId),
    });

    setPage("hypotheses");
  }

  // ------------------------------------------------------------
  // RENDER
  // ------------------------------------------------------------

  return (
    <div className="app-shell">

      <Sidebar
        cases={cases}
        selectedCaseId={selectedCaseId}
        selectedCase={selectedCase}
        onSelectCase={setSelectedCaseId}
        error={casesError || error}
        page={page}
        onNav={setPage}
      />

      <main>

        {/* ======================================================
            GRAPH
        ====================================================== */}

        {page === "graph" && (
          <div className="graph-page">

            <SearchBar
              onSearch={handleSearch}
              onReset={handleResetGraph}
              graphData={graphData}
              loading={loading}
              searching={searching}
              searchError={searchError}
            />

            {clickHint && (
              <div className="banner">
                {clickHint}
              </div>
            )}

            {selectedPersonId && (
              <div className="banner">

                Selected{" "}
                {personLabel ||
                  `PERSON:${selectedPersonId}`}

                {" "}

                <button
                  type="button"
                  className="linkish"
                  onClick={() =>
                    setPage("hypotheses")
                  }
                >
                  Open Hypotheses →
                </button>

              </div>
            )}

            <GraphCanvas
              graphData={graphData}
              selectedEntity={selectedEntity}
              onNodeClick={handleNodeClick}
            />

            {/* ==================================================
                ENTITY INTELLIGENCE DRAWER
            ================================================== */}

            {selectedEntity && (
              <div className="entity-drawer">

                <EntityIntelligencePanel
                  caseId={selectedCaseId}
                  selection={selectedEntity}
                  onOpenHypotheses={
                    openHypotheses
                  }
                />

              </div>
            )}

          </div>
        )}

        {/* ======================================================
            IDENTITY
        ====================================================== */}

        {page === "identity" && (
          <div className="page-view">

            <h1 className="page-title">
              Identity
            </h1>

            <IdentityPanel
              identity={identity}
            />

            {selectedEntity && (
              <EntityIntelligencePanel
                caseId={selectedCaseId}
                selection={selectedEntity}
                onOpenHypotheses={
                  openHypotheses
                }
              />
            )}

          </div>
        )}

        {/* ======================================================
            CASE DNA
        ====================================================== */}

        {page === "dna" && (
          <div className="page-view">

            <h1 className="page-title">
              Case DNA
            </h1>

            <RelatedCasesPanel
              relatedCases={relatedCases}
            />

          </div>
        )}

        {/* ======================================================
            HYPOTHESES
        ====================================================== */}

        {page === "hypotheses" && (
          <div className="page-view">

            <h1 className="page-title">
              Hypotheses
            </h1>

            <HypothesisPanel
              caseId={selectedCaseId}
              personId={selectedPersonId}
              personLabel={personLabel}
            />

            <ContradictionPanel
              caseId={selectedCaseId}
              personId={selectedPersonId}
            />

            <CounterfactualPanel
              caseId={selectedCaseId}
              personId={selectedPersonId}
              personLabel={personLabel}
            />

          </div>
        )}

        {/* ======================================================
            UPLOAD
        ====================================================== */}

        {page === "upload" && (
          <div className="page-view">

            <h1 className="page-title">
              Upload Document
            </h1>

            <UploadPanel
              caseId={selectedCaseId}
              onConfirmed={
                handleExtractConfirmed
              }
            />

          </div>
        )}

        {/* ======================================================
            COPILOT
        ====================================================== */}

        {page === "copilot" && (
          <div className="page-view copilot-page">

            <h1 className="page-title">
              Copilot
            </h1>

            <CopilotPanel
              caseId={selectedCaseId}
              fullPage
            />

          </div>
        )}

      </main>

      <footer className="app-footer">
        <DecisionBar
          caseId={selectedCaseId}
        />
      </footer>

    </div>
  );
}