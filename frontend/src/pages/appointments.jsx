import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
    getAppointments, createAppointment,
    updateAppointment, updateAppointmentStatus,
} from "../api/appointments";
import { getPets } from "../api/pets";
import { getStaff } from "../api/staff";
import { useAuth } from "../auth/authContext";

// ── Constants ──────────────────────────────────────────────────────────────────
const DAYS_ES  = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"];
const MONTHS_S = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const MONTHS_F = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const HOURS    = Array.from({ length: 13 }, (_, i) => i + 7); // 7 – 19

const PAL_KEYS = ["teal","amber","blue","purple","rose","slate"];
const PAL = {
    teal:   { bg:"#E1F5EE", text:"#085041", border:"#1D9E75" },
    amber:  { bg:"#FAEEDA", text:"#633806", border:"#BA7517" },
    blue:   { bg:"#E6F1FB", text:"#0C447C", border:"#378ADD" },
    purple: { bg:"#F0EDFB", text:"#3B1F79", border:"#7C5CBF" },
    rose:   { bg:"#FCE8EF", text:"#7B1535", border:"#D43B6A" },
    slate:  { bg:"#F1F4F8", text:"#2E3A4E", border:"#7A8FA6" },
};

const S_BADGE = { scheduled:"badge-info", done:"badge-success", canceled:"badge-danger" };
const S_LABEL = { scheduled:"Programada",  done:"Completada",    canceled:"Cancelada"   };

// ── Utils ──────────────────────────────────────────────────────────────────────
const pad = n => String(n).padStart(2,"0");

function getWeekStart(base, offset = 0) {
    const d = new Date(base);
    d.setDate(d.getDate() - d.getDay() + offset * 7);
    d.setHours(0, 0, 0, 0);
    return d;
}

function isSameDay(a, b) {
    return a.getFullYear() === b.getFullYear() &&
           a.getMonth()    === b.getMonth()    &&
           a.getDate()     === b.getDate();
}

function weekTitle(ws) {
    const we = new Date(ws); we.setDate(we.getDate() + 6);
    if (ws.getMonth() === we.getMonth())
        return `${ws.getDate()} – ${we.getDate()} de ${MONTHS_F[ws.getMonth()]} ${ws.getFullYear()}`;
    return `${ws.getDate()} ${MONTHS_S[ws.getMonth()]} – ${we.getDate()} ${MONTHS_S[we.getMonth()]} ${ws.getFullYear()}`;
}

function toDateStr(d) {
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}

function apptHour(a) {
    return parseInt(a.start_time?.split(":")[0] ?? "9", 10);
}

// ── Shared style atoms ─────────────────────────────────────────────────────────
const lblStyle = {
    display:"block", fontSize:"12px", fontWeight:"500",
    color:"var(--c-text-2)", marginBottom:"4px",
};

const miniNavBtn = {
    background:"none", border:"none", cursor:"pointer",
    color:"var(--c-text-2)", fontSize:"16px", padding:"2px 6px",
};

const calNavBtn = {
    background:"none", border:"1px solid var(--c-border)", borderRadius:"var(--r-md)",
    padding:"5px 10px", cursor:"pointer", color:"var(--c-text-2)",
    fontSize:"14px", boxShadow:"var(--shadow-xs)",
};

// ── MiniCalendar ───────────────────────────────────────────────────────────────
function MiniCalendar({ today, selectedDate, onSelect }) {
    const [view, setView] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
    const firstDow     = view.getDay();
    const daysInMonth  = new Date(view.getFullYear(), view.getMonth()+1, 0).getDate();
    const cells = [];
    for (let i = 0; i < firstDow; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);

    return (
        <div>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"10px"}}>
                <button style={miniNavBtn}
                    onClick={()=>setView(v=>new Date(v.getFullYear(),v.getMonth()-1,1))}>‹</button>
                <span style={{fontSize:"13px",fontWeight:"500",color:"var(--c-text)"}}>
                    {MONTHS_F[view.getMonth()]} {view.getFullYear()}
                </span>
                <button style={miniNavBtn}
                    onClick={()=>setView(v=>new Date(v.getFullYear(),v.getMonth()+1,1))}>›</button>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(7,1fr)",gap:"1px"}}>
                {DAYS_ES.map(d => (
                    <div key={d} style={{fontSize:"10px",color:"var(--c-text-3)",textAlign:"center",
                        paddingBottom:"4px",textTransform:"uppercase",fontWeight:"600"}}>
                        {d[0]}
                    </div>
                ))}
                {cells.map((d, i) => {
                    if (!d) return <div key={`e${i}`} />;
                    const date    = new Date(view.getFullYear(), view.getMonth(), d);
                    const isToday = isSameDay(date, today);
                    const isSel   = selectedDate && isSameDay(date, selectedDate);
                    return (
                        <div key={d} onClick={()=>onSelect(date)} style={{
                            fontSize:"12px", textAlign:"center", padding:"5px 2px",
                            borderRadius:"50%", cursor:"pointer",
                            background: isToday?"var(--c-primary)": isSel?"var(--c-primary-light)":"transparent",
                            color:      isToday?"#fff": isSel?"var(--c-primary-dark)":"var(--c-text-2)",
                            fontWeight: (isToday||isSel)?"600":"400",
                        }}>
                            {d}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ── ApptBadge (calendar cell) ──────────────────────────────────────────────────
function ApptBadge({ appt, pal, petName, ownerName, onClick }) {
    const canceled = appt.status === "canceled";
    const c = canceled
        ? { bg:"var(--c-subtle)", text:"var(--c-text-3)", border:"var(--c-border-2)" }
        : pal;
    return (
        <div onClick={e=>{e.stopPropagation(); onClick(appt);}} style={{
            position:"absolute", left:"3px", right:"3px", top:"3px",
            background:c.bg, borderLeft:`3px solid ${c.border}`,
            borderRadius:"5px", padding:"3px 6px", cursor:"pointer", zIndex:2,
            overflow:"hidden", opacity: canceled ? 0.55 : 1,
        }}>
            <span style={{display:"block",fontSize:"11px",fontWeight:"600",
                color:c.text,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>
                {petName}{ownerName ? ` · ${ownerName}` : ""}
            </span>
            <span style={{fontSize:"10px",color:c.text,opacity:0.72}}>
                {appt.reason}
            </span>
        </div>
    );
}

// ── Detail Modal ───────────────────────────────────────────────────────────────
function DetailModal({ appt, petName, vetName, petId, onClose, onStatusChange, onEdit, navigate, canEdit }) {
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal modal-md" onClick={e=>e.stopPropagation()}>
                <div className="modal-header">
                    <div>
                        <h3 style={{marginBottom:"5px"}}>{petName || "—"}</h3>
                        <span className={`badge ${S_BADGE[appt.status]}`}>{S_LABEL[appt.status]}</span>
                    </div>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>
                <div className="modal-body">
                    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"10px"}}>
                        {[
                            ["Veterinario", vetName || appt.veterinarian_name || "—"],
                            ["Fecha", new Date(appt.date+"T00:00:00").toLocaleDateString("es-ES",{weekday:"short",day:"numeric",month:"long",year:"numeric"})],
                            ["Horario", `${appt.start_time?.slice(0,5)} – ${appt.end_time?.slice(0,5)}`],
                            ["Motivo", appt.reason],
                        ].map(([k,v])=>(
                            <div key={k} style={{background:"var(--c-subtle)",borderRadius:"var(--r-md)",padding:"9px 11px"}}>
                                <div style={{fontSize:"11px",color:"var(--c-text-3)",fontWeight:"600",
                                    textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:"3px"}}>{k}</div>
                                <div style={{fontSize:"13px",fontWeight:"500",color:"var(--c-text)"}}>{v}</div>
                            </div>
                        ))}
                    </div>
                    {appt.notes && (
                        <div style={{marginTop:"12px",padding:"10px 12px",background:"var(--c-subtle)",
                            borderRadius:"var(--r-md)",fontSize:"13px",color:"var(--c-text-2)"}}>
                            {appt.notes}
                        </div>
                    )}
                </div>
                <div className="modal-footer" style={{flexDirection:"column",gap:"8px"}}>
                    {appt.status === "scheduled" && canEdit && (
                        <div style={{display:"flex",gap:"8px",width:"100%"}}>
                            <button className="btn btn-info btn-md" style={{flex:1}}
                                onClick={()=>onEdit(appt)}>Editar</button>
                            <button className="btn btn-md" style={{flex:1,background:"#22c55e",borderColor:"#22c55e",color:"#fff"}}
                                onClick={()=>onStatusChange(appt.id,"done")}>Completar</button>
                            <button className="btn btn-danger btn-md" style={{flex:1}}
                                onClick={()=>{ if(confirm("¿Cancelar esta cita?")) onStatusChange(appt.id,"canceled"); }}>
                                Cancelar
                            </button>
                        </div>
                    )}
                    {appt.status === "canceled" && canEdit && (
                        <button className="btn btn-info btn-md" style={{width:"100%"}}
                            onClick={()=>onStatusChange(appt.id,"scheduled")}>Reprogramar</button>
                    )}
                    {appt.status === "done" && (
                        <>
                            {appt.medical_record_ids?.length > 0 ? (
                                <button className="btn btn-purple btn-md" style={{width:"100%"}}
                                    onClick={()=>{onClose(); navigate(`/medical-records?record=${appt.medical_record_ids[0]}`); }}>
                                    Ver Consulta
                                </button>
                            ) : canEdit && (
                                <button className="btn btn-purple btn-md" style={{width:"100%"}}
                                    onClick={()=>{onClose(); navigate(`/medical-records?pet=${petId}&appointment=${appt.id}`); }}>
                                    + Crear Consulta Médica
                                </button>
                            )}
                            {appt.invoice_id && (
                                <button className="btn btn-md"
                                    style={{width:"100%",background:"#059669",borderColor:"#059669",color:"#fff"}}
                                    onClick={()=>{onClose(); navigate("/billing"); }}>
                                    Ver Factura
                                </button>
                            )}
                        </>
                    )}
                    <button className="btn btn-secondary btn-md" style={{width:"100%"}} onClick={onClose}>
                        Cerrar
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Edit Modal ─────────────────────────────────────────────────────────────────
function EditModal({ appt, pets, staff, user, onClose, onSave }) {
    const [form, setForm] = useState({
        veterinarian: String(appt.veterinarian || ""),
        date:         appt.date || "",
        start_time:   appt.start_time?.slice(0,5) || "09:00",
        end_time:     appt.end_time?.slice(0,5)   || "10:00",
        reason:       appt.reason || "",
        notes:        appt.notes  || "",
    });
    const [error, setError] = useState("");
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!form.veterinarian) { setError("Selecciona un veterinario"); return; }
        if (!form.date)         { setError("La fecha es obligatoria"); return; }
        if (!form.reason.trim()) { setError("El motivo es obligatorio"); return; }
        setError(""); setSaving(true);
        try { await onSave(form); }
        catch (err) { setError(err.response?.data?.error || "Error al guardar"); }
        finally { setSaving(false); }
    }

    const petName = pets.find(p => p.id === appt.pet)?.name || "—";

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal modal-md" onClick={e=>e.stopPropagation()}>
                <div className="modal-header">
                    <h3>Editar Cita</h3>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>
                <div className="modal-body">
                    {error && <div className="alert alert-danger" style={{marginBottom:"14px"}}>{error}</div>}
                    <div className="form-group">
                        <label className="form-label">MASCOTA</label>
                        <p style={{fontSize:"14px",fontWeight:"600"}}>{petName}</p>
                    </div>
                    <div className="form-group">
                        <label className="form-label">VETERINARIO *</label>
                        <select className="select-input" value={form.veterinarian}
                            onChange={e=>setForm({...form,veterinarian:e.target.value})}
                            disabled={user?.role==="VET"}>
                            <option value="">Seleccionar</option>
                            {staff.map(s=>(
                                <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">FECHA *</label>
                        <input type="date" className="input" value={form.date}
                            onChange={e=>setForm({...form,date:e.target.value})}/>
                    </div>
                    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"14px"}}>
                        <div className="form-group">
                            <label className="form-label">HORA INICIO *</label>
                            <input type="time" className="input" value={form.start_time}
                                onChange={e=>setForm({...form,start_time:e.target.value})}/>
                        </div>
                        <div className="form-group">
                            <label className="form-label">HORA FIN *</label>
                            <input type="time" className="input" value={form.end_time}
                                onChange={e=>setForm({...form,end_time:e.target.value})}/>
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">MOTIVO *</label>
                        <input type="text" className="input" value={form.reason}
                            onChange={e=>setForm({...form,reason:e.target.value})}
                            placeholder="Ej: Vacunación, Revisión general"/>
                    </div>
                    <div className="form-group">
                        <label className="form-label">NOTAS</label>
                        <textarea className="textarea-input" style={{minHeight:"60px"}} value={form.notes}
                            onChange={e=>setForm({...form,notes:e.target.value})}
                            placeholder="Notas adicionales..."/>
                    </div>
                </div>
                <div className="modal-footer">
                    <button className="btn btn-primary btn-md" style={{flex:1}}
                        onClick={handleSave} disabled={saving}>
                        {saving ? "Guardando..." : "Guardar cambios"}
                    </button>
                    <button className="btn btn-secondary btn-md" style={{flex:1}} onClick={onClose}>
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Sidebar Form (new appointment) ─────────────────────────────────────────────
function SidebarForm({ slot, onSave, onClear, pets, staff, user, formRef }) {
    const [petId,  setPetId]  = useState("");
    const [vetId,  setVetId]  = useState(user?.role==="VET" ? String(user.id) : "");
    const [reason, setReason] = useState("");
    const [notes,  setNotes]  = useState("");
    const [hour,   setHour]   = useState(slot?.hour ?? 9);
    const [error,  setError]  = useState("");
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (slot?.hour !== undefined) setHour(slot.hour);
    }, [slot?.hour]);

    useEffect(() => {
        if (user?.role === "VET") setVetId(String(user.id));
    }, [user]);

    async function handleSave() {
        if (!petId)        { setError("Selecciona una mascota"); return; }
        if (!vetId)        { setError("Selecciona un veterinario"); return; }
        if (!reason.trim()){ setError("Ingresa el motivo de la consulta"); return; }
        if (!slot)         { setError("Selecciona un horario en el calendario"); return; }
        setError(""); setSaving(true);
        try {
            await onSave({
                petId, vetId,
                reason: reason.trim(), notes,
                start_time: `${pad(hour)}:00`,
                end_time:   `${pad(Math.min(hour+1,20))}:00`,
            });
            setPetId(""); setReason(""); setNotes("");
            if (user?.role !== "VET") setVetId("");
        } catch (err) {
            setError(err.response?.data?.error || "Error al crear la cita");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div ref={formRef}>
            <p style={{fontSize:"11px",fontWeight:"700",color:"var(--c-text-3)",
                textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:"14px"}}>
                Nueva cita
            </p>

            {slot ? (
                <div style={{
                    background:"var(--c-primary-light)",color:"var(--c-primary-dark)",
                    borderRadius:"var(--r-md)",padding:"7px 10px",fontSize:"12px",fontWeight:"500",
                    marginBottom:"12px",display:"flex",justifyContent:"space-between",alignItems:"center",
                    border:"1px solid #99f6e4",
                }}>
                    <span>{slot.label}</span>
                    <button onClick={onClear} style={{background:"none",border:"none",
                        color:"var(--c-primary-dark)",cursor:"pointer",fontSize:"16px",lineHeight:1,padding:"0 2px"}}>
                        ×
                    </button>
                </div>
            ) : (
                <div style={{
                    background:"var(--c-subtle)",color:"var(--c-text-3)",borderRadius:"var(--r-md)",
                    padding:"7px 10px",fontSize:"12px",marginBottom:"12px",border:"1px solid var(--c-border)",
                }}>
                    Haz clic en una celda del calendario
                </div>
            )}

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle}>Mascota</label>
                <select className="select-input" value={petId}
                    onChange={e=>setPetId(e.target.value)} style={{fontSize:"13px"}}>
                    <option value="">Seleccionar mascota</option>
                    {pets.map(p=>(
                        <option key={p.id} value={p.id}>
                            {p.name}{p.owner?.name ? ` – ${p.owner.name}` : ""}
                        </option>
                    ))}
                </select>
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle}>Veterinario</label>
                <select className="select-input" value={vetId}
                    onChange={e=>setVetId(e.target.value)}
                    disabled={user?.role==="VET"} style={{fontSize:"13px"}}>
                    <option value="">Seleccionar veterinario</option>
                    {staff.map(s=>(
                        <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                    ))}
                </select>
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle}>Motivo</label>
                <input className="input" value={reason} onChange={e=>setReason(e.target.value)}
                    placeholder="Ej: Vacunación, Revisión general" style={{fontSize:"13px"}}/>
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle}>Hora</label>
                <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"4px"}}>
                    {HOURS.map(h=>(
                        <button key={h} type="button" onClick={()=>setHour(h)} style={{
                            padding:"5px 2px",
                            border:`1px solid ${hour===h?"var(--c-primary)":"var(--c-border)"}`,
                            borderRadius:"var(--r-sm)", fontSize:"11px", cursor:"pointer",
                            background:  hour===h?"var(--c-primary)":"var(--c-subtle)",
                            color:       hour===h?"#fff":"var(--c-text-2)",
                            fontFamily:  "inherit", fontWeight: hour===h?"600":"400",
                            transition:  "all var(--t)",
                        }}>
                            {h}:00
                        </button>
                    ))}
                </div>
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle}>Notas (opcional)</label>
                <textarea className="textarea-input" value={notes} onChange={e=>setNotes(e.target.value)}
                    placeholder="Notas adicionales..." style={{minHeight:"50px",fontSize:"13px"}}/>
            </div>

            {error && (
                <div className="alert alert-danger"
                    style={{fontSize:"12.5px",padding:"7px 10px",marginBottom:"10px"}}>
                    {error}
                </div>
            )}

            <button className="btn btn-primary btn-md" style={{width:"100%"}}
                onClick={handleSave} disabled={saving}>
                {saving ? "Guardando..." : "Guardar cita"}
            </button>
        </div>
    );
}

// ── Main Component ─────────────────────────────────────────────────────────────
const Appointments = () => {
    const { token, initializing, user } = useAuth();
    const navigate = useNavigate();
    const formRef  = useRef(null);

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const [appointments, setAppointments] = useState([]);
    const [pets,         setPets]         = useState([]);
    const [staff,        setStaff]        = useState([]);
    const [loading,      setLoading]      = useState(true);

    const [weekOffset,   setWeekOffset]   = useState(0);
    const [selectedSlot, setSelectedSlot] = useState(null);
    const [viewAppt,     setViewAppt]     = useState(null);
    const [editingAppt,  setEditingAppt]  = useState(null);
    const [filterVetId,  setFilterVetId]  = useState("");
    const [success,      setSuccess]      = useState("");

    useEffect(() => {
        if (token) loadAll();
    }, [token]);

    const loadAll = async () => {
        try {
            const [petsData, staffData, apptData] = await Promise.all([
                getPets(token),
                getStaff(token),
                getAppointments(token),
            ]);
            setPets(petsData);
            setStaff(staffData);
            setAppointments(Array.isArray(apptData) ? apptData : (apptData.results || []));
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const loadAppointments = async () => {
        try {
            const data = await getAppointments(token);
            setAppointments(Array.isArray(data) ? data : (data.results || []));
        } catch (err) {
            console.log(err);
        }
    };

    // Vet → palette (assigned by staff index)
    const vetPalMap = {};
    staff.forEach((s, i) => { vetPalMap[s.id] = PAL[PAL_KEYS[i % PAL_KEYS.length]]; });
    const getVetPal = id => vetPalMap[id] || PAL.teal;

    const getPetById   = id => pets.find(p => p.id === id);
    const getStaffById = id => staff.find(s => s.id === id);
    const getVetName   = id => {
        const s = getStaffById(id);
        return s ? `${s.first_name} ${s.last_name}` : null;
    };

    // Week
    const weekStart = getWeekStart(today, weekOffset);
    const weekDays  = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(weekStart); d.setDate(d.getDate() + i); return d;
    });

    // Filtered appointments for this week's grid
    const weekAppts = appointments.filter(a => {
        const d = new Date(a.date + "T00:00:00");
        const inWeek = weekDays.some(wd => isSameDay(d, wd));
        const vetOk  = !filterVetId || String(a.veterinarian) === filterVetId;
        return inWeek && vetOk;
    });

    const apptForCell = (date, hour) => weekAppts.filter(a => {
        const d = new Date(a.date + "T00:00:00");
        return isSameDay(d, date) && apptHour(a) === hour;
    });

    // Stats (always use full unfiltered list)
    const todayCount = appointments.filter(a => {
        const d = new Date(a.date + "T00:00:00");
        return isSameDay(d, today);
    }).length;

    const ws0 = getWeekStart(today, 0);
    const we0 = new Date(ws0); we0.setDate(we0.getDate() + 6);
    const weekCount = appointments.filter(a => {
        const d = new Date(a.date + "T00:00:00");
        return d >= ws0 && d <= we0;
    }).length;

    // Permissions
    const canCreate = user?.role !== "ASSISTANT";
    const canEdit   = user?.role === "ADMIN" || user?.role === "VET";

    // ── Handlers ──────────────────────────────────────────────────────────────
    const handleSlotClick = (date, hour) => {
        if (!canCreate) return;
        const label = `${DAYS_ES[date.getDay()]} ${date.getDate()} ${MONTHS_S[date.getMonth()]} · ${pad(hour)}:00 hs`;
        setSelectedSlot({ date, hour, label });
        setTimeout(() => formRef.current?.scrollIntoView({ behavior:"smooth", block:"nearest" }), 50);
    };

    const handleFormSave = async ({ petId, vetId, reason, notes, start_time, end_time }) => {
        await createAppointment(token, {
            pet:          parseInt(petId),
            veterinarian: parseInt(vetId),
            date:         toDateStr(selectedSlot.date),
            start_time, end_time, reason, notes,
            status: "scheduled",
        });
        window.dispatchEvent(new Event("dashboard:refresh"));
        setSuccess("Cita creada exitosamente");
        setSelectedSlot(null);
        loadAppointments();
        setTimeout(() => setSuccess(""), 3500);
    };

    const handleStatusChange = async (id, status) => {
        try {
            await updateAppointmentStatus(token, id, status);
            window.dispatchEvent(new Event("dashboard:refresh"));
            setViewAppt(null);
            loadAppointments();
            const msg = status==="done"?"Cita completada" : status==="canceled"?"Cita cancelada" : "Cita reprogramada";
            setSuccess(msg);
            setTimeout(() => setSuccess(""), 3500);
        } catch (err) {
            console.log(err);
        }
    };

    const handleEditSave = async (form) => {
        await updateAppointment(token, editingAppt.id, {
            pet:          editingAppt.pet,
            veterinarian: parseInt(form.veterinarian),
            date:         form.date,
            start_time:   form.start_time,
            end_time:     form.end_time,
            reason:       form.reason,
            notes:        form.notes,
            status:       editingAppt.status,
        });
        window.dispatchEvent(new Event("dashboard:refresh"));
        setEditingAppt(null);
        loadAppointments();
        setSuccess("Cita actualizada");
        setTimeout(() => setSuccess(""), 3500);
    };

    const handleMiniSelect = (date) => {
        const ws   = getWeekStart(date, 0);
        const base = getWeekStart(today, 0);
        const diff = Math.round((ws - base) / (7 * 86400000));
        setWeekOffset(diff);
    };

    if (initializing || loading) {
        return (
            <div style={{display:"flex",justifyContent:"center",alignItems:"center",height:"50vh"}}>
                <p style={{color:"var(--c-text-3)",fontSize:"13px"}}>Cargando...</p>
            </div>
        );
    }

    return (
        <div>
            <style>{`
                .apt-slot:hover { background: var(--c-primary-light) !important; }
                .apt-slot:hover .apt-hint { opacity: 1 !important; }
                .apt-body::-webkit-scrollbar { width: 4px; }
                .apt-body::-webkit-scrollbar-thumb { background: var(--c-border-2); border-radius: 4px; }
            `}</style>

            {success && (
                <div className="alert alert-success" style={{marginBottom:"16px"}}>
                    {success}
                    <button className="alert-close" onClick={()=>setSuccess("")}>✕</button>
                </div>
            )}

            {/* Page header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Citas</h1>
                    <p className="page-subtitle">{weekTitle(weekStart)}</p>
                </div>
            </div>

            {/* Main grid: calendar + sidebar */}
            <div style={{display:"grid",gridTemplateColumns:"1fr 296px",gap:"16px",alignItems:"start"}}>

                {/* ── Calendar panel ── */}
                <div style={{
                    background:"var(--c-surface)",border:"1px solid var(--c-border)",
                    borderRadius:"var(--r-xl)",overflow:"hidden",boxShadow:"var(--shadow-sm)",
                }}>
                    {/* Header */}
                    <div style={{
                        display:"flex",alignItems:"center",justifyContent:"space-between",
                        padding:"14px 20px",borderBottom:"1px solid var(--c-border)",
                    }}>
                        <span style={{fontSize:"15px",fontWeight:"700",color:"var(--c-text)"}}>
                            {weekTitle(weekStart)}
                        </span>
                        <div style={{display:"flex",gap:"6px",alignItems:"center"}}>
                            <button style={calNavBtn} onClick={()=>setWeekOffset(o=>o-1)}>‹</button>
                            <button style={{...calNavBtn,fontSize:"12px",padding:"5px 10px"}}
                                onClick={()=>setWeekOffset(0)}>Hoy</button>
                            <button style={calNavBtn} onClick={()=>setWeekOffset(o=>o+1)}>›</button>
                        </div>
                    </div>

                    {/* Day labels */}
                    <div style={{
                        display:"grid",gridTemplateColumns:"52px repeat(7,1fr)",
                        borderBottom:"1px solid var(--c-border)",
                    }}>
                        <div />
                        {weekDays.map((d, i) => {
                            const isToday = isSameDay(d, today);
                            return (
                                <div key={i} style={{textAlign:"center",padding:"10px 4px",
                                    borderLeft:"1px solid var(--c-border)"}}>
                                    <div style={{fontSize:"10px",fontWeight:"600",textTransform:"uppercase",
                                        letterSpacing:"0.07em",
                                        color: isToday?"var(--c-primary)":"var(--c-text-3)"}}>
                                        {DAYS_ES[d.getDay()]}
                                    </div>
                                    <div style={{fontSize:"15px",marginTop:"2px",
                                        fontWeight: isToday?"700":"400",
                                        color: isToday?"var(--c-primary)":"var(--c-text)"}}>
                                        {d.getDate()}
                                    </div>
                                    {isToday && (
                                        <div style={{width:"5px",height:"5px",borderRadius:"50%",
                                            background:"var(--c-primary)",margin:"3px auto 0"}}/>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Time grid */}
                    <div className="apt-body" style={{overflowY:"auto",maxHeight:"490px"}}>
                        {HOURS.map(hour => (
                            <div key={hour} style={{display:"grid",gridTemplateColumns:"52px repeat(7,1fr)"}}>
                                <div style={{display:"flex",alignItems:"flex-start",justifyContent:"flex-end",
                                    paddingTop:"6px",paddingRight:"8px"}}>
                                    <span style={{fontSize:"11px",color:"var(--c-text-3)",
                                        fontVariantNumeric:"tabular-nums",whiteSpace:"nowrap"}}>
                                        {hour}:00
                                    </span>
                                </div>
                                {weekDays.map((date, di) => {
                                    const cellAppts = apptForCell(date, hour);
                                    const isToday   = isSameDay(date, today);
                                    return (
                                        <div key={di}
                                            className="apt-slot"
                                            onClick={()=>handleSlotClick(date, hour)}
                                            style={{
                                                borderTop:"1px solid var(--c-border)",
                                                borderLeft:"1px solid var(--c-border)",
                                                minHeight:"56px", position:"relative",
                                                cursor: canCreate?"pointer":"default",
                                                background: isToday?"rgba(45,212,191,0.03)":"transparent",
                                                transition:"background 0.12s",
                                            }}
                                        >
                                            {cellAppts.length === 0 && canCreate && (
                                                <span className="apt-hint" style={{
                                                    position:"absolute",top:"50%",left:"50%",
                                                    transform:"translate(-50%,-50%)",
                                                    fontSize:"11px",color:"var(--c-primary)",
                                                    opacity:0,whiteSpace:"nowrap",pointerEvents:"none",
                                                    fontWeight:"500",transition:"opacity 0.12s",
                                                }}>
                                                    + Agendar
                                                </span>
                                            )}
                                            {cellAppts.map(a => {
                                                const pet = getPetById(a.pet);
                                                return (
                                                    <ApptBadge
                                                        key={a.id}
                                                        appt={a}
                                                        pal={getVetPal(a.veterinarian)}
                                                        petName={pet?.name || "—"}
                                                        ownerName={pet?.owner?.name || ""}
                                                        onClick={setViewAppt}
                                                    />
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                </div>

                {/* ── Sidebar ── */}
                <div style={{display:"flex",flexDirection:"column",gap:"14px"}}>

                    {/* Mini calendar + vet filter */}
                    <div style={{
                        background:"var(--c-surface)",border:"1px solid var(--c-border)",
                        borderRadius:"var(--r-xl)",padding:"18px 20px",boxShadow:"var(--shadow-sm)",
                    }}>
                        <MiniCalendar
                            today={today}
                            selectedDate={selectedSlot?.date}
                            onSelect={handleMiniSelect}
                        />

                        <div style={{borderTop:"1px solid var(--c-border)",marginTop:"14px",paddingTop:"14px"}}>
                            <p style={{fontSize:"11px",fontWeight:"700",color:"var(--c-text-3)",
                                textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:"10px"}}>
                                Veterinarios
                            </p>
                            <div style={{display:"flex",flexWrap:"wrap",gap:"5px"}}>
                                {/* All chip */}
                                <div onClick={()=>setFilterVetId("")} style={{
                                    display:"inline-flex",alignItems:"center",gap:"5px",
                                    padding:"3px 9px",borderRadius:"var(--r-full)",cursor:"pointer",
                                    background: filterVetId===""?"var(--c-primary)":"var(--c-subtle)",
                                    color:      filterVetId===""?"#fff":"var(--c-text-2)",
                                    fontSize:"11px",fontWeight:"500",transition:"all 0.15s",
                                    border: filterVetId===""?"1px solid var(--c-primary)":"1px solid var(--c-border)",
                                }}>
                                    Todos
                                </div>
                                {staff.map((s, i) => {
                                    const c = PAL[PAL_KEYS[i % PAL_KEYS.length]];
                                    const isActive = filterVetId === String(s.id);
                                    return (
                                        <div key={s.id}
                                            onClick={()=>setFilterVetId(f=>f===String(s.id)?"":String(s.id))}
                                            style={{
                                                display:"inline-flex",alignItems:"center",gap:"5px",
                                                padding:"3px 9px",borderRadius:"var(--r-full)",cursor:"pointer",
                                                background: isActive?c.border:c.bg,
                                                color:      isActive?"#fff":c.text,
                                                fontSize:"11px",fontWeight:"500",transition:"all 0.15s",
                                            }}
                                        >
                                            <span style={{width:"6px",height:"6px",borderRadius:"50%",flexShrink:0,
                                                background: isActive?"#fff":c.border}}/>
                                            {s.first_name} {s.last_name}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    {/* New appointment form */}
                    <div style={{
                        background:"var(--c-surface)",border:"1px solid var(--c-border)",
                        borderRadius:"var(--r-xl)",padding:"18px 20px",boxShadow:"var(--shadow-sm)",
                    }}>
                        {canCreate ? (
                            <SidebarForm
                                slot={selectedSlot}
                                onSave={handleFormSave}
                                onClear={()=>setSelectedSlot(null)}
                                pets={pets}
                                staff={staff}
                                user={user}
                                formRef={formRef}
                            />
                        ) : (
                            <p style={{fontSize:"12.5px",color:"var(--c-text-3)",
                                fontStyle:"italic",textAlign:"center"}}>
                                Modo lectura — sin permiso para crear citas
                            </p>
                        )}
                    </div>

                    {/* Stats */}
                    <div style={{
                        background:"var(--c-primary-light)", border:"1px solid #99f6e4",
                        borderRadius:"var(--r-xl)", padding:"14px 18px",
                        display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px",
                    }}>
                        {[["Hoy", todayCount], ["Esta semana", weekCount]].map(([label,count])=>(
                            <div key={label}>
                                <div style={{fontSize:"11px",color:"var(--c-primary-dark)",marginBottom:"2px"}}>
                                    {label}
                                </div>
                                <div style={{fontSize:"26px",fontWeight:"700",color:"var(--c-primary-dark)",lineHeight:1}}>
                                    {count}
                                </div>
                                <div style={{fontSize:"11px",color:"var(--c-primary-dark)",opacity:0.7,marginTop:"2px"}}>
                                    cita{count!==1?"s":""}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Detail Modal */}
            {viewAppt && (
                <DetailModal
                    appt={viewAppt}
                    petName={getPetById(viewAppt.pet)?.name || "—"}
                    vetName={getVetName(viewAppt.veterinarian) || viewAppt.veterinarian_name}
                    petId={viewAppt.pet}
                    onClose={()=>setViewAppt(null)}
                    onStatusChange={handleStatusChange}
                    onEdit={appt=>{ setEditingAppt(appt); setViewAppt(null); }}
                    navigate={navigate}
                    canEdit={canEdit}
                />
            )}

            {/* Edit Modal */}
            {editingAppt && (
                <EditModal
                    appt={editingAppt}
                    pets={pets}
                    staff={staff}
                    user={user}
                    onClose={()=>setEditingAppt(null)}
                    onSave={handleEditSave}
                />
            )}
        </div>
    );
};

export default Appointments;
