import api from "./client";

export const getStaff = async (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    const url = qs ? `staff/?${qs}` : "staff/";
    const res = await api.get(url);
    return res.data;
};

export const createStaff = async (data) => {
    const res = await api.post("staff/create/", data);
    return res.data;
};

export const deactivateStaff = async (id) => {
    const res = await api.delete(`staff/${id}/`);
    return res.data;
};
