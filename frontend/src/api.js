import axios from "axios";

const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export function apiError(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return err?.message || "Request failed";
}

export const getCases = () => axios.get(`${BASE}/cases`).then((r) => r.data);

export const getCaseGraph = (caseId) =>
  axios.get(`${BASE}/cases/${caseId}/graph`).then((r) => r.data);

export const searchGraph = (caseId, name) =>
  axios
    .get(`${BASE}/cases/${caseId}/graph/search`, { params: { name } })
    .then((r) => r.data);

export const getIdentityCandidates = (caseId) =>
  axios.get(`${BASE}/cases/${caseId}/identity-candidates`).then((r) => r.data);

export const getRelatedCases = (caseId) =>
  axios.get(`${BASE}/cases/${caseId}/related-cases`).then((r) => r.data);

export const getHypotheses = (caseId, personId) =>
  axios.get(`${BASE}/cases/${caseId}/hypotheses/${personId}`).then((r) => r.data);

export const getContradictions = (caseId, personId) =>
  axios.get(`${BASE}/cases/${caseId}/contradictions/${personId}`).then((r) => r.data);

export const runCounterfactual = (caseId, personId) =>
  axios.post(`${BASE}/cases/${caseId}/counterfactual/${personId}`).then((r) => r.data);

export const askCopilot = (caseId, question) =>
  axios.post(`${BASE}/cases/${caseId}/ask`, { question }).then((r) => r.data);

export const postDecision = (caseId, payload) =>
  axios.post(`${BASE}/cases/${caseId}/decisions`, payload).then((r) => r.data);

export const uploadPdf = (caseId, file) => {
  const form = new FormData();
  form.append("file", file);
  // Let the browser set multipart boundary — do not force Content-Type.
  return axios.post(`${BASE}/cases/${caseId}/upload-pdf`, form).then((r) => r.data);
};

export const confirmExtraction = (caseId, payload) =>
  axios.post(`${BASE}/cases/${caseId}/upload-pdf/confirm`, payload).then((r) => r.data);

export const createCase = (payload) =>
  axios.post(`${BASE}/cases`, payload).then((r) => r.data);

export const uploadImage = (caseId, file) => {
  const form = new FormData();
  form.append("file", file);
  return axios.post(`${BASE}/cases/${caseId}/upload-image`, form).then((r) => r.data);
};

export const confirmImageExtraction = (caseId, payload) =>
  axios.post(`${BASE}/cases/${caseId}/upload-image/confirm`, payload).then((r) => r.data);
