# Canon de Narrativa CF · Ficha de empresa (ARROBA)

> Fuente única de verdad de **cómo habla** la ficha. Rige por encima de cualquier copy existente.
> Objetivo: que todo lo que lee el usuario suene a **analista / consultor / estratega de M&A** —
> preciso y sofisticado en lo financiero— **en prosa**, sin tecnicismos de máquina ni referencias a
> mecanismos internos de la plataforma. Complementa (no sustituye) las etiquetas ARROBA ya aprobadas.

---

## 1. Principios

1. **Prosa, no telegrama.** Frases completas de registro asesor. Nada de enums, pares clave-valor,
   ni cadenas tipo `signal: sector_contraction`.
2. **Cero interior de la máquina.** No aparecen: nombres de motores/engines, "proveedor", "agregador",
   "score" (como palabra), `engine_version`, `master_id`, `testid`, códigos de estado, ni el
   funcionamiento del cálculo ("universo", "degraded", "muestra", "fan-out", "passthrough").
3. **Cero jerga codificada.** No se muestran códigos CNAE, `geo_id`, acrónimos como etiqueta suelta
   (HHI, PN/Activo, DSO…), ni nombres de metodologías crudas ("DOJ/FTC Horizontal Merger Guidelines").
   El **nombre del sector/territorio en claro** sí; el código, no.
4. **La cifra vive dentro de la frase.** "una caída del 15,4% en el último año", no `yoy: -15.4`.
   Los números que ya aporta la ficha (anillos, KPIs, tablas) se mantienen; lo que cambia es la
   **narrativa** que los acompaña.
5. **Honestidad sin exponer el método.** Cuando el dato es orientativo, se dice en prosa el *qué*
   ("lectura orientativa por el reducido número de comparables"), nunca el *cómo* interno
   ("degraded a division por universo <5").
6. **Sobrio, no publicitario.** Registro de teaser / memo de comité de inversión: afirmaciones
   medidas, sin superlativos de marketing y sin adornos.

---

## 2. Léxico: prohibido → cómo se dice

| No usar (interno/tecnicista) | En prosa CF |
|---|---|
| motor / engine / scoring / proveedor / agregador | (se omite; se describe el hecho, no el sistema) |
| `signal: sector_contraction` | "el sector se encuentra en contracción" |
| `signal: growth_momentum` | "el sector muestra impulso de crecimiento" |
| `signal: corporate_hub` | "plaza empresarial de primer nivel / gran concentración de actividad" |
| `trend_direction: down/up/flat` | "a la baja / al alza / estable" |
| `primary_driver: activity/size` | "impulsado por la actividad / por el tamaño del mercado" |
| `HHI 10000 · highly_concentrated` | "mercado muy concentrado" |
| `cnae_level: group/division` · código CNAE | nombre del sector en claro (sin código ni nivel) |
| `degraded: true` / `degraded_reason` | "lectura ampliada al conjunto del sector por disponibilidad de datos" |
| `caveat: universo reducido` | "conviene tomarlo como orientativo" |
| `scope: sector CNAE + banda de tamaño (0,3x–3x ingresos)` | "entre compañías comparables por sector y tamaño" |
| `sector_revenue_percentile: 100` | "en la primera posición por ingresos de su sector" |
| `PN/Activo 73,5%` | "una autonomía financiera del 73,5% (patrimonio neto sobre activo)" |
| `Calidad financiera sólida (100/100)` | "calidad financiera sólida" (el número lo lleva el anillo) |
| "no lo proporciona el motor" | "Información en preparación · Estamos consolidando este apartado." |

---

## 3. Reescrituras por sección (antes → después)

### Mercado
- **Sector** — antes: `dynamism 19 · yoy −15,4 · trend down · signal sector_contraction · primary_driver activity`.
  Después: *"El sector de especialidades farmacéuticas se encuentra en contracción, con una caída de
  actividad del 15,4% en el último año. El dinamismo es reducido y la evolución, a la baja."*
- **Geografía** — antes: `Madrid · dynamism 61 · signal corporate_hub · net_company_creation 1544`.
  Después: *"Madrid es una plaza empresarial de primer nivel y elevado dinamismo, con creación neta de
  empresas positiva en el último ejercicio."*
- **Concentración** — antes: `HHI 10000 · highly_concentrated · degraded false · caveat universo reducido`.
  Después: *"Es un mercado muy concentrado, en manos de unos pocos operadores. El reducido número de
  compañías comparables aconseja tomar esta lectura como orientativa."*
- **Caso degradado (PROCOLUIDE)** — antes: `degraded true · cae a division · degraded_reason universo del grupo insuficiente`.
  Después: *"El análisis se ha ampliado al conjunto del sector químico por disponibilidad de datos
  comparables; la lectura de concentración es, por tanto, orientativa."*

### Rankings / Posición
- Antes: `#2 de 9 · scope "sector CNAE + banda de tamaño (0,3x–3x ingresos)"`.
  Después: *"Segunda por ingresos entre nueve compañías comparables de su sector y tamaño."*
- Antes: `percentil 100`.
  Después: *"Se sitúa en cabeza por ingresos de su sector."* (o "en el tramo alto", según percentil).
- Antes: `#1 de 34 · scope municipio`.
  Después: *"Primera por ingresos entre las de su sector en Madrid."*

### Lectura financiera / Veredicto
- Antes: `"Calidad financiera sólida (100/100). Margen EBITDA moderado del 11.3%. … Autonomía financiera (PN/Activo) del 73.5%."`
  Después: *"Compañía de calidad financiera sólida: margen EBITDA moderado del 11,3%, ingresos al alza
  (+11,7% interanual) y una holgada autonomía financiera del 73,5% (patrimonio neto sobre activo)."*
  (El "100" permanece en el anillo de Diagnóstico; no se repite como "100/100" en la frase.)
- Fortalezas/riesgos: frase completa, no etiqueta. Antes: `"Crecimiento de ingresos >10% interanual"`.
  Después: *"Crecimiento de ingresos superior al 10% en el último año."*

### Estados vacíos
- Único copy aprobado: **"Información en preparación · Estamos consolidando este apartado."**
  (En Mercado/Rankings puede añadirse el nombre del apartado, sin mecanismos.)

---

## 4. Reglas de composición

- **Una idea, una frase.** Sujeto claro (la compañía / el sector / la plaza) + hecho + cifra.
- **Cifras en español**: coma decimal, "M€"/"k€", porcentajes con signo cuando aporta ("+11,7%").
- **Acrónimos**: si son inevitables (EBITDA, ROE), se usan como término financiero, no como etiqueta
  suelta; la primera aparición puede glosarse en prosa.
- **Nombres en claro**: sector y territorio por su nombre; nunca su código.
- **Sin imperativos de sistema** ("cablea", "consolida el apartado" fuera del estado vacío aprobado).

---

## 5. Reparto de aplicación (Intel / Beta)

- **Intel** reescribe los textos que **emite** en el contrato: `verdict`, `assessment`, `strengths[]`,
  `weaknesses[]`, `risks[]`, `explain[]`, los `caveat`/`degraded_reason`, y traduce los enums
  (`signal`, `primary_driver`, `trend_direction`, `concentration_label`) a **frases** o a un campo
  de texto ya redactado. Los enums crudos pueden seguir en el JSON como metadato, pero **debe existir
  un campo de prosa** que Beta pinte; Beta nunca traduce enums por su cuenta (evita derivación).
- **Beta** reescribe los textos que **renderiza**: títulos de sección, etiquetas, `scope`, tooltips,
  estados vacíos, y consume el campo de prosa de Intel en vez de componer a partir de enums/cifras
  sueltas. Donde hoy compone la frase a partir de valores, pasa a mostrar la prosa de Intel.

Regla de oro: **la frase de cara al usuario se redacta una sola vez, en el lado que posee el dato**
(R13, fuente única). Si un enum no tiene aún su frase, Beta muestra el hecho mínimo en prosa neutra
o `Empty`, nunca el enum.

---

## 5.bis Decisiones ratificadas (2026-08-11)

- **Campo de prosa = `narrative` por bloque:** `sector.narrative`, `geo.narrative`,
  `concentration.narrative`, `position.narrative` (string, nullable). Se conservan los enums/cifras
  crudos como metadato. Beta lee `narrative`; si null → `Empty`. Financiero mantiene `assessment` + `verdict`.
- **Bandas de percentil → frase** (posicional/neutra; la polaridad la da el nombre de la métrica):
  ≥90 "en cabeza de su sector" · 75–89 "en el tramo alto del sector" · 50–74 "por encima de la media
  del sector" · 25–49 "por debajo de la media del sector" · <25 "en el tramo bajo del sector".
  Posición ordinal (rank/total) → literal: "Segunda de nueve compañías comparables de su sector y tamaño."
- **`scope` y `explain[]`:** los emite Intel → se **foldean en `position.narrative`**; Beta deja de
  mostrar el crudo. Títulos de sección, etiquetas, tooltips y estados vacíos = Beta.
- **Traducción enum→frase determinista** (sin IA, dato real), según §2.

## Anexo A · Inventario de strings + reescrituras (de `CompanyFichaLayoutV2.tsx`)

> Basado en la copia local del componente (puede ir por detrás de la versión de Beta en preview).
> Beta **reconcilia contra su versión actual** y **añade los strings de las secciones nuevas**
> (Gobierno, Propiedad, Eventos/BORME, Mercado, Rankings, Hero Veredicto), que aquí no aparecen.
> Columna "Lado": **B** = copy del front (Beta) · **I** = narrativa emitida (Intel).

| Ubicación | Texto actual (tecnicista/interno) | Reescritura CF | Lado |
|---|---|---|---|
| Panel "Próxima acción" | "…se activará al cablear el estado de la compañía a su motor." | "Aún no consta el estado de la compañía (en venta, buscando capital, comprando). En cuanto se determine, aquí verás la recomendación de actuación." | B |
| Empty `Pending` | "Este dato aún no lo proporciona el motor para esta compañía." | "Información en preparación · Estamos consolidando este apartado." | B |
| Resumen · card scores | "Scores de inteligencia" / "Calculados por Arroba" | "Diagnóstico de ARROBA" / "Valoración cualitativa de ARROBA" | B |
| Resumen · 2ª fila KPI | "Ranking mercado · sector · territorio" / "percentil facturación" / "Innovación · inferido" | (sustituir por Rankings real: "Posición en el sector", "Percentil por ingresos", "Posición local"; **quitar "Innovación · inferido"** si no hay dato) | B |
| Resumen · Identificación | "Datos registrales · fuentes verificadas + BORME" | "Datos registrales y de registros públicos" | B |
| Finanzas · card narrativa | "Inteligencia Arroba" | "Lectura financiera de ARROBA" | B |
| Finanzas · ratios leyenda | "Dato recibido (verificado)" / "Calculado por Arroba" / "Barra = percentil sectorial" | "Verificado en fuente" / "Estimación de ARROBA" / "La barra indica el percentil frente al sector" | B |
| Valoración · intel | "El valor mostrado es una aproximación devuelta por el motor." | "El valor mostrado es una aproximación orientativa, no una valoración formal." | B |
| Valoración · Ring | "Quality Score" / "de 100 · calidad financiera" | "Calidad financiera" (el número lo lleva el anillo) | B |
| Valoración · hipótesis | "El motor devuelve la explicación, no solo el número — sin cifras inventadas" | "Los factores que sustentan el rango de valor:" | B |
| Comparativa · perfil | "Los rasgos con los que Arroba busca sus comparables" | "Rasgos de negocio que definen a la compañía frente a sus comparables" | B |
| Comparativa · compradores | "Ordenados por encaje (0–100). Haz clic…" | "Ordenados por grado de encaje. Selecciona un comprador para ver por qué encaja." | B |
| Comparativa · descomposición | "Descomposición del encaje {N}/100…" | "Cómo se descompone el encaje de {comprador}, factor a factor." | B |
| Comparativa · parecidas | "La similitud la calcula el Fingerprint: modelo de negocio…" | "Compañías con un perfil de negocio análogo por sector, tamaño, márgenes y territorio." | B |
| Señales · subtítulo/meta | "Severidad {x} · confianza {N}%" | narrativa: "Relevancia alta/media/baja" (sin acrónimos ni % crudo, o glosado en prosa) | I/B |
| Copilot · nota | "…el Copilot responde con sus motores." | "Pregunta sobre esta compañía y el copiloto te responde con su análisis." | B |
| Evolución (masked) | "🔒 Regístrate para ver las cifras" | (correcto; se mantiene) | B |
| Rankings/Mercado (nuevo) | enums `signal/primary_driver/trend/concentration_label` + `scope`/`explain` | prosa vía `narrative` por bloque (§5.bis) | I |

**Regla de aplicación:** donde hoy el front compone la frase a partir de valores/enums (Mercado, Rankings,
Señales severidad), pasa a **consumir la prosa de Intel** (`narrative`, `assessment`, `verdict`, `explain`
foldeado). El resto (títulos, etiquetas, leyendas, estados) lo reescribe Beta con esta tabla.

## Anexo B · Señales (Cambios relevantes) + Oportunidades

> El canon aplica a **toda** la ficha (Daniel 2026-08-13). Estas dos secciones siguen mostrando el payload
> crudo del motor de señales/recomendación. Reescrituras:

| Ubicación | Actual (tecnicista) | Reescritura CF | Lado |
|---|---|---|---|
| Señal · título | `growth.ebitda_expansion` (nombre de regla) | usar la **descripción** como titular ("EBITDA +24,4% interanual"); nunca el ID de regla | B (o `title` en prosa de Intel) |
| Señal · polaridad | "Relevancia positive / informativo / negative" | "Señal **favorable** / **desfavorable** / **de alerta** / **informativa**" | I emite `polarity_label` ES · B traduce fallback |
| Señal · evidencia | "EVIDENCIA `ebitda_growth_yoy` · 0,24 · yoy" | **ocultar el campo crudo** (la descripción ya lo dice); si se quiere, "Base: crecimiento de EBITDA interanual" | B/I |
| Señal · scores | "Impacto 67% · Confianza 100% · Urgencia 40% · Persistencia 50%" | lectura **cualitativa** breve ("Impacto alto · confianza alta"); retirar los chips de % crudos | B (bandas alto/medio/bajo) |
| Señal · acciones | "→ analyze / → add_to_watchlist / → compare" | "**Analizar** / **Añadir a seguimiento** / **Comparar**" | B |
| Señal · "Regla ·" | "Regla · growth.ebitda_expansion" | **eliminar** (mecanismo interno) | B |
| Señal · tag categoría | "growth / market" | "**Crecimiento** / **Mercado**" | I `category_label` ES · B traduce |
| Sección · subtítulo | "…que Arroba ha detectado…" | "Hechos y cambios recientes que afectan al atractivo de la compañía para una operación." | B |
| Oportunidad · escala | "Puntuación 0–100 de cada tesis" | "Atractivo por tesis" (sin escala cruda; el número lo lleva la barra) | B |
| Oportunidad · tesis | `recommendation_type` crudo | nombre de la tesis en prosa | I/B |
| Oportunidad · acciones | "→ {action}" | acción en prosa ("Preparar teaser", "Buscar comprador"…) | B |

**Bandas cualitativas de score** (para Señales, análogo al percentil §5.bis): ≥80 "muy alto" · 60–79 "alto" ·
40–59 "moderado" · <40 "bajo". Se aplican a Impacto y Confianza; Urgencia/Persistencia se pueden omitir o
plegar. Estas secciones son **gated** (auth) → sin implicación DPD extra más allá del gate.

## 6. Definición de "hecho"
Ningún string de cara al usuario contiene: enums, códigos, acrónimos-etiqueta, nombres de mecanismos
o metodologías internas. Todo apartado con dato se lee como un párrafo de analista. Verificación:
grep del render (y del JSON servido) sin coincidencias de la lista del §2.
