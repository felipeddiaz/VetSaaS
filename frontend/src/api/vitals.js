import api from "./client";

export const getVitals = (medicalRecordId) =>
  api.get(`medical-records/${medicalRecordId}/vitals/`).then(r => r.data);

export const createVitals = (medicalRecordId, data) =>
  api.post(`medical-records/${medicalRecordId}/vitals/`, data).then(r => r.data);

export const getSummary = (medicalRecordId) =>
  api.get(`medical-records/${medicalRecordId}/summary/`).then(r => r.data);
