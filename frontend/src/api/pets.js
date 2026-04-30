import api from "./client";

export const getPets = (params = {}) =>
    api.get("pets/", { params }).then(r => r.data);

export const getPet = async (id) => {
    const res = await api.get(`pets/${id}/`);
    return res.data;
};

export const createPet = async (token, data) => {
    const res = await api.post("pets/", data);
    return res.data;
};

export const updatePet = async (token, id, data) => {
    const res = await api.put(`pets/${id}/`, data);
    return res.data;
};

export const deletePet = async (token, id) => {
    const res = await api.delete(`pets/${id}/`);
    return res.data;
};

export const getOwners = (params = {}) =>
    api.get("owners/", { params }).then(r => r.data);

