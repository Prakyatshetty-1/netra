import { useEffect, useState } from "react";
import { getCases, searchGraph } from "./api";
import { useCaseData } from "./useCaseData";
import Sidebar from "./components/Sidebar";
import SearchBar from "./components/SearchBar";
import GraphCanvas from "./components/GraphCanvas";
import IdentityPanel from "./components/IdentityPanel";
import RelatedCasesPanel from "./components/RelatedCasesPanel";
import HypothesisPanel from "./components/HypothesisPanel";
import ContradictionPanel from "./components/ContradictionPanel";
import CounterfactualPanel from "./components/CounterfactualPanel";
import CopilotPanel from "./components/CopilotPanel";
import DecisionBar from "./components/DecisionBar";

export default function App() {
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [selectedPersonId, setSelectedPersonId] = useState(null);
  const [highlightedGraph, setHighlightedGraph] = useState(null);
  const [casesError, setCasesError] = useState(null);

  const { graph, identity, relatedCases, loading, error, refetchGraph } = useCaseData(selectedCaseId);

  useEffect(() => {
    getCases()
      .then((list) => {
        setCases(list);
        if (list.length) setSelectedCaseId(list[0].case_id);
      })
      .catch((err) => setCasesError(err.message || "Cannot reach API"));
  }, []);

  useEffect(() => {
    setHighlightedGraph(null);
    setSelectedPersonId(null);
  }, [selectedCaseId]);

  const selectedCase = cases.find((c) => c.case_id === selectedCaseId) || null;
  const graphData = highlightedGraph || graph;

  const personLabel =
    graphData?.nodes?.find((n) => n.id === `PERSON:${selectedPersonId}`)?.label || null;

  async function handleSearch(name) {
    if (!name || selectedCaseId == null) return;
    const data = await searchGraph(selectedCaseId, name);
    setHighlightedGraph(data);
    if (data.matched_node && String(data.matched_node).startsWith("PERSON:")) {
      setSelectedPersonId(Number(String(data.matched_node).split(":")[1]));
    }
  }

  async function handleResetGraph() {
    setHighlightedGraph(null);
    await refetchGraph();
  }

  function handleNodeClick(nodeId) {
    const id = String(nodeId);
    if (id.startsWith("PERSON:")) {
      setSelectedPersonId(Number(id.split(":")[1]));
    } else if (/^\d+$/.test(id)) {
      setSelectedPersonId(Number(id));
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        cases={cases}
        selectedCaseId={selectedCaseId}
        selectedCase={selectedCase}
        onSelectCase={setSelectedCaseId}
        error={casesError || error}
      />
      <main>
        <SearchBar
          onSearch={handleSearch}
          onReset={handleResetGraph}
          graphData={graphData}
          loading={loading}
        />
        <GraphCanvas graphData={graphData} onNodeClick={handleNodeClick} />
      </main>
      <aside className="right-panel">
        <IdentityPanel identity={identity} />
        <RelatedCasesPanel relatedCases={relatedCases} />
        <HypothesisPanel caseId={selectedCaseId} personId={selectedPersonId} personLabel={personLabel} />
        <ContradictionPanel caseId={selectedCaseId} personId={selectedPersonId} />
        <CounterfactualPanel caseId={selectedCaseId} personId={selectedPersonId} personLabel={personLabel} />
      </aside>
      <footer className="app-footer">
        <CopilotPanel caseId={selectedCaseId} />
        <DecisionBar caseId={selectedCaseId} />
      </footer>
    </div>
  );
}
