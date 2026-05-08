const SPECIES_OPTIONS = ['canino', 'felino', 'equino', 'ave', 'reptil', 'exótico', 'otro'];

const SEX_OPTIONS = [
    { value: 'unknown', label: 'No especificado' },
    { value: 'male',    label: 'Macho' },
    { value: 'female',  label: 'Hembra' },
];

const fldLbl = {
    display: 'block', fontSize: '11px', fontWeight: '600',
    color: 'var(--c-text-2)', marginBottom: '3px',
    textTransform: 'uppercase', letterSpacing: '0.05em',
};

const sectionLbl = {
    fontSize: '10px', fontWeight: '700', color: 'var(--c-text-3)',
    textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: '6px',
};

const QuickPatientForm = ({ value, onChange, onCancel, disabled }) => {
    const set = (field, val) => onChange({ ...value, [field]: val });

    return (
        <div style={{
            padding: '12px', background: 'var(--c-subtle)',
            borderRadius: 'var(--r-md)', border: '1px solid var(--c-border)',
        }}>
            <p style={{ fontSize: '11px', fontWeight: '700', color: 'var(--c-text)',
                textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: '10px' }}>
                Nuevo paciente
            </p>

            <p style={sectionLbl}>Dueño</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '8px' }}>
                <div>
                    <label style={fldLbl}>Nombre *</label>
                    <input
                        className="input"
                        style={{ fontSize: '12px' }}
                        value={value.ownerName}
                        onChange={e => set('ownerName', e.target.value)}
                        placeholder="Ej: Juan Pérez"
                        disabled={disabled}
                    />
                </div>
                <div>
                    <label style={fldLbl}>Teléfono *</label>
                    <input
                        className="input"
                        style={{ fontSize: '12px' }}
                        value={value.ownerPhone}
                        onChange={e => set('ownerPhone', e.target.value.replace(/\D/g, '').slice(0, 10))}
                        placeholder="10 dígitos"
                        disabled={disabled}
                    />
                </div>
            </div>

            <p style={sectionLbl}>Mascota</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '6px' }}>
                <div>
                    <label style={fldLbl}>Nombre *</label>
                    <input
                        className="input"
                        style={{ fontSize: '12px' }}
                        value={value.petName}
                        onChange={e => set('petName', e.target.value)}
                        placeholder="Ej: Firulais"
                        disabled={disabled}
                    />
                </div>
                <div>
                    <label style={fldLbl}>Especie *</label>
                    <select
                        className="select-input"
                        style={{ fontSize: '12px' }}
                        value={value.species}
                        onChange={e => set('species', e.target.value)}
                        disabled={disabled}
                    >
                        <option value="">Seleccionar</option>
                        {SPECIES_OPTIONS.map(s => (
                            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                        ))}
                    </select>
                </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '10px' }}>
                <div>
                    <label style={fldLbl}>Sexo</label>
                    <select
                        className="select-input"
                        style={{ fontSize: '12px' }}
                        value={value.sex}
                        onChange={e => set('sex', e.target.value)}
                        disabled={disabled}
                    >
                        {SEX_OPTIONS.map(o => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label style={fldLbl}>F. Nacimiento</label>
                    <input
                        type="date"
                        className="input"
                        style={{ fontSize: '12px' }}
                        value={value.birthDate}
                        onChange={e => set('birthDate', e.target.value)}
                        disabled={disabled}
                    />
                </div>
            </div>

            <button
                type="button"
                onClick={onCancel}
                disabled={disabled}
                style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    fontSize: '11px', color: 'var(--c-text-3)', padding: '0',
                    textDecoration: 'underline',
                }}
            >
                ← Cancelar
            </button>
        </div>
    );
};

export default QuickPatientForm;
