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

export default function App() {
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [selectedPersonId, setSelectedPersonId] = useState(null);
  const [highlightedGraph, setHighlightedGraph] = useState(null);
  const [casesError, setCasesError] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const [searching, setSearching] = useState(false);
  const [page, setPage] = useState("graph");
  const [clickHint, setClickHint] = useState(null);

  const { graph, identity, relatedCases, loading, error, refetchGraph } = useCaseData(selectedCaseId);

  useEffect(() => {
    getCases()
      .then((list) => {
        setCases(list);
        if (list.length) setSelectedCaseId(list[0].case_id);
      })
      .catch((err) => setCasesError(apiError(err) || "Cannot reach API"));
  }, []);

  useEffect(() => {
    setHighlightedGraph(null);
    setSelectedPersonId(null);
    setSearchError(null);
    setClickHint(null);
  }, [selectedCaseId]);

  const selectedCase = cases.find((c) => c.case_id === selectedCaseId) || null;
  const graphData = highlightedGraph || graph;

  const personLabel =
    graphData?.nodes?.find((n) => n.id === `PERSON:${selectedPersonId}`)?.label || null;

  async function handleSearch(name) {
    if (!name || selectedCaseId == null) {
      setSearchError(name ? null : "Enter a name to search");
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const data = await searchGraph(selectedCaseId, name);
      setHighlightedGraph(data);
      if (data.matched_node && String(data.matched_node).startsWith("PERSON:")) {
        setSelectedPersonId(Number(String(data.matched_node).split(":")[1]));
      } else {
        setSearchError("No matching person in this case graph");
      }
    } catch (err) {
      console.error(err);
      setSearchError(apiError(err));
    } finally {
      setSearching(false);
    }
  }

  async function handleResetGraph() {
    setHighlightedGraph(null);
    setSearchError(null);
    try {
      await refetchGraph();
    } catch (err) {
      setSearchError(apiError(err));
    }
  }

  function handleNodeClick(nodeId) {
    const id = String(nodeId);
    if (id.startsWith("PERSON:")) {
      setSelectedPersonId(Number(id.split(":")[1]));
      setClickHint(null);
      return;
    }
    setClickHint("Select a PERSON node (not vehicle/location/account) for hypotheses and counterfactual.");
  }

  async function handleExtractConfirmed() {
    setHighlightedGraph(null);
    await refetchGraph();
    setPage("graph");
  }

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
            {clickHint && <div className="banner">{clickHint}</div>}
            {selectedPersonId && (
              <div className="banner">
                Selected {personLabel || `PERSON:${selectedPersonId}`}.{" "}
                <button type="button" className="linkish" onClick={() => setPage("hypotheses")}>
                  Open Hypotheses →
                </button>
              </div>
            )}
            <GraphCanvas
              graphData={graphData}
              selectedPersonId={selectedPersonId}
              onNodeClick={handleNodeClick}
            />
          </div>
        )}
        {page === "identity" && (
          <div className="page-view">
            <h1 className="page-title">Identity</h1>
            <IdentityPanel identity={identity} />
          </div>
        )}
        {page === "dna" && (
          <div className="page-view">
            <h1 className="page-title">Case DNA</h1>
            <RelatedCasesPanel relatedCases={relatedCases} />
          </div>
        )}
        {page === "hypotheses" && (
          <div className="page-view">
            <h1 className="page-title">Hypotheses</h1>
            <HypothesisPanel caseId={selectedCaseId} personId={selectedPersonId} personLabel={personLabel} />
            <ContradictionPanel caseId={selectedCaseId} personId={selectedPersonId} />
            <CounterfactualPanel caseId={selectedCaseId} personId={selectedPersonId} personLabel={personLabel} />
          </div>
        )}
        {page === "upload" && (
          <div className="page-view">
            <h1 className="page-title">Upload Document</h1>
            <UploadPanel caseId={selectedCaseId} onConfirmed={handleExtractConfirmed} />
          </div>
        )}
        {page === "copilot" && (
          <div className="page-view copilot-page">
            <h1 className="page-title">Copilot</h1>
            <CopilotPanel caseId={selectedCaseId} fullPage />
          </div>
        )}
      </main>
      <footer className="app-footer">
        <DecisionBar caseId={selectedCaseId} />
      </footer>
    </div>
  );
}
