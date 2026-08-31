import { useEffect, useState } from "react";
import { apiError, postDecision } from "../api";

export default function DecisionBar({ caseId }) {
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function decide(decision) {
    if (caseId == null || busy) return;
    const rationale = window.prompt("One-line rationale", "");
    if (rationale === null) return;
    setBusy(true);
    setErr(null);
    try {
      const rec = await postDecision(caseId, {
        decision,
        reviewer: "IO Demo",
        rationale,
      });
      setToast(`${rec.decision} · ${rec.timestamp} · ${rec.hash}`);
    } catch (e) {
      console.error(e);
      setErr(apiError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="decision-bar">
        <div className="decision-label">Decision</div>
        <button className="btn ok" type="button" disabled={busy} onClick={() => decide("ACCEPT")}>
          {busy ? "Saving…" : "Accept"}
        </button>
        <button className="btn danger" type="button" disabled={busy} onClick={() => decide("REJECT")}>
          Reject
        </button>
        <button className="btn warn" type="button" disabled={busy} onClick={() => decide("REQUEST_MORE")}>
          Request More Evidence
        </button>
        {err && <span className="error-inline">{err}</span>}
      </div>
      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
