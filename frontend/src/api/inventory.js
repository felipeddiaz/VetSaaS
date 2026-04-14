import api from "./client";

export const getProducts = (params = {}) =>
    api.get("inventory/products/", { params }).then(r => r.data);

export const getLowStockProducts = () =>
    api.get("inventory/products/low-stock/").then(r => r.data);

export const createProduct = (data) =>
    api.post("inventory/products/", data).then(r => r.data);

export const updateProduct = (id, data) =>
    api.put(`inventory/products/${id}/`, data).then(r => r.data);

export const deleteProduct = (id) =>
    api.delete(`inventory/products/${id}/`);

export const adjustStock = (id, data) =>
    api.post(`inventory/products/${id}/adjust/`, data).then(r => r.data);

export const getMovements = (params = {}) =>
    api.get("inventory/movements/", { params }).then(r => r.data);

export const getMedicalRecordProducts = (medicalRecordId) =>
    api.get(`medical-records/${medicalRecordId}/products/`).then(r => r.data);

export const addMedicalRecordProduct = (medicalRecordId, data) =>
    api.post(`medical-records/${medicalRecordId}/products/`, data).then(r => r.data);

export const removeMedicalRecordProduct = (medicalRecordId, id) =>
    api.delete(`medical-records/${medicalRecordId}/products/${id}/`);

export const getUnitChoices = () =>
    api.get("inventory/units/").then(r => r.data);

export const getPresentations = (params = {}) =>
    api.get("inventory/presentations/", { params }).then(r => r.data);
