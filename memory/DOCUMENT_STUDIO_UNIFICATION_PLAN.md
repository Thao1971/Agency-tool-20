# DOCUMENT_STUDIO_UNIFICATION_PLAN.md
**Plan de desarrollo — Unificación del módulo de creación de documentos**
_Versión: `document-studio-unification-v1` · 2026-07-24 · Estado: **PROPUESTA, PENDIENTE DE APROBACIÓN — no iniciada la implementación**._

> Alcance confirmado por Daniel: unificar **Documentos**, **Marcas**, **Document Studio** y **Template Builder**. **Editorial queda fuera** (es la herramienta de curación de noticias sectoriales/"adCeo", módulo independiente y no se toca).

## Decisiones tomadas (2026-07-24, confirmadas por Daniel)

1. **Arquitectura (§1): APROBADA** — `docstudio` = base de composición inteligente (reescrita sobre datos/motores reales); `documents` = capa única de render/marca/exportación/entrega.
2. **Catálogo (§2): CERRADO** — 16 documentos en 3 familias (7 empresa + 6 sector/cartera + 3 legales).
3. **Modelo de marca: DOS CAPAS (white-label).**
   - **Capa base = marca de plataforma por defecto**, determinada por la plataforma activa que genera el documento: arroba.com → marca Arroba, BUD → marca BUD, Valuo → marca Valuo. Es el look de partida.
   - **Capa cliente (overlay) = personalización de quien se descarga el informe**: el cliente final puede aplicar **su propio logo** y **su sistema de diseño (fundamentalmente colores)** encima de la marca de plataforma. Es una capa ligera (logo + paleta) que se superpone, no una marca completa nueva.
   - Implicación: el modelo de marca unificado debe distinguir `marca_base` (plataforma) de `overlay_cliente` (logo + tokens de color), y componerlas en el render. Esto además **resuelve limpiamente la colisión** `brand_bud`/`brand_arroba` detectada: no hay que fusionar marcas "iguales" — la base la elige el contexto de plataforma, la personalización es un concepto aparte.
4. **IA = narrativa, con Claude.** La generación de texto (prosa/narrativa) de los documentos usa **Claude**, no el `gpt-5.2` que el código actual (`docstudio/model_provider.py`) tiene cableado. Sustituir el proveedor en la Fase 2. La IA es **narrativa** (redacta el texto a partir de datos ya calculados), nunca inventa cifras — se mantiene el principio "fact-locked" ya presente en el código.
5. **Familia C (legales): modelo estándar + cláusulas añadibles.** Se parte de plantillas estándar (NDA/LOI/NBO) y el usuario puede **añadir cláusulas** propias. No se redacta contenido jurídico inventado; la biblioteca base de cláusulas se define antes de construir.

6. **Documento de Oportunidades (B3): SIEMPRE acotado, nunca el universo en bruto.** Dos niveles independientes de personalización:
   - **Contenido (a qué oportunidades ve)**: se genera a partir de un *alcance* definido al crearlo — (a) **por filtros** (sector CNAE, provincia, tipo, tendencia): universal, sirve desde el minuto uno; (b) **por mandato de comprador** (E1): "las oportunidades que encajan con tu buy-box", más inteligente, requiere que el comprador tenga su mandato cargado. El universo completo ranqueado queda solo como **vista interna** de BUD (originar/rastrear), nunca como entregable a cliente.
   - **Marca (cómo se ve)**: capa base plataforma + overlay de cliente (decisión 3), independiente del alcance.
   - **Decisión de arranque**: se construye primero el modo **por filtros** (baseline universal) y luego el modo **por mandato** encima. Confirmado por Daniel ("ok").

7. **Control total de maquetación, en todo momento.** El usuario debe poder **añadir o eliminar módulos** (bloques/secciones), reordenarlos, controlar **colores** y **saltos de página**, etc., sobre cualquier documento — no solo elegir una plantilla fija. Implicaciones firmes:
   - Refuerza la decisión de arquitectura: la base de composición es el **modelo de bloques** de `docstudio` (secciones + bloques tipados, que ya soporta añadir/editar/reordenar/regenerar bloque a bloque), NO las plantillas HTML/CSS rígidas de `documents`. El render debe respetar overrides de maquetación por-documento.
   - El modelo de datos (Fase 1) debe soportar, **a nivel de documento** (no solo de plantilla): añadir/eliminar/reordenar módulos, un tipo de bloque **salto de página**, y overrides de color por-documento (además del overlay de marca de cliente).
   - El editor (Fase 5) es WYSIWYG por bloques: la plantilla es el punto de partida, pero todo es editable después.

8. **Punto de arranque: FASE 1 (fundamentos).** Confirmado por Daniel ("desde el principio para no liarnos"). Se unifica primero marca (2 capas) + plantilla (modelo de bloques con control de maquetación) antes de construir documentos nuevos.
9. **Generación asíncrona + aviso al usuario (decisión de Daniel).** Un documento tarda en procesarse; el usuario NO debe quedarse esperando. La generación ya es asíncrona (cola `document_jobs` + `documents/worker.py`). Requisitos a implementar:
   - **ETA / tiempo estimado** al pedir el documento — factible YA con dato real: la telemetría de DocStudio guarda `metadata.generation_time_ms` y `avg_generation_ms`; se muestra "suele tardar ~X s / min" a partir del histórico real por tipo de documento (nunca un número inventado).
   - **Notificación en plataforma** al terminar — construible (patrón similar a `watchlist_alerts`; hoy no hay un sistema de notificaciones general, se crea uno ligero o se reutiliza ese patrón).
   - **Notificación por correo electrónico** — ⚠️ **requiere infraestructura de envío que hoy NO existe** (sin SMTP/SES/SendGrid; solo hay lectura IMAP entrante para Editorial). Mismo hueco ya documentado para las alertas de Q7. Antes de construirlo hay que elegir proveedor de envío. Hasta entonces: ETA + notificación en plataforma cubren el caso; el email queda como dependencia de infraestructura separada.
   - Encaje: esto vive en la Fase 4 (salida/entrega) del pipeline unificado, pero el ETA puede añadirse antes en cuanto haya telemetría real de los documentos nuevos.

---

## 0. Resumen del hallazgo

Antes de proponer nada se auditó el código real de los 4 módulos. Conclusión: **no hay que construir el módulo de documentos desde cero — ya existen DOS sistemas completos y funcionando en paralelo, nunca unificados entre sí, y ninguno conectado a la Capa de Inteligencia Estratégica documentada en `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md`.** El trabajo real es de consolidación + reconexión de datos, no de creación desde cero.

### Sistema A — `documents/` ("Document Engine", detrás de las pantallas Documentos + Marcas)
Pipeline **genérico y productivo**: `document_templates` (HTML/CSS versionado) → `document_projects` (ciclo de vida draft→frozen) → `document_jobs` (cola async) → **worker real corriendo** (`documents/worker.py`, arrancado en `server.py`) → `document_outputs`. Marcas propias (`document_brand_profiles`, 3 marcas: `brand_bud`/`brand_cis`/`brand_arroba`, con tokens de diseño ricos: colores/fuentes/portada/cierre). Endpoint de integración externa `POST /integrations/{consumer}/generate` — **este es probablemente el que usan hoy CIS/Valuo.pro** para sus PDFs de valoración (`renderers/valuation_renderer.py`). Pero **no compone inteligencia por sí mismo**: espera que alguien le entregue `data_payload` ya calculado.

### Sistema B — `docstudio/` ("Document Intelligence Studio", detrás de Document Studio + Template Builder)
Motor **compositor inteligente**: 8 funciones `compose_*` reales y funcionando (sector_report, company_profile, benchmark_report, investment_memo, teaser, information_memorandum, company_snapshot, benchmark_advanced) + un compositor genérico dirigido por plantilla (`compose_from_template`, lo que alimenta el Template Builder). Tiene su propia IA narrativa (`model_provider.py`, GPT-5.2, con extracción JSON "fact-locked" de riesgos/oportunidades), su propio motor financiero (`docstudio/financial_engine.py`: márgenes, CAGR, comparables por similitud, benchmarks sectoriales, EV implícito), su propio almacén de marcas (`docstudio_brands`, 4 marcas: `brand_bud`/`brand_valuo`/`brand_arroba`/`brand_custom`) y plantillas (`docstudio_templates`), export PDF/PPTX propio, quality score por documento, telemetría.

### El problema real (por qué hay que unificar)

1. **Colisión de identidad de marca**: `brand_bud` y `brand_arroba` existen en AMBOS sistemas con definiciones de tokens distintas. Nadie puede saber, solo por el `brand_id`, cuál de los dos se está usando.
2. **Dos plantillas, dos motores de render**: `document_templates` (HTML/CSS) vs `docstudio_templates` (secciones + block_types + data_source + ai_prompt). El Template Builder de la pantalla homónima solo habla con el segundo — cualquier plantilla creada ahí es invisible para el pipeline de `documents/`.
3. **`docstudio/financial_engine.py` reinventa el `Financial Intelligence Engine`** (`services/engines/financial/`) con menos rigor: su "Valoración Preliminar" en el Infomemo usa un múltiplo heurístico fijo (`mediana_sector_revenue * 1.5`) en vez del `valuation()` real del motor canónico, que YA distingue múltiplo de mercado real (Q6, `market_observed`) de múltiplo inferido (`inferred_reference`) — es decir, **la versión "inteligente" del documento es hoy menos honesta que el motor de valoración que ya tenemos**.
4. **Ninguno de los dos sistemas lee el esquema moderno.** Los 8 `compose_*` de `docstudio/` consultan `companies_master`/`master_company_id` e `iberinform_financials` (esquema LEGACY) — no `master_companies`/`master_id`, que es lo que usan Financial/Signal/Semantic/Recommendation/Strategy Intelligence y toda la capa Q1–T3 documentada esta sesión. Los documentos generados hoy **no pueden** incluir señales activas, oportunidades, tesis estratégicas, comparables reales del Recommendation Engine, roll-up thesis, ni fragmentación sectorial — toda esa inteligencia ya construida y verificada es invisible para Document Studio.
5. **El propio registro de plantillas de `docstudio/routes.py` (`TEMPLATE_REGISTRY`) está desactualizado**: marca Teaser/IM/Investment Memo como `"planned"` cuando sus funciones `compose_teaser`/`compose_information_memorandum`/`compose_investment_memo` ya existen y funcionan. Sintoma del mismo patrón de "documentación que no refleja el código real" visto en otras partes de la plataforma.
6. **Frontend igualmente partido**: `DocumentsPage`+`BrandsPage` (bajo `pages/documents/`) hablan con el Sistema A; `DocStudioPage`+`TemplateBuilderPage` (bajo `pages/`) hablan con el Sistema B. 1.774 líneas de UI real ya escritas, repartidas sin relación entre sí.

---

## 1. Decisión de arquitectura propuesta

**No se retira ningún sistema de golpe.** Se sigue el mismo patrón ya usado en este repo para consolidaciones de esquema (`LEGACY_MIGRATION_PLAN.md`: Construir→Validar→Migrar→Convivencia→Monitorizar→Retirar).

| Capa | Rol final | Qué sobrevive |
|---|---|---|
| **Composición inteligente** | `docstudio/composer.py` es la base — es el único de los dos que ya "compone" documentos con lógica por tipo. Se **reescribe su capa de datos** para leer `master_companies`/`master_id` y llamar a los motores canónicos (Financial/Signal/Semantic/Recommendation/Strategy) en vez de reimplementarlos. | Sistema B, con la capa de datos sustituida |
| **Render, marca, exportación, integración externa** | `documents/` (Document Engine) es el más "productizado" — proyectos con ciclo de vida, cola async con worker real, integración ya usada por CIS/Arroba. Se convierte en la **capa de salida única**: todo documento (venga de un `compose_*` inteligente o de una plantilla libre) se renderiza, exporta y entrega a través de este pipeline. | Sistema A, como backend de render/export/entrega |
| **Marca** | Un único modelo de marca **en dos capas** (decisión 3): capa base = marca de plataforma (Arroba/BUD/Valuo, elegida por contexto) sobre `document_brand_profiles` (el más rico en tokens); capa overlay = personalización del cliente (logo + colores) aplicada en el render/descarga. Sustituye a `docstudio_brands`; la colisión `brand_bud`/`brand_arroba` deja de ser problema (la base la fija la plataforma, no hay que fusionar). | Modelo de `documents/` + nueva capa overlay |
| **Plantillas** | Un único modelo de plantilla, con el formato "declarativo" de `docstudio_templates` (secciones + `data_source` + `ai_prompt`) porque es el que permite that el Template Builder genere plantillas nuevas sin tocar código — pero versionado y almacenado bajo el esquema de `document_templates` (con su ciclo `draft→published`, ya resuelto en Sistema A). | Formato de `docstudio`, ciclo de vida de `documents` |
| **Frontend** | 4 pantallas → 3: **Documentos** (galería de documentos generados + generar nuevo a partir de un tipo/plantilla), **Marcas** (gestor único), **Template Builder** (crear/editar plantillas personalizadas). "Document Studio" desaparece como pantalla propia — su funcionalidad (componer, exportar, dashboard, telemetría) se reparte entre Documentos y un panel de métricas dentro de Plataforma. | — |

Esto es una decisión de arquitectura no trivial (afecta al pipeline que ya consumen CIS/Arroba). **Se pide confirmación explícita de Daniel antes de tocar código** — ver §4.

---

## 2. Catálogo de documentos a construir

Se valida la lista contra los datos reales disponibles hoy. Todos son viables — ninguno requiere una fuente de datos que no exista ya en la plataforma (principio de no fabricar que gobierna todo el repo). El catálogo se organiza en **tres familias**, porque la plantilla y la entrada de datos son distintas en cada una — decisión de diseño que el módulo debe reflejar desde el principio:

- **A. Documentos de empresa** — entrada = una compañía (`master_id`/CIF).
- **B. Documentos de sector / cartera** — entrada = un sector (CNAE) / territorio / mandato, no una empresa.
- **C. Documentos legales / transaccionales** — no dependen de datos de empresa sino de cláusulas y partes; encajan en el módulo como plantillas rellenables, no como composición inteligente.

### Familia A — Documentos de empresa

| # | Documento | Estado hoy | Motores/datos reales | Esfuerzo |
|---|---|---|---|---|
| A1 | **Teaser de empresa** | Existe (`compose_teaser`), esquema legacy | Financial Intelligence (KPIs anonimizados) + Semantic (descripción de sector) | Bajo — migrar fuente |
| A2 | **Infomemo** (Information Memorandum) | Existe (`compose_information_memorandum`), el más completo hoy | Financial (históricos/ratios) + Signal (riesgos/oportunidades reales, hoy generados por IA "a ciegas") + `valuation()` real en vez del heurístico | Medio |
| A3 | **Análisis estratégico de empresa** | Parcial (`compose_company_profile` es solo ficha) — requiere ampliación real | Financial + Signal + Semantic + Strategy (Strategic Thesis) — el más compuesto, agrega 4 motores | Alto |
| A4 | **Análisis comparativo** | Parcial (motor propio de similitud) | Recommendation Engine `/comparables` (fit multidimensional real) + Semantic `/similar` | Medio |
| A5 | **Aproximación de valor** | No existe como documento (el dato sí) | Financial `valuation()` — documento corto 1-2 páginas, sin escenarios | Bajo |
| A6 | **Valoración avanzada** | No existe | `valuation()` + Q6 múltiplos reales + comparables (Recommendation) + escenarios bull/base/bear (Strategy `/scenarios`) | Alto |
| A7 | **Perfil de sucesión** ⭐ nuevo | No existe (el dato sí: `/succession-profile`, E2) | Signal/E2 Succession Intelligence — "el trigger de originación más potente en PYME familiar española" (Capability Map) | Bajo-Medio |

### Familia B — Documentos de sector / cartera

| # | Documento | Estado hoy | Motores/datos reales | Esfuerzo |
|---|---|---|---|---|
| B1 | **Análisis sectorial y/o geográfico** | Existe (`compose_sector_report`), ya sobre datos reales | Economic/Sector/Geo Intelligence + E7 Fragmentación opcional | Bajo |
| B2 | **Benchmark sectorial** | Existe (`compose_benchmark_report`/`_advanced`) | Financial (agregados sectoriales) — migrar del motor propio al canónico | Bajo-Medio |
| B3 | **Documento de oportunidades** | No existe — dato más maduro (160 oport. reales verificadas en v16) | Signal `/opportunities` + Recommendation (`/buyers`/`/sellers`) + Strategy (tesis). **SIEMPRE acotado** (ver decisión 6), nunca volcado del universo | Medio |
| B4 | **Ranking sectorial / de empresas** ⭐ nuevo | No existe (dato sí) | Sector Intelligence V2 `dynamism_score` (nivel sector) + ranking de empresas por facturación/crecimiento/señales (Q5) | Bajo |
| B5 | **Tesis de roll-up / consolidación** ⭐ nuevo | No existe (motor sí: E6, verificado) | E6 `rollup-thesis` (viabilidad HHI + candidato a plataforma + ranking de add-ons) | Medio |
| B6 | **Mapa de fragmentación sectorial** ⭐ nuevo | No existe (motor sí: E7, verificado) | E7 `fragmentation` (HHI + targets standalone viables) — diagnóstico de sector, complementa a B5 | Bajo |

### Familia C — Documentos legales / transaccionales (plantillas rellenables, no composición inteligente)

| # | Documento | Estado hoy | Naturaleza | Esfuerzo |
|---|---|---|---|---|
| C1 | **NDA** (acuerdo de confidencialidad) | En `TEMPLATE_REGISTRY` como "planned" | Plantilla con cláusulas + campos de partes/fechas/alcance. Sin datos de empresa salvo identificación. | Bajo |
| C2 | **Oferta no vinculante** (NBO / IOI) | No existe | Plantilla + puede pre-rellenar rango de valoración desde A5/A6 (Aproximación/Valoración) — puente natural con la Familia A | Medio |
| C3 | **LOI** (carta de intenciones) | En `TEMPLATE_REGISTRY` como "planned" | Plantilla con términos de la operación (precio, exclusividad, condiciones, calendario) | Medio |

> **Nota sobre la Familia C**: son documentos **legales**, no de inteligencia — su valor no está en componer datos sino en tener plantillas jurídicas correctas y rellenables. Se incluyen en el módulo por decisión de producto (que todo el ciclo documental de una operación viva en un mismo sitio), pero se construyen con un motor de plantilla + campos, no con los `compose_*` inteligentes. **La NBO (C2) es el puente**: puede pre-rellenar su rango de precio desde la Aproximación/Valoración (A5/A6), conectando la inteligencia con el documento transaccional. Antes de construir C1/C3 conviene decidir si las cláusulas las aporta el equipo legal (plantillas propias) o se parte de modelos estándar — no inventar redacción jurídica.

**Nota sobre A5 y A6**: no son el mismo documento a distinta extensión — "Aproximación de valor" es deliberadamente ligero (un número + su método) y "Valoración avanzada" compone escenarios y comparables. Se mantienen como dos entregables distintos porque tienen audiencias distintas (conversación inicial vs. soporte de una decisión).

**Segunda tanda (no en este catálogo inicial, documentadas para no perderlas)**: Longlist/screening de targets por mandato (E1 Buyer Mandate), Informe de matching comprador-vendedor (Recommendation `/matching`), Mapa de control / estructura societaria (T3 grafo — esfuerzo alto por el render de grafo), Digest de watchlist (Q7 — encaja mejor como informe recurrente/email que como documento puntual).

---

## 3. Fases de desarrollo propuestas

### Fase 0 — Congelar el punto de partida (sin código)
Confirmar con Daniel la decisión de arquitectura de §1 antes de tocar nada. Ningún consumidor existente (CIS/Arroba vía `/documents/integrations/{consumer}/generate`) debe romperse durante la migración.

### Fase 1 — Unificar Marca y Plantilla (fundamentos, sin tocar composición)
- **Marca en dos capas (decisión 3):** capa base = marca de plataforma (Arroba/BUD/Valuo) sobre `document_brand_profiles`; nueva **capa overlay de cliente** = entidad ligera (logo + paleta de colores + opcionalmente fuente) que se aplica en el render. El documento final compone base + overlay. Migrar las marcas de `docstudio_brands` a este modelo (la colisión `brand_bud`/`brand_arroba` se disuelve: la base la fija la plataforma).
- Unificar el modelo de plantilla: `document_templates` adopta el formato declarativo de `docstudio_templates` (secciones + `data_source` + `ai_prompt`) como un campo más de su esquema (aditivo, no rompe lo existente).
- Un único Template Builder (frontend) que escribe en el modelo unificado; la pantalla Marcas gestiona base (plataforma) y permite al cliente definir su overlay.
- Smoke tests de migración (mismo patrón que toda la sesión: verificar antes/después, cero pérdida de datos) + test de que overlay de cliente se aplica correctamente sobre cada marca base.

### Fase 2 — Reconectar la composición al esquema e inteligencia modernos
- Reescribir cada `compose_*` de `docstudio/composer.py` para leer `master_companies`/`master_id` en vez de `companies_master`.
- Sustituir `docstudio/financial_engine.py` por llamadas in-process al **Financial Intelligence Engine** real (mismo backend, sin necesidad de HTTP).
- Añadir Signal Intelligence (señales/oportunidades activas de la empresa) como fuente de datos disponible para cualquier plantilla, no solo para el Infomemo.
- **IA narrativa con Claude (decisión 4):** sustituir el proveedor `gpt-5.2` cableado en `docstudio/model_provider.py` por Claude para toda la generación de texto narrativo. Mantener el patrón "fact-locked" ya existente (la IA redacta a partir de datos ya calculados, nunca inventa cifras). La capa de análisis/extracción determinista no cambia; lo que pasa a Claude es la prosa.
- Retirar `docstudio/financial_engine.py` una vez migrado (Definition of Done: cero referencias).

### Fase 3 — Construir los documentos que faltan de verdad
Por orden de valor/esfuerzo (dato ya listo primero):
1. **Documento de Oportunidades** (B3) — dato más maduro, 160 oport. reales verificadas.
2. **Ranking sectorial** (B4) y **Mapa de Fragmentación** (B6) — esfuerzo bajo, motores ya verificados.
3. **Aproximación de Valor** (A5) y **Perfil de Sucesión** (A7) — esfuerzo bajo, dato listo.
4. **Tesis de Roll-up** (B5) y **Análisis Comparativo** (A4) — esfuerzo medio.
5. **Análisis Estratégico de Empresa** (A3, agrega 4 motores) y **Valoración Avanzada** (A6, con escenarios) — los dos más ambiciosos, al final.

### Fase 3-bis — Documentos legales / transaccionales (Familia C)
Motor de plantilla + campos rellenables (no `compose_*`), con **biblioteca de cláusulas estándar + cláusulas añadibles por el usuario** (decisión 5). **NDA** (C1) → **Oferta no vinculante** (C2, con pre-relleno de rango desde A5/A6) → **LOI** (C3). Se parte de modelos estándar; el usuario puede añadir cláusulas propias. No se redacta contenido jurídico inventado — la biblioteca base se define antes de construir.

### Fase 4 — Unificar la salida (render/export/entrega)
Todo `compose_*` deja de generar su propio PDF/PPTX (`docstudio/pdf_export.py`/`pptx_export.py`) y en su lugar entrega su `data_payload` estructurado al pipeline de `documents/` (`documents/renderers/`, `documents/worker.py`) para render, versión, congelación y exportación — una sola vía de salida, un solo lugar donde CIS/Arroba y el resto de consumidores externos reciben el documento final.

### Fase 5 — Consolidar frontend
De 4 pantallas a 3 (Documentos, Marcas, Template Builder) según §1. `DocStudioPage.js` se retira; su dashboard/telemetría se reubica.

### Fase 6 — Retirar el código duplicado
Solo cuando Fases 1-5 estén verificadas y desplegadas: eliminar `docstudio_brands`, `docstudio_templates` (tras migración confirmada), `docstudio/financial_engine.py`, `docstudio/pdf_export.py`/`pptx_export.py`, y las rutas de `docstudio/routes.py` que queden sin uso.

---

## 4. Estado de las decisiones (todas confirmadas salvo el punto de arranque)

1. Arquitectura (§1) — ✅ **APROBADA** (ver Decisiones §3 arriba).
2. Catálogo (§2) — ✅ **CERRADO**, 16 documentos en 3 familias.
3. Modelo de marca — ✅ **DOS CAPAS** (plataforma por defecto + overlay de cliente con logo/colores).
4. Familia C legales — ✅ **modelo estándar + cláusulas añadibles**.
5. IA — ✅ **narrativa con Claude**.
6. **Punto de arranque — ⏳ ÚNICA PREGUNTA ABIERTA**: ¿Fase 1 (fundamentos) o Fase 3 directa (Documento de Oportunidades primero)? Recomendación: Fase 3 con Documento de Oportunidades, montando en paralelo la marca de 2 capas.

**Documentos relacionados**: `LEGACY_MIGRATION_PLAN.md` (patrón de migración ya validado en este repo), `STRATEGIC_INTELLIGENCE_LAYER_REPORT.md` y `INTELLIGENCE_API_REFERENCE.md` (motores que Document Studio debe consumir), `ARROBA_COPILOT_DEFINITION_v1.md` (el futuro Copilot de arroba.com también podría pedir documentos a este mismo pipeline unificado — razón adicional para no dejarlo partido en dos).
