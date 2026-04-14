import api from "./client";

export const getStaff = async () => {
    const res = await api.get("staff/");
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
