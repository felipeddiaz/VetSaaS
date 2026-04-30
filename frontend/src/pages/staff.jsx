import { useState, useEffect } from "react";
import { getStaff, createStaff, deactivateStaff } from "../api/staff";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import { useConfirm } from "../components/ConfirmDialog";
import { toast } from "sonner";

const EMPTY_FORM = {
    username: "",
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    role: "VET",
    specialty: ""
};

const ROLE_BADGE = {
    ADMIN_SAAS: "badge-danger",
    ADMIN: "badge-warning",
    VET: "badge-primary",
    ASSISTANT: "badge-default",
};

const ROLE_LABELS = {
    ADMIN_SAAS: "Admin SaaS",
    ADMIN: "Administrador",
    VET: "Veterinario",
    ASSISTANT: "Asistente",
};

const Staff = () => {
    const { user, initializing } = useAuth();
    const confirm = useConfirm();
    const isAdmin = user?.role === "ADMIN";

    const [staff, setStaff] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);

    useEffect(() => {
        if (!initializing && user) {
            fetchStaff();
        }
    }, [initializing, user]);

    const fetchStaff = async () => {
        try {
            setLoading(true);
            const data = await getStaff();
            setStaff(data);
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        const usernameRe = /^[A-Za-z0-9_.\-]+$/;
        const nameRe = /^[A-Za-zÁÉÍÓÚáéíóúñÑ ]+$/;

        if (!form.username.trim()) { toast.error("El nombre de usuario es obligatorio"); return; }
        if (!usernameRe.test(form.username.trim())) { toast.error("El usuario solo puede contener letras, números, puntos, guiones y guiones bajos"); return; }
        if (!form.first_name.trim()) { toast.error("El nombre es obligatorio"); return; }
        if (!nameRe.test(form.first_name.trim())) { toast.error("El nombre solo puede contener letras y espacios"); return; }
        if (!form.email.trim()) { toast.error("El email es obligatorio"); return; }
        if (!form.password || form.password.length < 8) { toast.error("La contraseña debe tener al menos 8 caracteres"); return; }
        if (!/[A-Z]/.test(form.password)) { toast.error("La contraseña debe contener al menos una mayúscula"); return; }
        if (!/[0-9]/.test(form.password)) { toast.error("La contraseña debe contener al menos un número"); return; }

        try {
            await toast.promise(createStaff(form), {
                loading: 'Creando usuario...',
                success: 'Usuario creado exitosamente',
                error: (err) => {
                    const d = err.response?.data;
                    if (d) {
                        const first = Object.values(d).flat()[0];
                        if (first) return String(first);
                    }
                    return "Error al crear usuario";
                },
            });
            setForm(EMPTY_FORM);
            setShowModal(false);
            fetchStaff();
        } catch (err) {
            // Modal stays open — toast already shows the error
        }
    };

    const handleDeactivate = async (id) => {
        const ok = await confirm({
            title: "Desactivar miembro",
            message: "El miembro perderá acceso al sistema. Esta acción se puede revertir desde la base de datos.",
            confirmText: "Desactivar",
            dangerMode: true,
        });
        if (!ok) return;
        try {
            await toast.promise(deactivateStaff(id), {
                loading: 'Desactivando...',
                success: 'Usuario desactivado',
                error: 'Error al desactivar usuario'
            });
            fetchStaff();
        } catch (err) {
        }
    };

    const closeModal = () => {
        setForm(EMPTY_FORM);
        setShowModal(false);
    };

    if (loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    return (
        <div>
            <div className="page-header">
                <div>
                    <h1 className="page-title">Equipo</h1>
                    <p className="page-subtitle">{staff.length} miembro{staff.length !== 1 ? "s" : ""}</p>
                </div>
                {isAdmin && (
                    <button
                        className="btn btn-primary btn-md"
                        onClick={() => setShowModal(true)}
                    >
                        + Agregar miembro
                    </button>
                )}
            </div>

            {staff.length === 0 ? (
                <div className="empty-state">
                    <p className="empty-state-title">Aún no hay miembros registrados</p>
                    <p className="empty-state-sub">
                        {isAdmin ? "Usa el botón de arriba para agregar miembros" : "Contacta al administrador"}
                    </p>
                </div>
            ) : (
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Nombre</th>
                                <th>Usuario</th>
                                <th>Email</th>
                                <th>Rol</th>
                                <th>Especialidad</th>
                                {isAdmin && <th></th>}
                            </tr>
                        </thead>
                        <tbody>
                            {staff.map((member) => (
                                <tr key={member.id}>
                                    <td style={{ fontWeight: "600" }}>
                                        {member.first_name} {member.last_name}
                                    </td>
                                    <td style={{ color: "var(--c-text-2)" }}>@{member.username}</td>
                                    <td style={{ color: "var(--c-text-2)" }}>{member.email}</td>
                                    <td>
                                        <span className={`badge ${ROLE_BADGE[member.role] || "badge-default"}`}>
                                            {ROLE_LABELS[member.role] || member.role}
                                        </span>
                                    </td>
                                    <td style={{ color: "var(--c-text-3)" }}>{member.specialty || "—"}</td>
                                    {isAdmin && (
                                        <td>
                                            <button
                                                className="btn btn-danger btn-sm"
                                                onClick={() => handleDeactivate(member.id)}
                                            >
                                                Desactivar
                                            </button>
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Modal Nuevo Miembro */}
            {showModal && (
                <div className="modal-overlay">
                    <div className="modal modal-lg">
                        <div className="modal-header">
                            <h3>Nuevo Miembro</h3>
                            <button className="modal-close" onClick={closeModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
                                    <div className="form-group">
                                        <label className="form-label">NOMBRE DE USUARIO *</label>
                                        <input
                                            className="input"
                                            placeholder="usuario123"
                                            value={form.username}
                                            onChange={e => setForm({ ...form, username: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">EMAIL *</label>
                                        <input
                                            type="email"
                                            className="input"
                                            placeholder="email@ejemplo.com"
                                            value={form.email}
                                            onChange={e => setForm({ ...form, email: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">NOMBRE *</label>
                                        <input
                                            className="input"
                                            placeholder="Juan"
                                            value={form.first_name}
                                            onChange={e => setForm({ ...form, first_name: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">APELLIDO</label>
                                        <input
                                            className="input"
                                            placeholder="Pérez"
                                            value={form.last_name}
                                            onChange={e => setForm({ ...form, last_name: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">CONTRASEÑA *</label>
                                        <input
                                            type="password"
                                            className="input"
                                            placeholder="Mínimo 6 caracteres"
                                            value={form.password}
                                            onChange={e => setForm({ ...form, password: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">ROL *</label>
                                        <select
                                            className="select-input"
                                            value={form.role}
                                            onChange={e => setForm({ ...form, role: e.target.value })}
                                        >
                                            <option value="VET">Veterinario</option>
                                            <option value="ASSISTANT">Asistente</option>
                                            <option value="ADMIN">Administrador</option>
                                        </select>
                                    </div>
                                    <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                                        <label className="form-label">ESPECIALIDAD</label>
                                        <input
                                            className="input"
                                            placeholder="Cirugía, Dermatología..."
                                            value={form.specialty}
                                            onChange={e => setForm({ ...form, specialty: e.target.value })}
                                        />
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div className="modal-footer">
                            <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleSubmit}>
                                Guardar
                            </button>
                            <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeModal}>
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Staff;
