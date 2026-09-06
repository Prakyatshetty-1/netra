import axios from "axios";

const BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

/* =========================================================
   ERROR HANDLING
   ========================================================= */

export function apiError(err) {
  const detail = err?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((x) => x?.msg || JSON.stringify(x))
      .join("; ");
  }

  return (
    err?.message ||
    "Request failed."
  );
}

/* =========================================================
   CASES
   ========================================================= */

export const getCases = () =>
  axios
    .get(`${BASE}/cases`)
    .then((r) => r.data);

export const createCase = (payload) =>
  axios
    .post(`${BASE}/cases`, payload)
    .then((r) => r.data);

/* =========================================================
   GRAPH
   ========================================================= */

export const getCaseGraph = (caseId) =>
  axios
    .get(`${BASE}/cases/${caseId}/graph`)
    .then((r) => r.data);

export const searchGraph = (
  caseId,
  name
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/graph/search`,
      {
        params: { name },
      }
    )
    .then((r) => r.data);

/* =========================================================
   IDENTITY
   ========================================================= */

export const getIdentityCandidates = (
  caseId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/identity-candidates`
    )
    .then((r) => r.data);

/* =========================================================
   RELATED CASES
   ========================================================= */

export const getRelatedCases = (
  caseId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/related-cases`
    )
    .then((r) => r.data);

/* =========================================================
   HYPOTHESES
   ========================================================= */

export const getHypotheses = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/hypotheses/${personId}`
    )
    .then((r) => r.data);

/* =========================================================
   CONTRADICTIONS
   ========================================================= */

export const getContradictions = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/contradictions/${personId}`
    )
    .then((r) => r.data);

/* =========================================================
   COUNTERFACTUAL
   ========================================================= */

export const runCounterfactual = (
  caseId,
  personId
) =>
  axios
    .post(
      `${BASE}/cases/${caseId}/counterfactual/${personId}`
    )
    .then((r) => r.data);

/* =========================================================
   COPILOT
   ========================================================= */

export const askCopilot = (
  caseId,
  question
) =>
  axios
    .post(
      `${BASE}/cases/${caseId}/ask`,
      {
        question,
      }
    )
    .then((r) => r.data);

/* =========================================================
   DECISIONS
   ========================================================= */

export const postDecision = (
  caseId,
  payload
) =>
  axios
    .post(
      `${BASE}/cases/${caseId}/decisions`,
      payload
    )
    .then((r) => r.data);

/* =========================================================
   DOCUMENT EXTRACTION
   ========================================================= */

export const uploadPdf = (
  caseId,
  file
) => {
  const form = new FormData();

  form.append(
    "file",
    file
  );

  return axios
    .post(
      `${BASE}/cases/${caseId}/upload-pdf`,
      form
    )
    .then((r) => r.data);
};

export const confirmExtraction = (
  caseId,
  payload
) =>
  axios
    .post(
      `${BASE}/cases/${caseId}/upload-pdf/confirm`,
      payload
    )
    .then((r) => r.data);

/* =========================================================
   ENTITY INTELLIGENCE
   ========================================================= */

export const getPersonIntelligence = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/persons/${personId}/intelligence`
    )
    .then((r) => r.data);

export const getPhoneIntelligence = (
  caseId,
  phoneId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/phones/${phoneId}/intelligence`
    )
    .then((r) => r.data);

export const getAccountIntelligence = (
  caseId,
  accountId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/accounts/${accountId}/intelligence`
    )
    .then((r) => r.data);

/* =========================================================
   ENTITY IDENTITY COMPARISON
   ========================================================= */

/*
 * PERSON → DigiLocker comparison
 *
 * Backend returns:
 * {
 *   verified,
 *   status,
 *   confidence,
 *   police_evidence,
 *   government_evidence,
 *   field_comparison,
 *   explainable_ai
 * }
 */

export const getPersonIdentityComparison = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/persons/${personId}/identity-comparison`
    )
    .then((r) => r.data);

/*
 * PHONE → PERSON → DigiLocker comparison
 */

export const getPhoneIdentityComparison = (
  caseId,
  phoneId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/phones/${phoneId}/identity-comparison/${personId}`
    )
    .then((r) => r.data);

/*
 * ACCOUNT → PERSON → DigiLocker comparison
 */

export const getAccountIdentityComparison = (
  caseId,
  accountId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/accounts/${accountId}/identity-comparison/${personId}`
    )
    .then((r) => r.data);

/* =========================================================
   DIGILOCKER
   ========================================================= */

/*
 * Start DigiLocker authorization.
 *
 * IMPORTANT:
 * This is GET, not POST.
 *
 * In mock mode backend returns:
 * {
 *   mode: "mock",
 *   authorization_url: null,
 *   case_id,
 *   person_id
 * }
 *
 * In production mode backend returns:
 * {
 *   mode: "production",
 *   authorization_url: "...",
 *   case_id,
 *   person_id
 * }
 */

export const startDigiLockerVerification = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/persons/${personId}/digilocker/start`
    )
    .then((r) => r.data);

/*
 * Local synthetic/demo verification.
 *
 * This does NOT access real DigiLocker.
 */

export const mockDigiLockerVerification = (
  caseId,
  personId
) =>
  axios
    .post(
      `${BASE}/cases/${caseId}/persons/${personId}/digilocker/mock-verify`
    )
    .then((r) => r.data);

/*
 * Existing stored verification.
 */

export const getDigiLockerVerification = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/persons/${personId}/digilocker`
    )
    .then((r) => r.data);

/* =========================================================
   COMPATIBILITY HELPERS
   ========================================================= */

/*
 * These functions are intentionally kept because the
 * EntityIntelligencePanel was already importing them.
 *
 * They all ultimately use the SAME existing DigiLocker
 * mock endpoint. There is no second DigiLocker system.
 */

export const verifyPersonDemo = (
  caseId,
  personId
) =>
  mockDigiLockerVerification(
    caseId,
    personId
  );

export const verifyPhoneDemo = (
  caseId,
  personId
) =>
  mockDigiLockerVerification(
    caseId,
    personId
  );

export const verifyAccountDemo = (
  caseId,
  personId
) =>
  mockDigiLockerVerification(
    caseId,
    personId
  );

/* =========================================================
   SELECTED PERSON PROFILE
   ========================================================= */

export const getEntityProfile = (
  caseId,
  personId
) =>
  axios
    .get(
      `${BASE}/cases/${caseId}/persons/${personId}/entity-profile`
    )
    .then((r) => r.data);