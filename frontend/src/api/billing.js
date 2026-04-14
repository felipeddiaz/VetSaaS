import api from "./client";

// Servicios
export const getServices = (params = {}) =>
    api.get("billing/services/", { params }).then(r => r.data);

export const createService = (data) =>
    api.post("billing/services/", data).then(r => r.data);

export const updateService = (id, data) =>
    api.put(`billing/services/${id}/`, data).then(r => r.data);

export const deleteService = (id) =>
    api.delete(`billing/services/${id}/`);

// Facturas
export const getInvoices = (params = {}) =>
    api.get("billing/invoices/", { params }).then(r => r.data);

export const getInvoice = (id) =>
    api.get(`billing/invoices/${id}/`).then(r => r.data);

export const createInvoice = (data) =>
    api.post("billing/invoices/", data).then(r => r.data);

export const updateInvoice = (id, data) =>
    api.patch(`billing/invoices/${id}/`, data).then(r => r.data);

export const confirmInvoice = (id) =>
    api.patch(`billing/invoices/${id}/confirm/`).then(r => r.data);

export const payInvoice = (id, paymentMethod) =>
    api.patch(`billing/invoices/${id}/pay/`, { payment_method: paymentMethod }).then(r => r.data);

// Ítems de factura
export const addInvoiceItem = (invoiceId, data) =>
    api.post(`billing/invoices/${invoiceId}/items/`, data).then(r => r.data);

export const updateInvoiceItem = (invoiceId, itemId, data) =>
    api.patch(`billing/invoices/${invoiceId}/items/${itemId}/`, data).then(r => r.data);

export const deleteInvoiceItem = (invoiceId, itemId) =>
    api.delete(`billing/invoices/${invoiceId}/items/${itemId}/`);
