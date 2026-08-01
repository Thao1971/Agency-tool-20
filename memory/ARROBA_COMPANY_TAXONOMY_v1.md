# ARROBA Company Taxonomy v1.0 (CANON)

> Taxonomía propia de ARROBA, en español, pensada para **búsqueda, análisis, comparables, matching y
> M&A** — NO una traducción del CNAE.
>
> **Regla rectora (congelada):** el CNAE describe la *actividad administrativa* de la sociedad; ARROBA
> clasifica el *negocio que realmente desarrolla*. Una empresa puede tener varias clasificaciones
> ARROBA, con una **principal** y otras **secundarias**.
>
> Estado: **estructura conceptual CONGELADA como v1.0**. Las 300–500 categorías finales NO se congelan
> palabra por palabra: el árbol se convierte en un **Taxonomy Registry versionado**; al clasificar las
> 24.992 empresas de Iberinform aparecerán huecos, solapamientos y categorías a dividir/fusionar.

## Modelo canónico
```
EMPRESA
├── Clasificación oficial
│     └── CNAE [1..n]
├── Clasificación ARROBA
│     ├── Sector [1..n]
│     ├── Industria [1..n]
│     └── Categoría [1..n]
├── Dimensiones transversales
│     ├── Verticales
│     ├── Capacidades
│     ├── Modelo de negocio
│     ├── Tipo de cliente
│     ├── Tecnología
│     └── Cadena de valor
├── Perfil semántico
└── Evidencias + confianza
```

## Nivel 1 — 11 Sectores

**S01 · Servicios Empresariales** — valor principal: prestar servicios profesionales/operativos/
especializados a otras organizaciones.
Industrias: Consultoría empresarial; Servicios profesionales; Recursos humanos; Servicios legales;
Auditoría y contabilidad; Ingeniería y servicios técnicos; Facility Management; BPO; Información
empresarial; Servicios de marketing.

**S02 · Tecnología** — producto principal basado en software, infraestructura digital, datos o tecnología.
Industrias: Software empresarial; Software financiero; Software de RRHH; Software comercial; Software de
marketing; Datos y analítica; Inteligencia artificial; Ciberseguridad; Cloud e infraestructura;
Desarrollo de software; Telecomunicaciones; Hardware y electrónica; Internet de las cosas; Automatización.

**S03 · Medios, Marketing y Comunicación** — clave para ARROBA: evita meter agencias, medios y AdTech
dentro de CNAE profesionales o tecnológicos.
Industrias: Agencias creativas; Agencias digitales; Branding y diseño; Agencias de medios; Marketing de
resultados; Martech; AdTech; Influencer Marketing; Relaciones públicas; Eventos y experiencias; Medios
digitales; Televisión y vídeo; Audio; Publicidad exterior; Investigación de mercados; Producción de
contenidos; Entretenimiento.

**S04 · Consumo y Retail** — Retail especializado; Gran distribución; Comercio electrónico; Moda y
accesorios; Belleza y cuidado personal; Hogar; Ocio y deporte; Servicios al consumidor; Restauración
organizada; Viajes y turismo; Hoteles.

**S05 · Salud y Ciencias de la Vida** — Industria farmacéutica; Biotecnología; Tecnología médica;
Diagnóstico; Hospitales; Atención ambulatoria; Dental; Salud mental; Residencias y dependencia;
HealthTech; CRO y servicios farmacéuticos; Distribución sanitaria; Salud animal.

**S06 · Industria** — Maquinaria; Automatización industrial; Componentes industriales; Automoción;
Aeroespacial y defensa; Química; Materiales; Packaging; Papel y productos forestales; Construcción;
Materiales de construcción; Equipamiento profesional; Mantenimiento industrial; Fabricación avanzada.

**S07 · Energía y Recursos Naturales** — Electricidad; Energías renovables; Servicios energéticos;
Oil & Gas; Gas; Almacenamiento energético; Hidrógeno; Gestión del agua; Residuos; Economía circular;
Minería; Servicios ambientales.

**S08 · Servicios Financieros** — Banca; Financiación; Pagos; Seguros; Mediación de seguros; Gestión de
activos; Capital privado; Crédito privado; Servicios de inversión; FinTech; InsurTech; RegTech;
Servicios financieros B2B.

**S09 · Inmobiliario e Infraestructuras** — Residencial; Oficinas; Retail inmobiliario; Industrial y
logística; Hoteles inmobiliarios; Activos alternativos; Promoción inmobiliaria; Gestión de activos;
Servicios inmobiliarios; PropTech; Infraestructuras; Infraestructura digital.

**S10 · Transporte y Logística** — Transporte terrestre; ferroviario; marítimo; aéreo; Logística;
Transitarios; Última milla; Mensajería; Movilidad; Tecnología logística; Infraestructuras de transporte.

**S11 · Alimentación y Agroindustria** — Agricultura; Ganadería; Pesca y acuicultura; Alimentación;
Bebidas; Panadería y dulces; Lácteos; Carne y proteínas; Ingredientes; Distribución alimentaria;
FoodTech; AgTech.

> Las categorías (nivel 3) de cada industria quedan en el Taxonomy Registry (ver §Versionado). El árbol
> completo con categorías de referencia por industria está en el mensaje fundacional de Daniel (2026-08-01).

## Dimensiones transversales (atraviesan sectores)
1. **Verticales** (screening/matching/tendencias): IA, SaaS, AdTech, MarTech, FinTech, InsurTech,
   HealthTech, BioTech, MedTech, LegalTech, HRTech, PropTech, EdTech, FoodTech, AgTech, ClimateTech,
   CleanTech, RetailTech, TravelTech, Cybersecurity, IoT, Robotics, MobilityTech, Creator Economy,
   Ecommerce, Digital Health, Industry 4.0. (Una empresa puede tener varias.)
2. **Modelo de negocio** (no mezclar con sector/monetización): B2B, B2C, B2B2C, B2G, SaaS, Suscripción,
   Licencia, Transaccional, Marketplace, Comisión, Publicidad, Servicios profesionales, Proyecto,
   Managed Services, Usage-based, Freemium, Hardware+Software, Distribución, Franquicia, Rental/Leasing.
   (Coexisten: p. ej. B2B + SaaS + Usage-based.)
3. **Tipo de cliente**: Grandes empresas, Mid-Market, PYME, Microempresa, AAPP, Consumidor, Agencias,
   Anunciantes, Publishers, Retailers, Instituciones financieras, Profesionales, Hospitales,
   Farmacéuticas, Industria, Distribuidores. (Ampliable por sector.)
4. **Tecnología** — distinguir `core_technology=true` de `technology_used=true`. *Una agencia que usa
   ChatGPT no es una empresa de IA; una cuyo producto depende de un modelo propio de IA sí.* Canónicas:
   IA, ML, IA generativa, Computer Vision, NLP, Big Data, Cloud, Blockchain, IoT, Robótica, AR/VR,
   Ciberseguridad, Edge Computing, 5G, Automatización, Low-Code, Digital Twin.
5. **Capacidades** — "¿qué sabe hacer?" (capa clave para M&A). Registro canónico propio. Ej. marketing:
   estrategia de marca, creatividad, compra de medios, performance, SEO, SEM, social, influencer, CRM,
   data analytics, programmatic, content, producción audiovisual, CX, commerce, loyalty. Ej. tech: data
   management, analytics, workflow automation, cybersecurity, cloud migration, software development,
   system integration, AI.
6. **Cadena de valor** (adquisiciones verticales): Fabricante, Desarrollador, Proveedor tecnológico,
   Distribuidor, Mayorista, Marketplace, Prestador de servicios, Integrador, Intermediario, Operador,
   Retailer, Propietario de activos, Gestor de activos.

## Regla de multiclasificación
Cada relación empresa↔taxonomía lleva: `taxonomy_id, role, confidence, evidence, source, classified_by,
classified_at, taxonomy_version`. `role ∈ {primary, secondary, adjacent}`. Una empresa puede ser
`sector S03 primary (0.97)` y `sector S02 secondary (0.88)` a la vez.

## Regla crítica — Primary Industry (doble modo de búsqueda)
ARROBA soporta **"Cualquier clasificación"** y **"Solo actividad principal"** (filtro "☐ Solo categoría
principal"). Imprescindible para usuarios profesionales.

## ARROBA Classification Fingerprint
No se reduce la empresa a una categoría: se construye una **huella** con la confianza por eje (Sector,
Industria, Vertical, Capacidades, Modelo de negocio, Cliente, Tecnología). La **similitud entre
fingerprints** alimenta: Similar Companies, Comparables, Matching, Buyer Fit, Roll-up Detection, Peer
Universe, Recommendation y Copilot. (Ventaja competitiva.)

## Peer Universe Resolver (obligatorio)
No se pueden usar automáticamente todas las empresas que comparten sector. Selecciona comparables por:
Categoría + Industria + Capacidades + Modelo de negocio + Vertical + Tamaño + Geografía + Perfil
semántico. (Una agencia creativa de 8 M€ no se compara con Publicis por estar ambas en S03.) Base para
que percentiles, márgenes, múltiplos y benchmarks tengan sentido.

## Filosofía de interfaz
Complejidad en el **Data Layer**, simplicidad en **ARROBA**. La ficha muestra: Actividad (industria →
sectores), Especialización (capacidades), Modelo, Tecnología; y en "Fuentes", el CNAE. El usuario no ve
la arquitectura interna.

## Versionado y siguiente paso
- **Congelado v1.0:** regla rectora, modelo canónico, 11 sectores, 6 dimensiones, multiclasificación,
  Primary Industry, Fingerprint, Peer Universe Resolver, filosofía UI.
- **NO congelado:** las 300–500 categorías finales → **Taxonomy Registry versionado**.
- **Roadmap recomendado (Daniel):** construir en Agency Tool el **Taxonomy Registry v1 + Company
  Classification Engine** → primera clasificación de las **24.992** compañías de Iberinform → auditar
  **100–200** empresas → iterar el árbol antes de escalar. Ahí la taxonomía deja de ser documento y pasa
  a ser infraestructura intelectual propia de ARROBA.

_Origen: mensaje fundacional de Daniel, 2026-08-01._
