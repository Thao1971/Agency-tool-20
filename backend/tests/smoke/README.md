# Smoke Tests — Intelligence Engine + Platform Console

Red de seguridad ejecutable antes y después de cada deploy.
**20 tests · ~1s contra localhost · ~4s contra preview.**

## Ejecución

```bash
# Contra local (default)
./tests/run_smoke.sh

# Contra preview / staging / producción
SMOKE_BASE_URL=https://data-factory-hub.preview.emergentagent.com ./tests/run_smoke.sh
SMOKE_BASE_URL=https://agencias.wearebudadvisors.com ./tests/run_smoke.sh

# Filtrar por test
./tests/run_smoke.sh -k engine_health

# Mostrar output detallado en fallo
./tests/run_smoke.sh -v --tb=long
```

Exit code 0 = deploy verde. Cualquier otro = investigar antes de promocionar.

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SMOKE_BASE_URL` | `http://localhost:8001` | Backend a testear |
| `SMOKE_TEST_EMAIL` | `daniel@wearebudadvisors.com` | Usuario admin |
| `SMOKE_TEST_PASSWORD` | (en `.env` privado) | Password del usuario |

## Tests incluidos (8 archivos · 20 tests)

| Archivo | Verifica |
|---------|----------|
| `test_engine_health.py` (2) | `/valuo/health` reachable + verdict ∈ {healthy, busy} + 12 buckets de timeline |
| `test_profiles.py` (3) | `/intelligence/profiles` devuelve exactamente {basic, valuo, arroba} |
| `test_enrichment.py` (3) | `enrich_company(profile=basic)` devuelve `_engine` block + 404 si master no existe + 400 si profile inválido |
| `test_valuo_e2e.py` (2) | `request-update-from-valuo` → status `completed` < 10s · 0 stuck globales |
| `test_web_source.py` (3) | Cache hit < 500ms · cache miss encola job · `/scrape-queue` reporta counts |
| `test_profiles_sources.py` (3) | basic ⊂ valuo ⊂ arroba (invariante de jerarquía) |
| `test_lineage.py` (2) | `master.sources.{web,bme,…}` existe post Phase-2 |
| `test_sidebar_sections.py` (2) | Layout.js declara las 7 secciones + branding "Intelligence Engine / Platform Console" |

## Integración CI/CD

Pre-deploy:
```yaml
- name: Smoke tests pre-deploy
  run: SMOKE_BASE_URL=https://staging.example.com ./backend/tests/run_smoke.sh
```

Post-deploy (canary):
```yaml
- name: Smoke tests post-deploy
  run: SMOKE_BASE_URL=https://agencias.wearebudadvisors.com ./backend/tests/run_smoke.sh
```

Cualquier fallo debería disparar rollback automático.
