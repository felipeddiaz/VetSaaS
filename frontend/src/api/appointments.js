import api from "./client";

export const getAppointments = async (token, filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const url = params ? `appointments/?${params}` : "appointments/";
    const res = await api.get(url);
    return res.data;
};

export const createAppointment = async (token, data) => {
    const res = await api.post("appointments/", data);
    return res.data;
};

export const updateAppointment = async (token, id, data) => {
    const res = await api.put(`appointments/${id}/`, data);
    return res.data;
};

export const updateAppointmentStatus = async (token, id, status) => {
    const res = await api.patch(`appointments/${id}/status/`, { status });
    return res.data;
};

export const deleteAppointment = async (token, id) => {
    const res = await api.delete(`appointments/${id}/`);
    return res.data;
};
