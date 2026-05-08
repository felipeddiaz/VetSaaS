# Mapeo .claude -> .agents (Compatibilidad Dual)

**Regla**: `.claude/skills` es la fuente canónica para Claude Code; `.agents/skills` es la capa de compatibilidad para este runtime.

## Inventory

| `.claude` | Tipo | Target `.agents` | Estado |
|-----------|-----|-----------------|--------|
| `code-reviewer` | skill | `skills/code-reviewer/` | ✅ ya espejado |
| `frontend-design` | skill | `skills/frontend-design/` | ✅ ya espejado |
| `senior-security` | skill | `skills/senior-security/` | ✅ ya espejado |
| `ui-ux-pro-max` | skill | `skills/ui-ux-pro-max/` | ✅ corregido |
| `react-best-practices` | skill | `skills/react-best-practices/` | ✅ espejado |
| `python-patterns` | skill | `skills/python-patterns/` | ✅ espejado |
| `api-security-best-practices` | skill | `skills/api-security-best-practices/` | ✅ espejado |
| `webapp-testing` | skill | `skills/webapp-testing/` | ✅ espejado |
| `security-auditor` | agent | `skills/security-auditor/SKILL.md` | ✅ convertido |
| `ui-ux-designer` | agent | `skills/ui-ux-designer/SKILL.md` | ✅ convertido |

## Leyenda

- ✅ ya espejado: existe y es usable
- ⚠️ necesita rewrite: existe pero tiene rutas/compatibilidad rotas
- 📋 pending: noch no espejado
- 📋 convertir: viene de `.claude/agents`, hay que adaptar a skill
- ⏭️ skip: no migrar (específico de Code/Codex)

## Reglas de Conversion

### Mirror as-is
Skill portable y autocontenido, mínimo cambio.

### Mirror with rewrite
Skill útil pero con rutas específicas de Code/Codex:
- `.Codex/` → `.claude/` o eliminar
- `context-manager` → remover o reescribir
- Nombres de herramientas específicos → mapear

### Convert agent -> skill
Agents de `.claude/agents` se convierten a:
- Extraer frontmatter
- Reescribir system prompt como skill instrucciones
- Ajustar herramientas disponibles
- Simplificar flujos complejos

### Leave Claude-only
No migrar:
- `agent-development` (específico de Code)
- `artifacts-builder` (específico de Code)
- `settings.local.json` (permisos Code)