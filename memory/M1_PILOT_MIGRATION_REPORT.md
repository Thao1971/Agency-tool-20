# M1_PILOT_MIGRATION_REPORT.md
**Informe final — Sprint 8.2 · Consolidación de la Red de Seguridad + M1 (migración piloto)**
_Versión: `m1-report-v1` · 2026-06-26 · Estado: **COMPLETADO**._

> Objetivo: cerrar los gaps de la red de seguridad y validar el procedimiento completo
> **Construir → Validar → Migrar → Convivencia → Monitorizar → Retirar** con una migración real de bajo riesgo.

---

## 1. Estado de los Golden Tests
- **Cobertura**: de 47 → **62 tests** (suite `/app/backend/tests/golden/`).
- **Nuevos casos añadidos (FASE A)**:
  - `test_data_layer_admin_contract.py` (9): auth-gates de rebuild-master/embeddings/signals/graph + **contrato `rebuild-signals`** (superficie de M1) + jobs (list/404/cancel-409).
  - `test_signal_engine_snapshot.py` (6): **snapshot determinista** de `compute_signals` (`signal_score=71`, 9 señales con tipo/título/severidad/score/confidence) + invariantes (uuid, clamps 0..1, score 0..100) + `signal_similarity` (0.95/0.3/0.75) + caso sparse + **test de paridad M1**.
- **Resultado final**: **62/62 PASS** (idempotente, ~3.4s).

## 2. Resultado de M1
- **Componentes migrados**: `services/signal_engine.py` → **relocalizado byte-for-byte** a `services/engines/signal/master_signals.py` (md5 idéntico verificado). Importadores actualizados: `routes/data_layer.py`, `services/skills_recommend.py`.
- **Componentes en convivencia**: `services/signal_engine.py` queda como **shim** re-exportando `compute_signals/rebuild_signals/signal_similarity` (fase CONVIVENCIA).
- **Componentes retirados**: **ninguno** (retirada diferida hasta confirmar 0 importadores externos).
- **Decisión clave**: la sustitución semántica por el motor canónico `engines/signal.engine` **se descartó** por no ser funcionalmente equivalente (distinta colección/esquema/salida); habría roto el contrato de `skills/recommend` y `rebuild-signals`. El movimiento seguro fue **relocalizar + shim**.

## 3. Validación (condiciones obligatorias del sprint)
| Condición | Resultado |
|---|---|
| Golden Contract Tests 100% | ✅ **62/62** |
| Suite Smoke en verde | ✅ **203/203** (un fallo puntual de `test_logo_url_resolves_to_binary` fue flakiness por timeout bajo carga; pasa en aislamiento y en re-ejecución completa) |
| Sin regresión funcional | ✅ |
| Sin cambios de contrato externo | ✅ (ningún endpoint/ruta/JSON modificado) |
| Sin disminución de cobertura | ✅ (47 → 62 golden) |
| Sin diferencias de comportamiento entre implementaciones | ✅ **test de paridad**: shim ↔ canónico son el mismo objeto; mismo `signal_score` |
| Compatibilidad con **Valuo.pro** | ✅ nula afectación (no consume signal_engine) |
| Compatibilidad con **arroba.com** | ✅ `skills/recommend` idéntico (golden verde) |

## 4. Recomendaciones
- El patrón **Construir → Validar → Migrar → Convivencia → Monitorizar → Retirar** queda **validado** con evidencia (paridad + golden + smoke). El procedimiento es repetible.
- **Matiz aprendido**: distinguir dos tipos de migración:
  1. **Relocalización/consolidación** (como M1): mover código sin cambiar lógica → riesgo mínimo, shim de convivencia.
  2. **Sustitución semántica** (M2–M5): cambiar el origen de datos/lógica → exige paridad estricta vía golden + posibles snapshot-diffs + flags + convivencia larga.
- **Antes de M2** (riesgo MEDIO, toca el camino de Valuo.pro `profile=valuo`): cerrar los gaps de cobertura aún abiertos — golden de los endpoints admin secundarios de `master` y operativos de `intelligence_engine`, y **snapshot-diffs** de `enrich?profile=valuo` por empresa fija (golden data set) para detectar derivas de cálculo.
- **Monitorización de M1**: vigilar que ningún nuevo código importe `services.signal_engine`; cuando el único importador sea el snapshot test, planificar la retirada del shim (apuntando el snapshot test a la ruta canónica).

## 5. Conclusión
M1 demuestra que la plataforma puede evolucionar **sin afectar a ningún consumidor externo**. **No se inicia M2/M3/M4/M5** hasta tu aprobación. Recomendación: aprobar el patrón y abordar M2 tras cerrar los gaps de cobertura indicados.
