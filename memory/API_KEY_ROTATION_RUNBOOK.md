# RUNBOOK — Rotación de API Keys de servicio (arroba.com)
**Documentación operativa. No bloquea la integración.**
_Versión: `api-key-rotation-v1` · 2026-07-04_

> La autenticación de los motores usa una **clave de servicio** en cabecera `X-API-Key`. La clave activa
> es el valor de la variable de entorno **`ARROBA_SERVICE_API_KEY`** de cada entorno. Al arrancar, el
> backend la **siembra hasheada (sha256)** en `db.api_keys` (`ensure_service_key`, idempotente).
> La clave **en claro NUNCA se guarda** en base de datos: solo su hash.

---

## 0. Entornos y dominios (fuente de verdad)
| Entorno | Base URL | Clave |
|---|---|---|
| **Preview (dev/staging)** | `https://data-factory-hub.preview.emergentagent.com` | `ARROBA_SERVICE_API_KEY` (preview) |
| **Producción** | `https://agencias.wearebudadvisors.com` | `ARROBA_SERVICE_API_KEY` (producción) |

> ⚠️ Preview y producción tienen (o deben tener) **claves distintas**. Rota SIEMPRE la de producción
> antes de dar acceso definitivo.

---

## 1. Cuándo rotar
- Antes de pasar de preview a producción (clave de producción nueva y exclusiva).
- Rotación periódica programada (recomendado cada 90 días).
- Ante sospecha de filtración o salida de un miembro con acceso.
- A petición del consumidor (arroba.com).

## 2. Modelo de seguridad (por qué es seguro)
- Solo se persiste el **hash sha256** de la clave (`db.api_keys.key_hash`, índice único).
- La clave en claro vive **solo** en la variable de entorno del servidor.
- El rate limit y el `last_used_at` se aplican por `key_hash`.

---

## 3. Procedimiento de rotación SIN downtime (recomendado)

> Estrategia de solape: se admite temporalmente la clave **nueva** y la **antigua** a la vez, se migra
> al consumidor, y solo entonces se revoca la antigua. Requiere una acción manual mínima en `db.api_keys`.

### Paso 1 — Generar una clave nueva (fuerte)
```bash
python3 -c "import secrets; print('as_' + secrets.token_urlsafe(32))"
```

### Paso 2 — Admitir la clave nueva SIN revocar la antigua (solape)
Insertar el hash de la clave nueva como registro de servicio adicional activo (no borra la antigua):
```bash
# NEWKEY = clave generada en el Paso 1
python3 - <<'PY'
import asyncio, hashlib, os
from datetime import datetime, timezone
from database import db
NEWKEY = os.environ["NEWKEY"]
async def go():
    h = hashlib.sha256(NEWKEY.encode()).hexdigest()
    await db.api_keys.update_one(
        {"kind": "service", "service_name": "arroba", "key_hash": h},
        {"$set": {"key_hash": h, "prefix": NEWKEY[:12], "active": True,
                  "kind": "service", "service_name": "arroba", "user_id": None,
                  "rotation_note": "new key during overlap"},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    print("nueva clave admitida (hash):", h[:16], "…")
asyncio.run(go())
PY
```
> A partir de aquí, tanto la clave antigua como la nueva son válidas.

### Paso 3 — Entregar la clave nueva a arroba.com por canal seguro
Gestor de secretos (1Password/Bitwarden/Vault) o enlace autodestructivo (onetimesecret).
**Nunca** en chats, tickets, repos ni documentos.

### Paso 4 — Actualizar la variable de entorno del entorno
- **Preview:** editar `backend/.env` → `ARROBA_SERVICE_API_KEY=<NEWKEY>` y `sudo supervisorctl restart backend`.
- **Producción:** actualizar `ARROBA_SERVICE_API_KEY` en la configuración de variables de entorno del
  deployment (panel de Emergent) y **redeployar/reiniciar**. `ensure_service_key` re-siembra al arrancar.

### Paso 5 — Confirmar que arroba.com ya usa la clave nueva
Verificar tráfico con la clave nueva (p. ej. `last_used_at` del hash nuevo) y confirmación del consumidor.

### Paso 6 — Revocar la clave antigua
```bash
# OLDKEY = clave anterior
python3 - <<'PY'
import asyncio, hashlib, os
from database import db
OLD = os.environ["OLDKEY"]
async def go():
    h = hashlib.sha256(OLD.encode()).hexdigest()
    r = await db.api_keys.update_one({"key_hash": h}, {"$set": {"active": False}})
    print("clave antigua revocada:", r.modified_count)
asyncio.run(go())
PY
```
> Alternativa a `active:false`: `db.api_keys.delete_one({"key_hash": <hash_old>})`.

---

## 4. Rotación SIMPLE (con breve corte) — si no se requiere solape
1. Generar clave nueva (Paso 1).
2. Reemplazar `ARROBA_SERVICE_API_KEY` en el entorno y reiniciar/redeployar.
   - Nota: `ensure_service_key` hace **upsert por `{kind, service_name}`**, por lo que actualiza el
     hash del registro de servicio de arroba; la clave antigua deja de ser válida al reiniciar.
3. Entregar la nueva a arroba.com por canal seguro y confirmar.
> Durante el reinicio y hasta que arroba use la nueva, las llamadas con la clave antigua dan `401`.

---

## 5. Verificación post-rotación
```bash
BASE=<base_url_del_entorno>
# Clave nueva → 200
curl -s -o /dev/null -w "new:%{http_code}\n" -X POST "$BASE/api/v1/financial-intelligence/analyze" \
  -H "X-API-Key: $NEWKEY" -H "Content-Type: application/json" -d '{"identifier":"<master_id>"}'
# Clave antigua → 401 (si ya revocada)
curl -s -o /dev/null -w "old:%{http_code}\n" -X POST "$BASE/api/v1/financial-intelligence/analyze" \
  -H "X-API-Key: $OLDKEY" -H "Content-Type: application/json" -d '{"identifier":"<master_id>"}'
```

## 6. Buenas prácticas
- Una clave **por entorno** y **por consumidor** (no compartir preview↔producción).
- Guardar SIEMPRE como secreto de servidor; llamadas **server-to-server** (nunca desde el navegador).
- Registrar cada rotación (fecha, motivo, quién) en el CHANGELOG operativo.
- No versionar claves en el repositorio (solo `ARROBA_SERVICE_API_KEY` en `.env`, que no se commitea).
