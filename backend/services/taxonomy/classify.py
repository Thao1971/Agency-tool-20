"""Company Classification Engine v1 (determinista). Combina el ancla CNAE→ARROBA con reglas de
alias/semántica sobre nombre + perfil, produce clasificación MULTICLASE (sector/industria/categoría +
dimensiones) con evidencia y confianza, distingue core_technology vs technology_used, calcula un
Fingerprint y persiste de forma idempotente. IA opcional (fase posterior). Fact-lock: no inventa.
Ver memory/ARROBA_TAXONOMY_ENGINE_DESIGN.md (P0–P5)."""

import re
import unicodedata
from typing import Dict, List, Optional

from services.taxonomy import TAXONOMY_VERSION
from services.taxonomy import registry as REG
from services.taxonomy import bridge as BRIDGE

CLASSIFIER_VERSION = "company-classification-engine-v1.3"

# ── Config (versionada)
W = {"cnae_section": 0.55, "division_industry": 0.6, "kw_industry": 0.55, "kw_category": 0.45,
     "prop_ind_to_sector": 0.4, "prop_cat_to_ind": 0.4, "dim": 0.6, "sector_label": 0.3}
KEEP, SECONDARY = 0.4, 0.6   # umbrales de rol
_TECH_SECTORS = {"S02"}

# Alias de alta señal por id de nodo/dimensión (además de la etiqueta). Se ampliará con la clasificación.
ALIASES: Dict[str, List[str]] = {
    # ── S01 Servicios Empresariales
    "IND-S01-consultoria-empresarial": ["consultoria", "consulting", "consultora", "asesoramiento estrategico",
                                        "consultancy", "business consulting"],
    "IND-S01-servicios-profesionales": ["servicios profesionales", "outsourcing"],
    "IND-S01-recursos-humanos": ["recursos humanos", "seleccion de personal", "ett", "trabajo temporal",
                                 "headhunting", "executive search", "reclutamiento"],
    "IND-S01-servicios-legales": ["despacho de abogados", "abogados", "bufete", "asesoria juridica", "legal"],
    "IND-S01-auditoria-y-contabilidad": ["auditoria", "contabilidad", "asesoria fiscal", "gestoria",
                                         "asesoria contable", "nominas", "accounting", "auditing",
                                         "bookkeeping", "tax consultancy"],
    "IND-S01-ingenieria-y-servicios-tecnicos": ["ingenieria", "arquitectura", "inspeccion", "certificacion",
                                                "project management"],
    "IND-S01-facility-management": ["facility management", "limpieza", "mantenimiento de edificios",
                                    "seguridad privada", "servicios integrales", "conserjeria"],
    "IND-S01-bpo": ["bpo", "contact center", "call center", "back office", "atencion al cliente"],
    "IND-S01-informacion-empresarial": ["informacion empresarial", "business information", "due diligence"],
    "IND-S01-servicios-de-marketing": ["investigacion de mercados", "field marketing", "promocion"],
    # ── S02 Tecnología
    "IND-S02-software-empresarial": ["saas", "software as a service", "plataforma software", "erp", "crm",
                                     "software de gestion", "aplicacion web", "plataforma cloud"],
    "IND-S02-software-financiero": ["software financiero", "software contable", "facturacion electronica"],
    "IND-S02-software-de-rrhh": ["software de rrhh", "hris", "software de nominas"],
    "IND-S02-datos-y-analitica": ["business intelligence", "analitica de datos", "data analytics",
                                  "big data", "cuadros de mando", "dashboards"],
    "IND-S02-inteligencia-artificial": ["inteligencia artificial", "machine learning", "deep learning",
                                        "aprendizaje automatico", "vision artificial", "ia generativa",
                                        "artificial intelligence"],
    "IND-S02-ciberseguridad": ["ciberseguridad", "cybersecurity", "seguridad informatica", "soc", "pentesting",
                               "cyber security"],
    "IND-S02-cloud-e-infraestructura": ["cloud computing", "hosting", "servidores", "devops", "infraestructura it",
                                        "data processing", "data center", "web portals"],
    "IND-S02-desarrollo-de-software": ["desarrollo de software", "software factory", "programacion informatica",
                                       "desarrollo web", "desarrollo de aplicaciones", "software a medida",
                                       "software development", "computer programming"],
    "IND-S02-telecomunicaciones": ["telecomunicaciones", "operador de telefonia", "redes", "fibra optica"],
    "IND-S02-hardware-y-electronica": ["hardware", "electronica", "sensores", "semiconductores"],
    "IND-S02-internet-de-las-cosas": ["internet de las cosas", "iot", "smart buildings", "telemetria"],
    "IND-S02-automatizacion": ["rpa", "automatizacion de procesos", "process mining"],
    # ── S03 Medios, Marketing y Comunicación
    "IND-S03-agencias-creativas": ["agencia creativa", "agencia de publicidad", "agencia publicitaria",
                                   "publicidad"],
    "IND-S03-agencias-digitales": ["agencia digital", "marketing digital", "marketing online"],
    "IND-S03-branding-y-diseno": ["branding", "diseno grafico", "identidad corporativa", "estudio de diseno"],
    "IND-S03-agencias-de-medios": ["agencia de medios", "compra de medios", "planificacion de medios",
                                   "media agency"],
    "IND-S03-marketing-de-resultados": ["performance marketing", "sem", "paid media", "captacion de leads",
                                        "afiliacion"],
    "IND-S03-martech": ["martech", "marketing automation", "customer data platform", "cdp"],
    "IND-S03-adtech": ["adtech", "publicidad programatica", "programmatic", "ad server", "dsp", "ssp",
                       "publicidad contextual"],
    "IND-S03-influencer-marketing": ["influencer marketing", "influencers", "creator economy"],
    "IND-S03-relaciones-publicas": ["relaciones publicas", "comunicacion corporativa", "gabinete de prensa",
                                    "public affairs"],
    "IND-S03-eventos-y-experiencias": ["organizacion de eventos", "eventos corporativos", "activaciones"],
    "IND-S03-medios-digitales": ["medios digitales", "portal de noticias", "publisher", "revista digital"],
    "IND-S03-television-y-video": ["productora audiovisual", "produccion audiovisual", "television", "video"],
    "IND-S03-audio": ["radio", "podcast", "audio digital"],
    "IND-S03-publicidad-exterior": ["publicidad exterior", "ooh", "dooh", "vallas publicitarias"],
    "IND-S03-investigacion-de-mercados": ["investigacion de mercados", "estudios de mercado", "consumer insights"],
    "IND-S03-produccion-de-contenidos": ["branded content", "produccion de contenidos", "content"],
    "IND-S03-entretenimiento": ["entretenimiento", "gaming", "videojuegos", "musica", "espectaculos"],
    # ── S04 Consumo y Retail
    "IND-S04-retail-especializado": ["tienda", "comercio minorista", "retail", "cadena de tiendas"],
    "IND-S04-gran-distribucion": ["supermercado", "hipermercado", "gran distribucion", "cadena de alimentacion"],
    "IND-S04-comercio-electronico": ["ecommerce", "comercio electronico", "tienda online", "venta online", "d2c"],
    "IND-S04-moda-y-accesorios": ["moda", "textil", "calzado", "complementos", "ropa"],
    "IND-S04-belleza-y-cuidado-personal": ["cosmetica", "perfumeria", "belleza", "cuidado personal"],
    "IND-S04-hogar": ["mobiliario", "muebles", "decoracion", "electrodomesticos"],
    "IND-S04-ocio-y-deporte": ["articulos deportivos", "deporte", "fitness", "outdoor"],
    "IND-S04-restauracion-organizada": ["restaurante", "restauracion", "hosteleria", "cafeteria", "delivery",
                                        "comida rapida"],
    "IND-S04-viajes-y-turismo": ["agencia de viajes", "turismo", "tour operador", "travel"],
    "IND-S04-hoteles": ["hotel", "hoteles", "resort", "aparthotel", "alojamiento"],
    # ── S05 Salud
    "IND-S05-industria-farmaceutica": ["farmaceutica", "laboratorio farmaceutico", "pharma", "medicamentos",
                                       "pharmaceutical", "manufacture of pharmaceutical"],
    "IND-S05-biotecnologia": ["biotecnologia", "biotech", "biotechnology"],
    "IND-S05-tecnologia-medica": ["tecnologia medica", "medtech", "dispositivos medicos", "equipamiento medico",
                                  "medical devices"],
    "IND-S05-diagnostico": ["laboratorio de analisis", "diagnostico", "imagen medica"],
    "IND-S05-hospitales": ["hospital", "clinica", "centro medico", "centro sanitario"],
    "IND-S05-atencion-ambulatoria": ["centro medico", "policlinica", "atencion primaria"],
    "IND-S05-dental": ["clinica dental", "dental", "odontologia"],
    "IND-S05-salud-mental": ["salud mental", "psicologia", "terapia"],
    "IND-S05-residencias-y-dependencia": ["residencia de mayores", "geriatrico", "dependencia", "ayuda a domicilio"],
    "IND-S05-healthtech": ["healthtech", "salud digital", "telemedicina"],
    "IND-S05-salud-animal": ["veterinaria", "salud animal", "clinica veterinaria"],
    # ── S06 Industria
    "IND-S06-maquinaria": ["maquinaria industrial", "fabricante de maquinaria", "bienes de equipo"],
    "IND-S06-automatizacion-industrial": ["robotica industrial", "automatizacion industrial", "control industrial"],
    "IND-S06-componentes-industriales": ["componentes industriales", "piezas", "fabricacion de componentes"],
    "IND-S06-automocion": ["automocion", "componentes de automocion", "recambios", "aftermarket"],
    "IND-S06-aeroespacial-y-defensa": ["aeronautica", "aeroespacial", "defensa"],
    "IND-S06-quimica": ["quimica", "industria quimica", "productos quimicos"],
    "IND-S06-materiales": ["metalurgia", "siderurgia", "vidrio", "ceramica"],
    "IND-S06-packaging": ["packaging", "envases", "embalaje"],
    "IND-S06-construccion": ["constructora", "construccion", "obra civil", "edificacion", "reformas",
                             "rehabilitacion", "construction", "civil engineering"],
    "IND-S06-materiales-de-construccion": ["cemento", "hormigon", "materiales de construccion", "aislamiento"],
    "IND-S06-mantenimiento-industrial": ["mantenimiento industrial", "mro"],
    # ── S07 Energía y Recursos Naturales
    "IND-S07-electricidad": ["electricidad", "comercializadora electrica", "distribucion electrica"],
    "IND-S07-energias-renovables": ["energias renovables", "fotovoltaica", "solar", "eolica", "biomasa"],
    "IND-S07-servicios-energeticos": ["eficiencia energetica", "esco", "servicios energeticos"],
    "IND-S07-oil-gas": ["petroleo", "gas", "hidrocarburos"],
    "IND-S07-gestion-del-agua": ["gestion del agua", "tratamiento de aguas", "depuracion", "desalacion"],
    "IND-S07-residuos": ["gestion de residuos", "reciclaje", "recogida de residuos"],
    "IND-S07-mineria": ["mineria", "extraccion", "cantera"],
    "IND-S07-servicios-ambientales": ["consultoria ambiental", "medio ambiente", "descontaminacion"],
    # ── S08 Servicios Financieros
    "IND-S08-banca": ["banco", "banca", "entidad financiera", "banking"],
    "IND-S08-financiacion": ["financiacion", "prestamos", "leasing", "renting", "credito al consumo",
                             "lending", "other lending activities"],
    "IND-S08-pagos": ["pagos", "medios de pago", "pasarela de pago", "tpv", "digital payments", "payment services"],
    "IND-S08-seguros": ["aseguradora", "compania de seguros", "seguros"],
    "IND-S08-mediacion-de-seguros": ["correduria de seguros", "corredor de seguros", "mediacion de seguros"],
    "IND-S08-gestion-de-activos": ["gestora de fondos", "gestion de activos", "asset management", "sgiic"],
    "IND-S08-capital-privado": ["private equity", "capital riesgo", "venture capital", "capital privado"],
    "IND-S08-servicios-de-inversion": ["sociedad de valores", "broker", "servicios de inversion"],
    "IND-S08-fintech": ["fintech", "neobanco", "financial technology"],
    "IND-S08-insurtech": ["insurtech"],
    # ── S09 Inmobiliario e Infraestructuras
    "IND-S09-residencial": ["vivienda residencial", "build to rent", "alquiler residencial"],
    "IND-S09-oficinas": ["oficinas", "espacios de trabajo", "coworking"],
    "IND-S09-industrial-y-logistica": ["naves logisticas", "naves industriales", "logistics property"],
    "IND-S09-promocion-inmobiliaria": ["promotora inmobiliaria", "promocion inmobiliaria", "desarrollo inmobiliario"],
    "IND-S09-gestion-de-activos": ["property management", "gestion de patrimonio inmobiliario"],
    "IND-S09-servicios-inmobiliarios": ["inmobiliaria", "agencia inmobiliaria", "real estate", "tasacion",
                                        "intermediacion inmobiliaria", "renting of real estate"],
    "IND-S09-proptech": ["proptech"],
    "IND-S09-infraestructuras": ["infraestructuras", "concesiones", "autopistas"],
    "IND-S09-infraestructura-digital": ["data center", "centro de datos", "torres de telecomunicaciones"],
    # ── S10 Transporte y Logística
    "IND-S10-transporte-terrestre": ["transporte por carretera", "transporte terrestre", "camiones",
                                     "transporte de mercancias"],
    "IND-S10-transporte-maritimo": ["transporte maritimo", "naviera", "shipping"],
    "IND-S10-transporte-aereo": ["aerolinea", "transporte aereo", "carga aerea"],
    "IND-S10-logistica": ["logistica", "operador logistico", "almacenaje", "3pl", "distribucion"],
    "IND-S10-transitarios": ["transitario", "freight forwarding", "agente de aduanas"],
    "IND-S10-ultima-milla": ["ultima milla", "reparto urbano", "last mile"],
    "IND-S10-mensajeria": ["mensajeria", "paqueteria", "courier", "envio urgente"],
    "IND-S10-movilidad": ["movilidad", "vtc", "carsharing", "movilidad compartida"],
    "IND-S10-tecnologia-logistica": ["software logistico", "tms", "gestion de flotas"],
    # ── S11 Alimentación y Agroindustria
    "IND-S11-agricultura": ["agricultura", "explotacion agricola", "cultivos"],
    "IND-S11-ganaderia": ["ganaderia", "explotacion ganadera", "avicultura"],
    "IND-S11-pesca-y-acuicultura": ["pesca", "acuicultura", "piscifactoria"],
    "IND-S11-alimentacion": ["industria alimentaria", "alimentacion", "procesado de alimentos", "conservas"],
    "IND-S11-bebidas": ["bebidas", "bodega", "vino", "cerveza", "refrescos"],
    "IND-S11-panaderia-y-dulces": ["panaderia", "pasteleria", "reposteria", "snacks"],
    "IND-S11-lacteos": ["lacteos", "quesos", "productos lacteos"],
    "IND-S11-carne-y-proteinas": ["carnica", "matadero", "procesado carnico"],
    "IND-S11-distribucion-alimentaria": ["distribucion alimentaria", "mayorista de alimentacion"],
    "IND-S11-foodtech": ["foodtech"],
    "IND-S11-agtech": ["agtech", "agricultura de precision"],
    # ── Dimensiones · Verticales
    "DIM-verticals-adtech": ["adtech", "publicidad programatica", "publicidad contextual", "programmatic"],
    "DIM-verticals-martech": ["martech", "marketing automation"],
    "DIM-verticals-saas": ["saas", "software as a service"],
    "DIM-verticals-inteligencia-artificial": ["inteligencia artificial", "machine learning", "ia generativa"],
    "DIM-verticals-fintech": ["fintech"],
    "DIM-verticals-insurtech": ["insurtech"],
    "DIM-verticals-healthtech": ["healthtech", "salud digital"],
    "DIM-verticals-proptech": ["proptech"],
    "DIM-verticals-ecommerce": ["ecommerce", "comercio electronico"],
    "DIM-verticals-cybersecurity": ["ciberseguridad", "cybersecurity"],
    "DIM-verticals-foodtech": ["foodtech"],
    "DIM-verticals-agtech": ["agtech"],
    # ── Dimensiones · Modelo de negocio
    "DIM-business_models-saas": ["saas", "suscripcion software"],
    "DIM-business_models-b2b": ["b2b", "para empresas"],
    "DIM-business_models-b2c": ["b2c", "consumidor final"],
    "DIM-business_models-marketplace": ["marketplace"],
    "DIM-business_models-suscripcion": ["suscripcion", "cuota mensual", "membresia"],
    "DIM-business_models-franquicia": ["franquicia"],
    "DIM-business_models-rental-leasing": ["renting", "leasing", "alquiler de equipos"],
    "DIM-business_models-servicios-profesionales": ["servicios profesionales", "consultoria"],
    # ── Dimensiones · Tipo de cliente
    "DIM-client_types-administraciones-publicas": ["administracion publica", "sector publico", "b2g"],
    "DIM-client_types-pyme": ["pymes", "pequenas y medianas empresas"],
    "DIM-client_types-grandes-empresas": ["grandes empresas", "grandes cuentas"],
    # ── Dimensiones · Tecnología (core)
    "DIM-technologies-inteligencia-artificial": ["inteligencia artificial", "machine learning", "ia generativa"],
    "DIM-technologies-cloud": ["cloud", "nube"],
    "DIM-technologies-blockchain": ["blockchain"],
    "DIM-technologies-iot": ["iot", "internet de las cosas"],
    "DIM-technologies-big-data": ["big data", "datos masivos"],
}


# v1.3 — alias en INGLÉS (los cnae_description reales vienen en inglés). Se fusionan en ALIASES sin
# sobrescribir (setdefault+extend). Cubren los patrones más frecuentes del triaje de baja confianza.
ALIASES_EN: Dict[str, List[str]] = {
    "IND-S04-gran-distribucion": ["wholesale trade", "wholesale", "comercio al por mayor"],
    "IND-S04-retail-especializado": ["retail trade", "retail sale", "comercio al por menor"],
    "IND-S06-automocion": ["motor vehicles", "repair and maintenance of motor vehicles",
                           "sale of motor vehicles", "motorcycles"],
    "IND-S03-entretenimiento": ["gambling", "betting", "gambling and betting"],
    "IND-S11-agricultura": ["crops", "cultivation", "growing of", "non-perennial crops",
                            "perennial crops"],
    "IND-S11-ganaderia": ["raising of", "animal production", "livestock"],
    "IND-S11-pesca-y-acuicultura": ["fishing", "aquaculture"],
    "IND-S06-materiales": ["metal products", "fabricated metal", "basic metals", "manufacture of metal"],
    "IND-S06-papel-y-productos-forestales": ["manufacture of wood", "wood", "paper", "forestry"],
    "IND-S06-maquinaria": ["manufacture of machinery", "machinery and equipment"],
    "IND-S06-construccion": ["construction", "building construction", "specialized construction",
                             "civil engineering"],
    "IND-S06-quimica": ["manufacture of chemicals", "chemical products", "manufacture of plastics",
                        "plastics in primary forms", "rubber and plastic"],
    "IND-S11-bebidas": ["brewing", "manufacture of beer", "distilling", "manufacture of wine", "soft drinks"],
    "IND-S11-panaderia-y-dulces": ["manufacture of bread", "bakery products", "cocoa, chocolate"],
    "IND-S11-carne-y-proteinas": ["processing and preserving of meat", "meat products"],
    "IND-S07-mineria": ["quarrying", "mining", "extraction of"],
    "IND-S01-facility-management": ["general cleaning of buildings", "cleaning of buildings",
                                    "cleaning activities", "landscape service"],
    "IND-S10-transporte-terrestre": ["freight transport by road", "road transport"],
    "IND-S10-logistica": ["warehousing", "storage"],
    "IND-S01-servicios-legales": ["legal activities"],
    "IND-S01-auditoria-y-contabilidad": ["accounting", "bookkeeping", "auditing", "tax consultancy"],
    "IND-S01-consultoria-empresarial": ["management consultancy", "business consultancy"],
    "IND-S01-ingenieria-y-servicios-tecnicos": ["engineering activities", "technical testing", "architecture"],
    "IND-S04-restauracion-organizada": ["restaurants", "food and beverage service", "catering"],
    "IND-S04-hoteles": ["hotels and similar accommodation", "accommodation"],
    "IND-S05-industria-farmaceutica": ["pharmaceutical", "pharmaceutical preparations"],
    "IND-S05-hospitales": ["hospital activities"],
    "IND-S08-banca": ["monetary intermediation", "banking"],
    "IND-S08-seguros": ["insurance", "life insurance", "non-life insurance"],
    "IND-S09-servicios-inmobiliarios": ["real estate activities", "real estate agencies"],
    "IND-S09-promocion-inmobiliaria": ["buying and selling of real estate", "development of building projects"],
}
for _k, _v in ALIASES_EN.items():
    ALIASES.setdefault(_k, [])
    for _t in _v:
        if _t not in ALIASES[_k]:
            ALIASES[_k].append(_t)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip() + " "


# ── Índices (una vez)
def _build_index():
    nodes = REG.build_nodes()
    node = {n["id"]: n for n in nodes}
    kw_nodes = []   # (kw_norm, node_id, level, sector_id, industry_id)
    for n in nodes:
        if n["level"] == "sector":
            continue
        sector_id = n["id"].split("-")[1] if n["level"] in ("industry", "category") else None
        industry_id = n["parent_id"] if n["level"] == "category" else n["id"]
        seen = set()
        for kw in [n["label_es"]] + ALIASES.get(n["id"], []):
            nk = _norm(kw).strip()
            if len(nk) >= 4 and nk not in seen:
                seen.add(nk)
                kw_nodes.append((nk, n["id"], n["level"], sector_id, industry_id))
    dims = REG.build_dimensions()
    kw_dims = []    # (kw_norm, dimension, dim_id, label)
    for d in dims:
        seen = set()
        for kw in [d["label_es"]] + ALIASES.get(d["id"], []):
            nk = _norm(kw).strip()
            if len(nk) >= 3 and nk not in seen:
                seen.add(nk)
                kw_dims.append((nk, d["dimension"], d["id"], d["label_es"]))
    sec_labels = {s["id"]: s["label_es"] for s in nodes if s["level"] == "sector"}
    return kw_nodes, kw_dims, node, sec_labels


_KW_NODES, _KW_DIMS, _NODE, _SEC_LABELS = _build_index()


def _add(scores: Dict, ev: Dict, key: str, w: float, source: str, detail: str):
    scores[key] = scores.get(key, 0.0) + w
    ev.setdefault(key, []).append({"source": source, "detail": detail, "weight": w})


def _rows(axis: str, scores: Dict, ev: Dict, label_of) -> List[Dict]:
    ranked = sorted(((k, min(0.99, round(v, 2))) for k, v in scores.items() if v >= KEEP),
                    key=lambda x: -x[1])
    out = []
    for i, (k, conf) in enumerate(ranked):
        role = "primary" if i == 0 else ("secondary" if conf >= SECONDARY else "adjacent")
        out.append({"axis": axis, "taxonomy_id": k, "label_es": label_of(k), "role": role,
                    "confidence": conf, "evidence": ev.get(k, [])})
    return out


async def _semantic_text(company_id: Optional[str]) -> str:
    """Señal de clasificación desde el Semantic Engine (perfil web/negocio). Best-effort; '' si no hay."""
    if not company_id:
        return ""
    try:
        from services.engines.semantic import persistence as _SP
        from services.engines.semantic import profile as _PR
        p = await _SP.get(company_id)
        return _PR.embedding_text(p) if p else ""
    except Exception:
        return ""


async def classify(request: Dict) -> Dict:
    inputs = request.get("inputs") or {}
    company_id = request.get("company_id") or inputs.get("company_id") or inputs.get("master_id")
    cnaes = inputs.get("cnae") or inputs.get("cnaes") or []
    if isinstance(cnaes, str):
        cnaes = [cnaes]
    name = inputs.get("name") or (inputs.get("identity") or {}).get("name") or ""
    desc = inputs.get("description") or inputs.get("profile_text") or inputs.get("objeto_social") or ""
    # Señal semántica real (perfil del Semantic Engine) salvo que se aporte inline o se desactive.
    sem = inputs.get("semantic_text") or ""
    if not sem and request.get("use_semantic", True):
        sem = await _semantic_text(company_id)
    hay = _norm(f"{name} {desc} {sem}")

    sec, ind, cat, ev = {}, {}, {}, {}
    dim_scores = {d: {} for d in ("verticals", "business_models", "client_types", "technologies",
                                  "value_chain", "capabilities")}
    dim_ev = {}

    # P1a — ancla CNAE
    for code in cnaes:
        s_id, ind_label = BRIDGE.anchor_from_cnae(code)
        if s_id:
            _add(sec, ev, s_id, W["cnae_section"], "cnae", f"CNAE {code}")
            if ind_label:
                iid = REG.industry_id(s_id, ind_label)
                _add(ind, ev, iid, W["division_industry"], "cnae", f"CNAE {code} → {ind_label}")
                _add(sec, ev, s_id, W["prop_ind_to_sector"], "cnae", f"industria {ind_label}")

    # P1b — reglas de alias/semántica (nombre + perfil)
    for kw, nid, level, sector_id, industry_id in _KW_NODES:
        if kw in hay:
            if level == "industry":
                _add(ind, ev, nid, W["kw_industry"], "rules", f"'{kw.strip()}'")
                if sector_id:
                    _add(sec, ev, sector_id, W["prop_ind_to_sector"], "rules", f"'{kw.strip()}'")
            elif level == "category":
                _add(cat, ev, nid, W["kw_category"], "rules", f"'{kw.strip()}'")
                if industry_id:
                    _add(ind, ev, industry_id, W["prop_cat_to_ind"], "rules", f"'{kw.strip()}'")
                if sector_id:
                    _add(sec, ev, sector_id, W["prop_ind_to_sector"] * 0.6, "rules", f"'{kw.strip()}'")
    for sid, label in _SEC_LABELS.items():
        if _norm(label).strip() in hay:
            _add(sec, ev, sid, W["sector_label"], "rules", label)

    # P1c — dimensiones transversales
    for kw, dimension, dim_id, label in _KW_DIMS:
        if kw in hay:
            _add(dim_scores[dimension], dim_ev, dim_id, W["dim"], "rules", f"'{kw.strip()}'")

    # Construcción de filas
    label_node = lambda k: (_NODE.get(k) or {}).get("label_es", k)
    sectors = _rows("sector", sec, ev, label_node)
    industries = _rows("industry", ind, ev, label_node)
    categories = _rows("category", cat, ev, label_node)
    primary_sector = sectors[0]["taxonomy_id"] if sectors else None

    dim_out = {}
    dim_label = {d["id"]: d["label_es"] for d in REG.build_dimensions()}
    for dimension, scores in dim_scores.items():
        rows = _rows(dimension, scores, dim_ev, lambda k: dim_label.get(k, k))
        # P3 — core vs used para tecnologías: la tecnología es NÚCLEO si el negocio es tecnológico
        # (sector Tecnología como principal o secundario fuerte), no por mera mención de uso.
        if dimension == "technologies":
            tech_business = (primary_sector in _TECH_SECTORS) or any(
                s["taxonomy_id"] in _TECH_SECTORS and s["confidence"] >= SECONDARY for s in sectors)
            for r in rows:
                r["core_technology"] = bool(tech_business and r["confidence"] >= SECONDARY)
        dim_out[dimension] = rows

    # P4 — Fingerprint (confianza del top por eje, 0..100)
    def _top(rows):
        return int(round(rows[0]["confidence"] * 100)) if rows else 0
    fingerprint = {"sector": _top(sectors), "industry": _top(industries),
                   "vertical": _top(dim_out["verticals"]), "capabilities": _top(dim_out["capabilities"]),
                   "business_model": _top(dim_out["business_models"]), "client": _top(dim_out["client_types"]),
                   "technology": _top(dim_out["technologies"])}
    overall = round(sum([fingerprint["sector"], fingerprint["industry"]]) / 200, 2)

    result = {"company_id": company_id, "taxonomy_version": TAXONOMY_VERSION,
              "classifier_version": CLASSIFIER_VERSION, "primary_sector": primary_sector,
              "classifications": {"sector": sectors, "industry": industries, "category": categories, **dim_out},
              "fingerprint": fingerprint, "overall_confidence": overall}
    if company_id:
        await _persist(company_id, result)
    return result


# ── Persistencia idempotente
_INDEXED = False


async def ensure_indexes():
    global _INDEXED
    if _INDEXED:
        return
    try:
        from database import db
        await db.company_classifications.create_index("company_id")
        await db.company_classifications.create_index([("axis", 1), ("taxonomy_id", 1)])
        await db.company_fingerprint.create_index("company_id", unique=True)
        _INDEXED = True
    except Exception:
        pass


async def _persist(company_id: str, result: Dict):
    try:
        from database import db
        from models import now_iso
        await ensure_indexes()
        now = now_iso()
        rows = []
        for axis, items in result["classifications"].items():
            for r in items:
                rows.append({"company_id": company_id, "axis": axis, "taxonomy_id": r["taxonomy_id"],
                             "label_es": r["label_es"], "role": r.get("role"),
                             "confidence": r["confidence"], "evidence": r.get("evidence", []),
                             "core_technology": r.get("core_technology"),
                             "source": "engine", "classified_at": now,
                             "taxonomy_version": TAXONOMY_VERSION, "classifier_version": CLASSIFIER_VERSION})
        # idempotente: reemplaza la clasificación de esta versión
        await db.company_classifications.delete_many(
            {"company_id": company_id, "taxonomy_version": TAXONOMY_VERSION})
        if rows:
            await db.company_classifications.insert_many(rows)
        await db.company_fingerprint.update_one({"company_id": company_id},
            {"$set": {"company_id": company_id, "fingerprint": result["fingerprint"],
                      "primary_sector": result["primary_sector"],
                      "overall_confidence": result["overall_confidence"],
                      "taxonomy_version": TAXONOMY_VERSION, "computed_at": now}}, upsert=True)
    except Exception:
        pass


async def get_company_classification(company_id: str) -> Dict:
    try:
        from database import db
        rows = [r async for r in db.company_classifications.find(
            {"company_id": company_id}, {"_id": 0}).sort("confidence", -1)]
        fp = await db.company_fingerprint.find_one({"company_id": company_id}, {"_id": 0})
        return {"company_id": company_id, "classifications": rows, "fingerprint": fp}
    except Exception:
        return {"company_id": company_id, "classifications": [], "fingerprint": None}
