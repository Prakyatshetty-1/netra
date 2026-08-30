import { useEffect, useState } from "react";
import { postDecision } from "../api";

export default function DecisionBar({ caseId }) {
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function decide(decision) {
    if (caseId == null) return;
    const rationale = window.prompt("One-line rationale", "") ?? "";
    const rec = await postDecision(caseId, {
      decision,
      reviewer: "IO Demo",
      rationale,
    });
    setToast(`${rec.decision} · ${rec.timestamp} · ${rec.hash}`);
  }

  return (
    <>
      <div className="decision-bar">
        <div className="decision-label">Decision</div>
        <button className="btn ok" type="button" onClick={() => decide("ACCEPT")}>
          Accept
        </button>
        <button className="btn danger" type="button" onClick={() => decide("REJECT")}>
          Reject
        </button>
        <button className="btn warn" type="button" onClick={() => decide("REQUEST_MORE")}>
          Request More Evidence
        </button>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
