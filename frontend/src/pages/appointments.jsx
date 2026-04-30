import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useConfirm } from "../components/ConfirmDialog";
import { toast } from "sonner";
import {
    getAppointments, createAppointment,
    updateAppointment, updateAppointmentStatus, walkInAppointment,
    getAppointmentHistory, assignPatient, createAppointmentWithPatient,
} from "../api/appointments";
import { getOrgSettings } from "../api/organizations";
import { getPets } from "../api/pets";
import { getStaff } from "../api/staff";
import SearchSelect from "../components/SearchSelect";
import QuickPatientForm from "../components/QuickPatientForm";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";

import { apiError } from "../utils/apiError";

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

const S_BADGE = {
    scheduled:   "badge-info",
    confirmed:   "badge-purple",
    in_progress: "badge-warning",
    done:        "badge-success",
    canceled:    "badge-danger",
    no_show:     "badge-secondary",
};
const S_LABEL = {
    scheduled:   "Programada",
    confirmed:   "Confirmada",
    in_progress: "En consulta",
    done:        "Completada",
    canceled:    "Cancelada",
    no_show:     "No se presentó",
};

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

// ── localTodayStr ──────────────────────────────────────────────────────────────
function localTodayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

// ── Detail Modal ───────────────────────────────────────────────────────────────
function DetailModal({ appt, petName, vetName, petId, onClose, onStatusChange, onEdit, onNewFromAppt, navigate, canEdit, showHistory, onRefresh }) {
    const confirm = useConfirm();
    const [history,          setHistory]          = useState([]);
    const [historyOpen,      setHistoryOpen]      = useState(false);
    const [loadingHist,      setLoadingHist]      = useState(false);
    const [assigningPatient, setAssigningPatient] = useState(false);
    const [newPetItem,       setNewPetItem]       = useState(null);
    const [savingAssign,     setSavingAssign]     = useState(false);

    const canReschedule = appt.status === "canceled" && appt.date >= localTodayStr();
    const showNewAppt   = (appt.status === "canceled" && appt.date < localTodayStr()) || appt.status === "no_show";

    const toggleHistory = async () => {
        if (!historyOpen && history.length === 0) {
            setLoadingHist(true);
            try {
                const data = await getAppointmentHistory(appt.id);
                setHistory(data);
            } catch {
                // silenciar — historial no crítico
            } finally {
                setLoadingHist(false);
            }
        }
        setHistoryOpen(prev => !prev);
    };

    const handleAssign = async () => {
        if (!newPetItem) { toast.error("Selecciona una mascota"); return; }
        setSavingAssign(true);
        try {
            const updated = await assignPatient(appt.id, newPetItem.id);
            onRefresh(updated);
            setAssigningPatient(false);
            setNewPetItem(null);
            toast.success("Paciente vinculado correctamente");
        } catch (err) {
            toast.error(apiError(err, "Error al vincular paciente"));
        } finally {
            setSavingAssign(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal modal-md" onClick={e=>e.stopPropagation()}>
                <div className="modal-header">
                    <div>
                        <h3 style={{marginBottom:"5px"}}>{petName || "—"}</h3>
                        <span className={`badge ${S_BADGE[appt.status] || "badge-info"}`}>
                            {S_LABEL[appt.status] || appt.status}
                        </span>
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
                    {appt.cancellation_reason && (
                        <div style={{marginTop:"8px",padding:"8px 12px",background:"#fef2f2",
                            borderRadius:"var(--r-md)",fontSize:"12px",color:"#991b1b",borderLeft:"3px solid #f87171"}}>
                            <strong>Motivo cancelación:</strong> {appt.cancellation_reason}
                        </div>
                    )}

                    {/* Banner: paciente genérico — vincular a real */}
                    {appt.pet_is_generic && canEdit && (
                        <div style={{
                            marginTop:"12px", padding:"12px 14px",
                            background:"#fffbeb", border:"1px solid #fbbf24",
                            borderRadius:"var(--r-md)",
                        }}>
                            <p style={{fontSize:"12.5px",fontWeight:"600",color:"#92400e",marginBottom:"8px"}}>
                                Paciente anónimo — vincular a paciente real
                            </p>
                            {appt.status === 'done' ? (
                                <p style={{fontSize:"12px",color:"#b45309"}}>
                                    La consulta ya fue completada. El paciente no puede reasignarse.
                                </p>
                            ) : assigningPatient ? (
                                <div>
                                    <SearchSelect
                                        value={newPetItem}
                                        onChange={item => setNewPetItem(item)}
                                        onSearch={q => getPets({ search: q }).then(ps =>
                                            ps.filter(p => !p.is_generic)
                                               .map(p => ({ id: p.id, label: `${p.name} – ${(p.owner?.name ?? "").trim()}`.trim().replace(/ – $/, "") }))
                                        )}
                                        placeholder="Buscar mascota..."
                                    />
                                    <div style={{display:"flex",gap:"6px",marginTop:"8px"}}>
                                        <button className="btn btn-primary btn-sm"
                                            disabled={!newPetItem || savingAssign}
                                            onClick={handleAssign}>
                                            {savingAssign ? "Guardando..." : "Vincular"}
                                        </button>
                                        <button className="btn btn-secondary btn-sm"
                                            onClick={() => { setAssigningPatient(false); setNewPetItem(null); }}>
                                            Cancelar
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <button className="btn btn-secondary btn-sm"
                                    onClick={() => setAssigningPatient(true)}>
                                    Vincular paciente
                                </button>
                            )}
                        </div>
                    )}

                    {/* Historial de estados — solo si el toggle está activo */}
                    {showHistory && (
                        <div style={{marginTop:"12px"}}>
                            <button
                                type="button"
                                onClick={toggleHistory}
                                style={{
                                    display:"flex",alignItems:"center",gap:"6px",
                                    background:"none",border:"none",cursor:"pointer",
                                    fontSize:"12px",fontWeight:"600",color:"var(--c-text-2)",padding:"0",
                                }}
                            >
                                <span style={{fontSize:"10px"}}>{historyOpen ? "▼" : "▶"}</span>
                                Historial de estados
                            </button>
                            {historyOpen && (
                                <div style={{marginTop:"8px",borderLeft:"2px solid var(--c-border)",paddingLeft:"12px"}}>
                                    {loadingHist ? (
                                        <p style={{fontSize:"12px",color:"var(--c-text-3)"}}>Cargando...</p>
                                    ) : history.length === 0 ? (
                                        <p style={{fontSize:"12px",color:"var(--c-text-3)"}}>Sin cambios registrados.</p>
                                    ) : history.map(h => (
                                        <div key={h.id} style={{marginBottom:"8px"}}>
                                            <div style={{display:"flex",alignItems:"center",gap:"6px",fontSize:"12.5px"}}>
                                                <span className={`badge ${S_BADGE[h.from_status] || "badge-default"}`} style={{fontSize:"10px"}}>
                                                    {h.from_status_display || h.from_status}
                                                </span>
                                                <span style={{color:"var(--c-text-3)"}}>→</span>
                                                <span className={`badge ${S_BADGE[h.to_status] || "badge-default"}`} style={{fontSize:"10px"}}>
                                                    {h.to_status_display || h.to_status}
                                                </span>
                                            </div>
                                            <p style={{fontSize:"11px",color:"var(--c-text-3)",marginTop:"2px"}}>
                                                {h.changed_by_name || "—"} · {h.created_at ? new Date(h.created_at).toLocaleString("es-MX",{dateStyle:"short",timeStyle:"short"}) : ""}
                                            </p>
                                            {h.reason && (
                                                <p style={{fontSize:"11px",color:"var(--c-text-3)",fontStyle:"italic"}}>{h.reason}</p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
                <div className="modal-footer" style={{flexDirection:"column",gap:"8px"}}>

                    {/* scheduled → confirm / start / no_show / cancel */}
                    {appt.status === "scheduled" && canEdit && (
                        <>
                            <div style={{display:"flex",gap:"6px",width:"100%"}}>
                                <button className="btn btn-info btn-md" style={{flex:1}}
                                    onClick={()=>onEdit(appt)}>Editar</button>
                                <button className="btn btn-purple btn-md" style={{flex:1}}
                                    onClick={()=>onStatusChange(appt.id,"confirmed")}>Confirmar</button>
                                <button className="btn btn-md" style={{flex:1,background:"#f59e0b",borderColor:"#f59e0b",color:"#fff"}}
                                    onClick={()=>onStatusChange(appt.id,"in_progress")}>Iniciar</button>
                            </div>
                            <div style={{display:"flex",gap:"6px",width:"100%"}}>
                                <button className="btn btn-secondary btn-md" style={{flex:1}}
                                    onClick={async ()=>{
                                        if(await confirm({ message:"¿Marcar como no presentado?", confirmText:"No se presentó" }))
                                            onStatusChange(appt.id,"no_show");
                                    }}>No se presentó</button>
                                <button className="btn btn-danger btn-md" style={{flex:1}}
                                    onClick={async ()=>{
                                        if(await confirm({ message:"¿Cancelar esta cita?", confirmText:"Cancelar cita", dangerMode:true }))
                                            onStatusChange(appt.id,"canceled");
                                    }}>Cancelar</button>
                            </div>
                        </>
                    )}

                    {/* confirmed → start / no_show / cancel */}
                    {appt.status === "confirmed" && canEdit && (
                        <>
                            <button className="btn btn-md btn-md" style={{width:"100%",background:"#f59e0b",borderColor:"#f59e0b",color:"#fff"}}
                                onClick={()=>onStatusChange(appt.id,"in_progress")}>Iniciar consulta</button>
                            <div style={{display:"flex",gap:"6px",width:"100%"}}>
                                <button className="btn btn-secondary btn-md" style={{flex:1}}
                                    onClick={async ()=>{
                                        if(await confirm({ message:"¿Marcar como no presentado?", confirmText:"No se presentó" }))
                                            onStatusChange(appt.id,"no_show");
                                    }}>No se presentó</button>
                                <button className="btn btn-danger btn-md" style={{flex:1}}
                                    onClick={async ()=>{
                                        if(await confirm({ message:"¿Cancelar esta cita?", confirmText:"Cancelar cita", dangerMode:true }))
                                            onStatusChange(appt.id,"canceled");
                                    }}>Cancelar</button>
                            </div>
                        </>
                    )}

                    {/* in_progress → done / cancel */}
                    {appt.status === "in_progress" && canEdit && (
                        <div style={{display:"flex",gap:"6px",width:"100%"}}>
                            <button className="btn btn-md" style={{flex:2,background:"#22c55e",borderColor:"#22c55e",color:"#fff"}}
                                onClick={()=>onStatusChange(appt.id,"done")}>Completar consulta</button>
                            <button className="btn btn-danger btn-md" style={{flex:1}}
                                onClick={async ()=>{
                                    if(await confirm({ message:"¿Cancelar esta consulta en progreso?", confirmText:"Cancelar", dangerMode:true }))
                                        onStatusChange(appt.id,"canceled");
                                }}>Cancelar</button>
                        </div>
                    )}

                    {/* done → medical record / invoice */}
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

                    {/* canceled → reschedule (if date still valid) or new appt */}
                    {canReschedule && canEdit && (
                        <button className="btn btn-info btn-md" style={{width:"100%"}}
                            onClick={()=>onStatusChange(appt.id,"scheduled")}>Reprogramar</button>
                    )}
                    {showNewAppt && canEdit && (
                        <button className="btn btn-info btn-md" style={{width:"100%"}}
                            onClick={()=>{ onClose(); onNewFromAppt(appt); }}>
                            + Crear nueva cita
                        </button>
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
function EditModal({ appt, staff, user, onClose, onSave }) {
    const [form, setForm] = useState({
        veterinarian: String(appt.veterinarian || ""),
        date:         appt.date || "",
        start_time:   appt.start_time?.slice(0,5) || "09:00",
        end_time:     appt.end_time?.slice(0,5)   || "10:00",
        reason:       appt.reason || "",
        notes:        appt.notes  || "",
    });
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!form.veterinarian) { toast.error("Selecciona un veterinario"); return; }
        if (!form.date)         { toast.error("La fecha es obligatoria"); return; }
        if (!form.reason.trim()) { toast.error("El motivo es obligatorio"); return; }
        setSaving(true);
        try {
            await toast.promise(onSave(form), {
                loading: 'Guardando cambios...',
                success: 'Cita actualizada',
                error: (err) => apiError(err, "Error al guardar")
            });
        } catch (err) {
        } finally { setSaving(false); }
    }

    const petName = appt.pet_name || "—";

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal modal-md" onClick={e=>e.stopPropagation()}>
                <div className="modal-header">
                    <h3>Editar Cita</h3>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>
                <div className="modal-body">
                    <div className="form-group">
                        <label className="form-label" htmlFor="edit-appt-pet">MASCOTA</label>
                        <input id="edit-appt-pet" name="edit-appt-pet" value={petName} readOnly className="input" />
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="edit-appt-vet">VETERINARIO *</label>
                        <select id="edit-appt-vet" name="edit-appt-vet" className="select-input" value={form.veterinarian}
                            onChange={e=>setForm({...form,veterinarian:e.target.value})}
                            disabled={user?.role==="VET"}>
                            <option value="">Seleccionar</option>
                            {staff.map(s=>(
                                <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="edit-appt-date">FECHA *</label>
                        <input id="edit-appt-date" name="edit-appt-date" type="date" className="input" value={form.date}
                            min={localTodayStr()}
                            onChange={e=>setForm({...form,date:e.target.value})}/>
                    </div>
                    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"14px"}}>
                        <div className="form-group">
                            <label className="form-label" htmlFor="edit-appt-start">HORA INICIO *</label>
                            <input id="edit-appt-start" name="edit-appt-start" type="time" className="input" value={form.start_time}
                                onChange={e=>setForm({...form,start_time:e.target.value})}/>
                        </div>
                        <div className="form-group">
                            <label className="form-label" htmlFor="edit-appt-end">HORA FIN *</label>
                            <input id="edit-appt-end" name="edit-appt-end" type="time" className="input" value={form.end_time}
                                onChange={e=>setForm({...form,end_time:e.target.value})}/>
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="edit-appt-reason">MOTIVO *</label>
                        <input id="edit-appt-reason" name="edit-appt-reason" type="text" className="input" value={form.reason}
                            onChange={e=>setForm({...form,reason:e.target.value})}
                            placeholder="Ej: Vacunación, Revisión general"/>
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="edit-appt-notes">NOTAS</label>
                        <textarea id="edit-appt-notes" name="edit-appt-notes" className="textarea-input" style={{minHeight:"60px"}} value={form.notes}
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
const EMPTY_QUICK = { ownerName: '', ownerPhone: '', petName: '', species: '', sex: 'unknown', birthDate: '' };

function SidebarForm({ slot, onSave, onSaveWithPatient, onClear, staff, user, formRef }) {
    const [petItem,          setPetItem]          = useState(null);
    const [vetId,            setVetId]            = useState(user?.role==="VET" ? String(user.id) : "");
    const [reason,           setReason]           = useState("");
    const [notes,            setNotes]            = useState("");
    const [hour,             setHour]             = useState(slot?.hour ?? 9);
    const [saving,           setSaving]           = useState(false);
    const [showQuickPatient, setShowQuickPatient] = useState(false);
    const [quickPatient,     setQuickPatient]     = useState(EMPTY_QUICK);
    const warnedPastRef = useRef(false);

    useEffect(() => {
        if (slot?.hour !== undefined) setHour(slot.hour);
    }, [slot?.hour]);

    useEffect(() => {
        if (!slot) { warnedPastRef.current = false; return; }
        const isPast = toDateStr(slot.date) < localTodayStr();
        if (isPast && !warnedPastRef.current) {
            warnedPastRef.current = true;
            toast.error("No puedes crear una cita pasada. Revisa la fecha o cambia el estado a 'Completada'.");
        }
        if (!isPast) warnedPastRef.current = false;
    }, [slot]);

    useEffect(() => {
        if (user?.role === "VET") setVetId(String(user.id));
    }, [user]);

    async function handleSave() {
        if (!petItem && !showQuickPatient) { toast.error("Selecciona una mascota"); return; }
        if (!vetId)         { toast.error("Selecciona un veterinario"); return; }
        if (!reason.trim()) { toast.error("Ingresa el motivo de la consulta"); return; }
        if (!slot)          { toast.error("Selecciona un horario en el calendario"); return; }

        if (showQuickPatient) {
            if (!quickPatient.ownerName.trim())            { toast.error("Nombre del dueño requerido"); return; }
            if (!/^\d{10}$/.test(quickPatient.ownerPhone)) { toast.error("Teléfono del dueño: 10 dígitos"); return; }
            if (!quickPatient.petName.trim())              { toast.error("Nombre de la mascota requerido"); return; }
            if (!quickPatient.species)                     { toast.error("Especie requerida"); return; }

            setSaving(true);
            try {
                await toast.promise(onSaveWithPatient({
                    owner_name:     quickPatient.ownerName.trim(),
                    owner_phone:    quickPatient.ownerPhone,
                    pet_name:       quickPatient.petName.trim(),
                    pet_species:    quickPatient.species,
                    pet_sex:        quickPatient.sex,
                    pet_birth_date: quickPatient.birthDate || null,
                    veterinarian:   parseInt(vetId),
                    date:           toDateStr(slot.date),
                    start_time:     `${pad(hour)}:00`,
                    end_time:       hour < 20 ? `${pad(hour)}:30` : '20:00',
                    reason:         reason.trim(),
                    notes,
                }), {
                    loading: 'Guardando cita...',
                    success: 'Cita creada exitosamente',
                    error: (err) => apiError(err, "Error al crear la cita"),
                });
                setPetItem(null); setReason(""); setNotes("");
                setShowQuickPatient(false); setQuickPatient(EMPTY_QUICK);
                if (user?.role !== "VET") setVetId("");
            } catch (err) {
            } finally {
                setSaving(false);
            }
        } else {
            setSaving(true);
            try {
                await toast.promise(onSave({
                    petId: petItem.id, vetId,
                    reason: reason.trim(), notes,
                    start_time: `${pad(hour)}:00`,
                    end_time:   hour < 20 ? `${pad(hour)}:30` : `20:00`,
                }), {
                    loading: 'Guardando cita...',
                    success: 'Cita creada exitosamente',
                    error: (err) => apiError(err, "Error al crear la cita"),
                });
                setPetItem(null); setReason(""); setNotes("");
                if (user?.role !== "VET") setVetId("");
            } catch (err) {
            } finally {
                setSaving(false);
            }
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
                {!showQuickPatient ? (
                    <>
                        <SearchSelect
                            id="new-appt-pet"
                            name="new-appt-pet"
                            value={petItem}
                            onChange={item => setPetItem(item)}
                            onSearch={q => getPets({ search: q }).then(ps =>
                                ps.map(p => ({ id: p.id, label: `${p.name} – ${(p.owner?.name ?? "").trim()}`.trim().replace(/ – $/, "") }))
                            )}
                            placeholder="Buscar mascota..."
                            disabled={saving}
                        />
                        <button
                            type="button"
                            onClick={() => setShowQuickPatient(true)}
                            disabled={saving}
                            style={{
                                background:"none",border:"none",cursor:"pointer",padding:"4px 0 0",
                                fontSize:"11px",color:"var(--c-text-3)",display:"block",
                            }}
                        >
                            No encuentro la mascota →
                        </button>
                    </>
                ) : (
                    <QuickPatientForm
                        value={quickPatient}
                        onChange={setQuickPatient}
                        onCancel={() => { setShowQuickPatient(false); setQuickPatient(EMPTY_QUICK); }}
                        disabled={saving}
                    />
                )}
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle} htmlFor="new-appt-vet">Veterinario</label>
                <select id="new-appt-vet" name="new-appt-vet" className="select-input" value={vetId}
                    onChange={e=>setVetId(e.target.value)}
                    disabled={user?.role==="VET"} style={{fontSize:"13px"}}>
                    <option value="">Seleccionar veterinario</option>
                    {staff.map(s=>(
                        <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                    ))}
                </select>
            </div>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle} htmlFor="new-appt-reason">Motivo</label>
                <input id="new-appt-reason" name="new-appt-reason" className="input" value={reason} onChange={e=>setReason(e.target.value)}
                    placeholder="Ej: Vacunación, Revisión general" style={{fontSize:"13px"}}/>
            </div>

            <fieldset style={{marginBottom:"10px", border:"none", padding:0, marginInline:0}}>
                <legend style={lblStyle}>Hora</legend>
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
            </fieldset>

            <div style={{marginBottom:"10px"}}>
                <label style={lblStyle} htmlFor="new-appt-notes">Notas (opcional)</label>
                <textarea id="new-appt-notes" name="new-appt-notes" className="textarea-input" value={notes} onChange={e=>setNotes(e.target.value)}
                    placeholder="Notas adicionales..." style={{minHeight:"50px",fontSize:"13px"}}/>
            </div>

            <button className="btn btn-primary btn-md" style={{width:"100%"}}
                onClick={handleSave} disabled={saving}>
                {saving ? "Guardando..." : "Guardar cita"}
            </button>
        </div>
    );
}

// ── WalkIn Modal ───────────────────────────────────────────────────────────────
function WalkInModal({ staff, user, onClose, onSave, allowAnonymousWalkIn }) {
    const [petItem, setPetItem] = useState(null);
    const [vetId,  setVetId]  = useState(user?.role === "VET" ? String(user.id) : "");
    const [reason, setReason] = useState("");
    const [notes,  setNotes]  = useState("");
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!petItem && !allowAnonymousWalkIn) { toast.error("Selecciona una mascota"); return; }
        if (!vetId)         { toast.error("Selecciona un veterinario"); return; }
        if (!reason.trim()) { toast.error("El motivo es obligatorio"); return; }
        setSaving(true);
        try {
            const payload = {
                veterinarian: parseInt(vetId),
                reason: reason.trim(),
                notes,
            };
            if (petItem) payload.pet = petItem.id;

            await toast.promise(onSave(payload), {
                loading: 'Registrando walk-in...',
                success: 'Walk-in registrado — consulta en progreso',
                error: (err) => apiError(err, "Error al registrar walk-in")
            });
        } catch (err) {
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal modal-md" onClick={e=>e.stopPropagation()}>
                <div className="modal-header">
                    <div>
                        <h3 style={{marginBottom:"4px"}}>Walk-in</h3>
                        <p style={{fontSize:"12px",color:"var(--c-text-3)",margin:0}}>
                            Consulta inmediata — la cita se crea en estado "En consulta"
                        </p>
                    </div>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>
                <div className="modal-body">
                    <div className="form-group">
                        <label className="form-label" htmlFor="walkin-pet">MASCOTA {allowAnonymousWalkIn ? "(opcional)" : "*"}</label>
                        <SearchSelect
                            id="walkin-pet"
                            name="walkin-pet"
                            value={petItem}
                            onChange={item => setPetItem(item)}
                            onSearch={q => getPets({ search: q }).then(ps =>
                                ps.map(p => ({ id: p.id, label: `${p.name} – ${(p.owner?.name ?? "").trim()}`.trim().replace(/ – $/, "") }))
                            )}
                            placeholder="Buscar mascota..."
                        />
                        {allowAnonymousWalkIn && (
                            <p style={{ fontSize: "11px", color: "var(--c-text-3)", marginTop: "5px" }}>
                                Si lo dejas vacío, se registrará como paciente anónimo.
                            </p>
                        )}
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="walkin-vet">VETERINARIO *</label>
                        <select id="walkin-vet" name="walkin-vet" className="select-input" value={vetId}
                            onChange={e=>setVetId(e.target.value)}
                            disabled={user?.role === "VET"}>
                            <option value="">Seleccionar veterinario</option>
                            {staff.map(s=>(
                                <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="walkin-reason">MOTIVO *</label>
                        <input id="walkin-reason" name="walkin-reason" className="input" value={reason} onChange={e=>setReason(e.target.value)}
                            placeholder="Ej: Revisión de urgencia, Vacunación"/>
                    </div>
                    <div className="form-group">
                        <label className="form-label" htmlFor="walkin-notes">NOTAS</label>
                        <textarea id="walkin-notes" name="walkin-notes" className="textarea-input" style={{minHeight:"56px"}} value={notes}
                            onChange={e=>setNotes(e.target.value)} placeholder="Observaciones adicionales..."/>
                    </div>
                </div>
                <div className="modal-footer">
                    <button className="btn btn-primary btn-md" style={{flex:1}}
                        onClick={handleSave} disabled={saving}>
                        {saving ? "Registrando..." : "Iniciar consulta"}
                    </button>
                    <button className="btn btn-secondary btn-md" style={{flex:1}} onClick={onClose}>
                        Cancelar
                    </button>
                </div>
            </div>
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
    const [staff,        setStaff]        = useState([]);
    const [loading,      setLoading]      = useState(true);

    const [weekOffset,   setWeekOffset]   = useState(0);
    const [selectedSlot, setSelectedSlot] = useState(null);
    const [viewAppt,     setViewAppt]     = useState(null);
    const [editingAppt,  setEditingAppt]  = useState(null);
    const [walkInOpen,   setWalkInOpen]   = useState(false);
    const [newFromAppt,  setNewFromAppt]  = useState(null);
    const [filterVetId,  setFilterVetId]  = useState("");
    const [orgSettings,  setOrgSettings]  = useState(null);

    useEffect(() => {
        if (token) {
            loadAll();
            getOrgSettings().then(setOrgSettings).catch(() => {});
        }
    }, [token]);

    const loadAll = async () => {
        try {
            const [staffData, apptData] = await Promise.all([
                getStaff(token),
                getAppointments(token),
            ]);
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
        const d = (() => { const [y,m,d] = a.date.split('-').map(Number); return new Date(y,m-1,d); })();
        const inWeek = weekDays.some(wd => isSameDay(d, wd));
        const vetOk  = !filterVetId || String(a.veterinarian) === filterVetId;
        return inWeek && vetOk;
    });

    const apptForCell = (date, hour) => weekAppts.filter(a => {
        const d = (() => { const [y,m,d] = a.date.split('-').map(Number); return new Date(y,m-1,d); })();
        return isSameDay(d, date) && apptHour(a) === hour;
    });

    // Stats (always use full unfiltered list)
    const todayCount = appointments.filter(a => {
        const d = (() => { const [y,m,d] = a.date.split('-').map(Number); return new Date(y,m-1,d); })();
        return isSameDay(d, today);
    }).length;

    const ws0 = getWeekStart(today, 0);
    const we0 = new Date(ws0); we0.setDate(we0.getDate() + 6);
    const weekCount = appointments.filter(a => {
        const d = (() => { const [y,m,d] = a.date.split('-').map(Number); return new Date(y,m-1,d); })();
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
        setSelectedSlot(null);
        loadAppointments();
    };

    const handleSaveWithPatient = async (data) => {
        await createAppointmentWithPatient(data);
        window.dispatchEvent(new Event("dashboard:refresh"));
        setSelectedSlot(null);
        loadAppointments();
    };

    const STATUS_MSG = {
        confirmed:   "Cita confirmada",
        in_progress: "Consulta iniciada",
        done:        "Consulta completada",
        canceled:    "Cita cancelada",
        no_show:     "Marcada como no presentado",
        scheduled:   "Cita reprogramada",
    };

    const handleStatusChange = async (id, newStatus) => {
        const p = updateAppointmentStatus(token, id, newStatus);
        toast.promise(p, {
            loading: 'Actualizando estado...',
            success: () => {
                window.dispatchEvent(new Event("dashboard:refresh"));
                setViewAppt(null);
                loadAppointments();
                return STATUS_MSG[newStatus] || "Estado actualizado";
            },
            error: (err) => apiError(err, "Error al cambiar estado")
        });
    };

    const refreshAppointment = (updatedAppt) => {
        setAppointments(prev => prev.map(a => a.id === updatedAppt.id ? updatedAppt : a));
        setViewAppt(updatedAppt);
    };

    const handleWalkIn = async (data) => {
        await walkInAppointment(token, data);
        window.dispatchEvent(new Event("dashboard:refresh"));
        setWalkInOpen(false);
        loadAppointments();
    };

    const handleNewFromAppt = () => {
        setSelectedSlot(null);
        setTimeout(() => formRef.current?.scrollIntoView({ behavior:"smooth", block:"nearest" }), 50);
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

            {/* Page header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Citas</h1>
                    <p className="page-subtitle">{weekTitle(weekStart)}</p>
                </div>
                {canEdit && (
                    <button className="btn btn-primary btn-md"
                        style={{display:"flex",alignItems:"center",gap:"6px"}}
                        onClick={()=>setWalkInOpen(true)}>
                        <Icon.Plus s={15} /> Walk-in
                    </button>
                )}
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
                                            {cellAppts.map(a => (
                                                <ApptBadge
                                                    key={a.id}
                                                    appt={a}
                                                    pal={getVetPal(a.veterinarian)}
                                                    petName={a.pet_name || "—"}
                                                    ownerName={a.owner_name || ""}
                                                    onClick={setViewAppt}
                                                />
                                            ))}
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
                                onSaveWithPatient={handleSaveWithPatient}
                                onClear={()=>setSelectedSlot(null)}
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
                    petName={viewAppt.pet_name || "—"}
                    vetName={getVetName(viewAppt.veterinarian) || viewAppt.veterinarian_name}
                    petId={viewAppt.pet}
                    onClose={()=>setViewAppt(null)}
                    onStatusChange={handleStatusChange}
                    onEdit={appt=>{ setEditingAppt(appt); setViewAppt(null); }}
                    onNewFromAppt={appt=>{ setViewAppt(null); handleNewFromAppt(appt); }}
                    navigate={navigate}
                    canEdit={canEdit}
                    showHistory={!!orgSettings?.show_status_change_history}
                    onRefresh={refreshAppointment}
                />
            )}

            {/* Edit Modal */}
            {editingAppt && (
                <EditModal
                    appt={editingAppt}
                    staff={staff}
                    user={user}
                    onClose={()=>setEditingAppt(null)}
                    onSave={handleEditSave}
                />
            )}

            {/* Walk-in Modal */}
            {walkInOpen && (
                <WalkInModal
                    staff={staff}
                    user={user}
                    allowAnonymousWalkIn={!!orgSettings?.allow_anonymous_walkin}
                    onClose={()=>setWalkInOpen(false)}
                    onSave={handleWalkIn}
                />
            )}
        </div>
    );
};

export default Appointments;
