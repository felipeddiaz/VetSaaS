import api from "./client";

export const getPrescriptions = (params = {}) =>
    api.get("prescriptions/", { params }).then(r => r.data);

export const getPrescription = (id) =>
    api.get(`prescriptions/${id}/`).then(r => r.data);

export const getPrescriptionsByPet = (petId) =>
    api.get(`prescriptions/pet/${petId}/`).then(r => r.data);

export const createPrescription = (data) =>
    api.post("prescriptions/", data).then(r => r.data);

export const updatePrescription = (id, data) =>
    api.put(`prescriptions/${id}/`, data).then(r => r.data);

export const deletePrescription = (id) =>
    api.delete(`prescriptions/${id}/`);

export const downloadPrescriptionPDF = (id) =>
    api.get(`prescriptions/${id}/pdf/`, { responseType: "blob" }).then(r => r.data);
