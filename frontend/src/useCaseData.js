import { useCallback, useEffect, useState } from "react";
import { getCaseGraph, getIdentityCandidates, getRelatedCases } from "./api";

export function useCaseData(caseId) {
  const [graph, setGraph] = useState(null);
  const [identity, setIdentity] = useState(null);
  const [relatedCases, setRelatedCases] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (caseId == null) return;
    setLoading(true);
    setError(null);
    try {
      const [g, ident, related] = await Promise.all([
        getCaseGraph(caseId),
        getIdentityCandidates(caseId),
        getRelatedCases(caseId),
      ]);
      setGraph(g);
      setIdentity(ident);
      setRelatedCases(related);
    } catch (err) {
      setError(err.message || "Failed to load case");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  const refetchGraph = useCallback(async () => {
    if (caseId == null) return null;
    const g = await getCaseGraph(caseId);
    setGraph(g);
    return g;
  }, [caseId]);

  return { graph, identity, relatedCases, loading, error, refetchGraph };
}
