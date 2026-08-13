# Redistribución de la pestaña RESUMEN (v2)

> Basado en los apuntes de Daniel + imágenes de referencia (cabecera modelo "Grupo Olmedo", card de resumen
> en prosa, veredicto → "Tesis de oportunidad"). Reglas de siempre: CF, DPD, R15 (dato real o Empty),
> explicabilidad (tooltips), deploy con purga. Toca **Intel (dato)** + **Beta (layout)**.

## Orden nuevo (de arriba a abajo)
1. **Cabecera** (reordenada)
2. **KPIs** (subidos arriba)
3. **Resumen de compañía** (prosa)
4. **Tesis de oportunidad** (ex "Veredicto de ARROBA")
5. **Detalles de la compañía** (ex "Identificación")
6. **Diagnóstico de ARROBA** (scores, sin marco azul)
7. **Evolución financiera** (gráfico, al final)

---

## 1 · Cabecera
- **Badges** junto al nombre: **"Verificada"** (verde) cuando el dato esté verificado; **"Auditada · {auditor}"**
  cuando conste auditor (nombre del auditor, del órgano de gobierno / rol auditor).
- **Subtítulo**: `Razón social · CIF · [actividad EN ESPAÑOL] · Localidad (Provincia) · URL clicable ↗ · [icono LinkedIn]`.
  - Actividad **en español** (etiqueta CNAE ES), no el literal inglés actual ("Manufacture of…").
  - **URL clicable** (abre en pestaña nueva).
  - **Icono LinkedIn** con enlace **solo si tenemos la URL real** (no se construye — ver nota LinkedIn).
- **Fila de OPORTUNIDADES**: chips de las tesis activas (p. ej. "Buy & Build · Captación de capital · Entrada de
  socio") desde el motor de oportunidades/recomendación. Gated (tras sesión).
- **Intel**: flag `verified`; nombre del auditor; actividad CNAE ES; URL LinkedIn (enrichment) si existe; tesis
  de oportunidad (chips). **Beta**: render de badges + subtítulo + chips.

## 2 · KPIs (arriba)
- Set: **Facturación · EBITDA · Deuda neta/EBITDA · Activos totales.** (Sustituye el set actual; salen Resultado
  neto y Empleados del bloque principal.)
- Cada KPI: **tooltip** (glosario) + **mini-gráfico de comparación con el año anterior** (sparkline o ▲▼ YoY).
- Donde `DN/EBITDA` no exista (sin deuda o sin EBITDA) → Empty honesto.
- **Resultado neto + Empleados** NO se eliminan: bajan de jerarquía y se muestran en la card "Detalles de la compañía".
- **Intel**: `DN/EBITDA` y `activos totales` ya en `finances` (confirmar). **Beta**: nuevo set + sparkline YoY.

## 3 · Resumen de compañía (prosa · card estilo oscuro)
- **La IA solo REFORMULA dato real, no inventa.** Su papel es convertir el objeto social legalero + actividad en
  prosa legible ("Compra, venta, importación…" → "Servier fabrica y comercializa especialidades farmacéuticas…"),
  no describir la empresa de la nada. Se le pasan datos reales (objeto social, CNAE, sector) y los resume.
- **Cascada de fuente** (primera que exista):
  1. Campo `description` de **Iberinform** (si es prosa legible).
  2. **IA (Nvidia) reformulando el objeto social / actividad** en prosa CF.
  3. **Búsqueda web** (texto "about" real de la empresa).
  4. **LinkedIn** (si tenemos su página).
- **Disclaimer** al final **cuando el texto proceda de IA o web** (no cuando sea `description`/objeto social oficial):
  *"Descripción generada/recopilada por IA a partir de fuentes públicas; puede contener imprecisiones sobre
  personas, lugares, hechos o cifras. Tómala como orientativa."*
- **Intel**: la cascada (IA reformula + web + LinkedIn) + un **flag de origen** del texto (`official` / `ai` / `web`)
  para saber si mostrar disclaimer. **Beta**: render de la card + disclaimer condicional según el flag.

## 4 · Tesis de oportunidad (ex "Veredicto de ARROBA")
- **Rebautizar** "Veredicto de ARROBA" → **"Tesis de oportunidad"**, en el **mismo bloque** pero **visualmente
  diferenciada** (pill/tarjeta destacada, estilo image4).
- **Contenido**: combinar **contexto sectorial + posicionamiento + veredicto financiero** en **prosa coherente**
  vía **motor semántico**, que explique en qué situación está la compañía, su posicionamiento y por qué es (o no)
  una oportunidad. Más explicabilidad que el veredicto actual.
- **Intel**: el motor semántico produce la tesis combinada (sector + posición + veredicto). **Beta**: render destacado.

## 5 · Detalles de la compañía (ex "Identificación")
- **Rename** "Identificación" → **"Detalles de la compañía"**. Mismo contenido registral. (Beta.)

## 6 · Diagnóstico de ARROBA (scores)
- Los anillos/scores con **explicación detallada** de qué significan (tooltip + copy), y **sin el marco azul**
  actual. (Beta; el copy de cada score va al glosario.)

## 7 · Evolución financiera
- El gráfico de evolución, **al final** del Resumen. (Beta: mover.)

---

## Nota LinkedIn
Las URLs de empresa de LinkedIn (`linkedin.com/company/{slug}`) usan un **slug arbitrario**, no derivable del
nombre ni del CIF → **no se construye**. Se muestra el icono **solo** si tenemos la URL real (enrichment/búsqueda).
Sin URL → sin icono.

## Reparto
- **Intel**: `verified` flag · auditor · actividad CNAE ES en identidad · `DN/EBITDA` + `activos totales` en KPIs ·
  cascada de descripción (web + Nvidia + LinkedIn) con flag de origen · tesis de oportunidad (semántico) · chips de
  oportunidades · URL LinkedIn si existe.
- **Beta**: reorden de bloques · cabecera (badges + subtítulo ES + URL + icono LinkedIn condicional + chips) · KPI
  set nuevo con sparkline · card de resumen con disclaimer condicional · tesis card destacada · rename "Detalles" ·
  scores sin marco azul · evolución al final.

## Decisiones ratificadas (Daniel · 2026-08-13)
1. **IA (Nvidia) = reformula, no inventa.** Se usa para convertir en prosa CF el **objeto social/actividad reales**
   (no describir de la nada). Cascada: `description` Iberinform → IA reformula objeto social → web → LinkedIn.
   Disclaimer solo con origen `ai`/`web`. Nunca marcar el texto IA como verificado.
2. **KPIs = Facturación · EBITDA · DN/EBITDA · Activos totales.** DN/EBITDA sin dato → Empty. **Resultado neto y
   Empleados no se pierden**: bajan a la card "Detalles de la compañía".
3. **Chips ≠ Tesis (son complementarias):** las **chips** de la cabecera = el *qué* (tipos de tesis: Buy & Build,
   Captación de capital, Entrada de socio, del motor de oportunidades); la **"Tesis de oportunidad"** en prosa = el
   *por qué* (sector + posición + veredicto, vía semántico) que **justifica** las chips.
4. **"Verificada" = cuentas depositadas y verificadas en fuente oficial** (`has_financials:true`, origen registral/
   Iberinform; no web/IA). Acotada a las cuentas, no "lo hemos comprobado todo". **"Auditada · {auditor}"** desde el
   rol auditor del órgano de gobierno.
