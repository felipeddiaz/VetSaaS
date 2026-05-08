import { useMemo } from "react";
import { Icon } from "../../components/icons";
import styles from "./medicalRecords.module.css";

const SPECIES_DOG = /perro|can[ei]|dog/i;
const SPECIES_CAT = /gato|fel[iy]|cat/i;

const getSpeciesBg = (species) => {
    if (SPECIES_DOG.test(species)) return "var(--c-primary-light)";
    if (SPECIES_CAT.test(species)) return "var(--c-purple-bg)";
    return "var(--c-subtle)";
};

const PetSidebar = ({
    pets,
    petCounts,
    selectedPet,
    petSearch,
    onSelectPet,
    onPetSearch,
    isLoadingPets = false,
    collapsed = false,
    onToggleCollapse,
}) => {
    const filteredPets = useMemo(() => {
        if (!petSearch.trim()) return pets;
        const q = petSearch.toLowerCase();
        return pets.filter(p =>
            p.name?.toLowerCase().includes(q) ||
            p.species?.toLowerCase().includes(q) ||
            p.breed?.toLowerCase().includes(q) ||
            (p.owner?.name || "").toLowerCase().includes(q)
        );
    }, [pets, petSearch]);

    const activePet = selectedPet ? pets.find(p => String(p.id) === String(selectedPet)) : null;

    if (collapsed) {
        return (
            <aside className={`${styles.petSidebar} ${styles.petSidebarCollapsed}`}>
                <button
                    className={styles.sidebarToggleBtn}
                    onClick={onToggleCollapse}
                    title="Mostrar buscador de mascotas"
                >
                    <Icon.ChevronRight s={16} />
                </button>

                {activePet && (
                    <div className={styles.sidebarRailPet} title={activePet.name}>
                        <div
                            className={styles.sidebarRailAvatar}
                            style={{ background: getSpeciesBg((activePet.species || "").toLowerCase()) }}
                        >
                            {SPECIES_DOG.test(activePet.species || "") ? <Icon.Dog s={14} /> :
                             SPECIES_CAT.test(activePet.species || "") ? <Icon.Cat s={14} /> :
                             <Icon.Paw s={14} />}
                        </div>
                        <span className={styles.sidebarRailName}>
                            {activePet.name.slice(0, 2).toUpperCase()}
                        </span>
                    </div>
                )}

                <div className={styles.sidebarRailCount} title={`${pets.length} mascotas`}>
                    <Icon.Paw s={13} />
                    <span>{pets.length}</span>
                </div>
            </aside>
        );
    }

    return (
        <aside className={styles.petSidebar}>
            <div className={styles.sidebarHeaderRow}>
                <span className={styles.sidebarHeader}>Mascotas</span>
                <button
                    className={styles.sidebarCollapseBtn}
                    onClick={onToggleCollapse}
                    title="Ocultar buscador"
                >
                    <Icon.ChevronLeft s={15} />
                </button>
            </div>

            <div className={styles.sidebarSearchWrap}>
                <span className={styles.sidebarSearchIcon}><Icon.Search /></span>
                <input
                    className={styles.sidebarSearchInput}
                    placeholder="Nombre, raza, especie…"
                    value={petSearch}
                    onChange={e => onPetSearch(e.target.value)}
                />
            </div>

            <div className={styles.petList}>
                {isLoadingPets ? (
                    <p className={styles.sidebarEmpty}>Cargando…</p>
                ) : filteredPets.length === 0 ? (
                    <p className={styles.sidebarEmpty}>Sin resultados</p>
                ) : filteredPets.map(pet => {
                    const sp = (pet.species || "").toLowerCase();
                    const isActive = String(pet.id) === String(selectedPet);
                    return (
                        <button
                            key={pet.id}
                            className={`${styles.petListItem}${isActive ? ` ${styles.petListItemActive}` : ""}`}
                            onClick={() => onSelectPet(String(pet.id))}
                        >
                            <div className={styles.petListIcon} style={{ background: getSpeciesBg(sp) }}>
                                {SPECIES_DOG.test(sp) ? <Icon.Dog size={15} /> :
                                 SPECIES_CAT.test(sp) ? <Icon.Cat size={15} /> :
                                 <Icon.Paw size={15} />}
                            </div>
                            <div className={styles.petListInfo}>
                                <div className={styles.petListName}>{pet.name}</div>
                                <div className={styles.petListSub}>
                                    {[pet.species, pet.breed].filter(Boolean).join(" · ") || "—"}
                                </div>
                            </div>
                            {petCounts[pet.id] > 0 && (
                                <span className={styles.petListBadge}>{petCounts[pet.id]}</span>
                            )}
                        </button>
                    );
                })}
            </div>
        </aside>
    );
};

export default PetSidebar;
