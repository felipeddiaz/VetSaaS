import api from "./client";

export const getMedicalRecords = async (token, filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const url = params ? `medical-records/?${params}` : "medical-records/";
    const res = await api.get(url);
    return res.data;
};

export const getMedicalRecordsByPet = async (token, petId, page = 1) => {
    const res = await api.get(`medical-records/pet/${petId}/?page=${page}`);
    return res.data;
};

export const getMedicalRecord = async (token, id) => {
    const res = await api.get(`medical-records/${id}/`);
    return res.data;
};

export const createMedicalRecord = async (token, data) => {
    const res = await api.post("medical-records/", data);
    return res.data;
};

export const updateMedicalRecord = async (token, id, data) => {
    const res = await api.put(`medical-records/${id}/`, data);
    return res.data;
};

export const deleteMedicalRecord = async (token, id) => {
    const res = await api.delete(`medical-records/${id}/`);
    return res.data;
};

export const closeMedicalRecord = async (token, id) => {
    const res = await api.post(`medical-records/${id}/close/`);
    return res.data;
};
