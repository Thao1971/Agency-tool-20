"""ARROBA Taxonomy Registry v1 — árbol versionado (sectores → industrias → categorías base) +
dimensiones transversales. Ids estables autogenerados por slug. Siembra idempotente.

Ver memory/ARROBA_COMPANY_TAXONOMY_v1.md y ARROBA_TAXONOMY_ENGINE_DESIGN.md.
"""

import re
import unicodedata
from typing import Dict, List, Optional

from services.taxonomy import TAXONOMY_VERSION


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


# ── Árbol: {sector_id: {"label", "industries": {industria: [categorías base...]}}}
SEED: Dict[str, Dict] = {
    "S01": {"label": "Servicios Empresariales", "industries": {
        "Consultoría empresarial": ["Estrategia", "Operaciones", "Organización", "Transformación", "Innovación", "Consultoría tecnológica"],
        "Servicios profesionales": ["Servicios corporativos", "Outsourcing profesional", "Servicios técnicos", "Servicios especializados"],
        "Recursos humanos": ["Selección", "Executive Search", "Trabajo temporal", "RPO", "Formación corporativa", "HR Consulting"],
        "Servicios legales": ["Despachos", "Legal Services", "Legal Process Outsourcing", "Compliance", "Propiedad intelectual"],
        "Auditoría y contabilidad": ["Auditoría", "Contabilidad", "Asesoría fiscal", "Nóminas", "Servicios financieros externalizados"],
        "Ingeniería y servicios técnicos": ["Ingeniería", "Arquitectura", "Inspección", "Certificación", "Ensayos", "Project Management"],
        "Facility Management": ["Limpieza", "Mantenimiento", "Seguridad", "Servicios integrales", "Gestión de instalaciones"],
        "BPO": ["Contact Center", "Back Office", "Atención al cliente", "Procesamiento documental", "Outsourcing administrativo"],
        "Información empresarial": ["Business Information", "Credit Information", "Market Intelligence", "Due Diligence", "Datos empresariales"],
        "Servicios de marketing": ["Investigación de mercados", "Eventos", "Producción", "Promoción", "Field Marketing", "Loyalty"],
    }},
    "S02": {"label": "Tecnología", "industries": {
        "Software empresarial": ["ERP", "CRM", "Gestión documental", "Workflow", "Productividad", "Software vertical"],
        "Software financiero": ["Contabilidad", "Tesorería", "Facturación", "Gestión financiera", "FP&A"],
        "Software de RRHH": ["HRIS", "Nóminas", "Recruiting Software", "Workforce Management", "Employee Experience"],
        "Software comercial": ["Sales Tech", "Revenue Operations", "Customer Success", "Sales Enablement"],
        "Software de marketing": ["Marketing Automation", "CRM Marketing", "Personalización", "Loyalty Technology"],
        "Datos y analítica": ["Business Intelligence", "Data Analytics", "Data Platforms", "Data Management", "Data Visualization"],
        "Inteligencia artificial": ["IA generativa", "Machine Learning", "Computer Vision", "NLP", "Decision Intelligence"],
        "Ciberseguridad": ["Seguridad de red", "Identidad", "Cloud Security", "Endpoint", "SOC", "Fraud Detection"],
        "Cloud e infraestructura": ["Cloud Computing", "Hosting", "DevOps", "Infrastructure Software", "Edge Computing"],
        "Desarrollo de software": ["Software Development", "Outsourcing tecnológico", "QA", "Integración", "Low-Code"],
        "Telecomunicaciones": ["Operadores", "Redes", "Comunicaciones empresariales", "UCaaS", "CPaaS"],
        "Hardware y electrónica": ["Equipamiento", "IoT", "Sensores", "Electrónica profesional", "Semiconductores"],
        "Internet de las cosas": ["Industrial IoT", "Smart Buildings", "Connected Devices", "Telemetría"],
        "Automatización": ["RPA", "Workflow Automation", "Intelligent Automation", "Process Mining"],
    }},
    "S03": {"label": "Medios, Marketing y Comunicación", "industries": {
        "Agencias creativas": ["Publicidad", "Creatividad", "Campañas integradas", "Brand Advertising"],
        "Agencias digitales": ["Digital Full Service", "Experiencia digital", "Social", "Content"],
        "Branding y diseño": ["Branding", "Identidad", "Packaging", "Diseño gráfico", "Diseño estratégico"],
        "Agencias de medios": ["Planificación", "Compra de medios", "Performance Media", "Media Consulting"],
        "Marketing de resultados": ["Performance Marketing", "Paid Search", "Paid Social", "Affiliate Marketing", "Lead Generation"],
        "Martech": ["Marketing Automation", "Customer Data", "Personalización", "Loyalty", "Marketing Analytics"],
        "AdTech": ["DSP", "SSP", "Ad Server", "Programmatic", "Contextual Advertising", "Ad Verification"],
        "Influencer Marketing": ["Plataformas", "Agencias", "Creator Economy", "Influencer Technology"],
        "Relaciones públicas": ["Comunicación corporativa", "PR", "Public Affairs", "Crisis", "Comunicación financiera"],
        "Eventos y experiencias": ["Eventos corporativos", "Experiential", "Ferias", "Activaciones", "Producción"],
        "Medios digitales": ["Publishers", "Digital Media", "Portales", "Medios especializados"],
        "Televisión y vídeo": ["Televisión", "Producción audiovisual", "Streaming", "Vídeo digital"],
        "Audio": ["Radio", "Podcast", "Audio digital"],
        "Publicidad exterior": ["OOH", "DOOH", "Exclusivistas", "Mobiliario urbano", "Tecnología OOH"],
        "Investigación de mercados": ["Market Research", "Consumer Insights", "Social Listening", "Paneles"],
        "Producción de contenidos": ["Productoras", "Branded Content", "Content Studios", "Postproducción"],
        "Entretenimiento": ["Producción", "Distribución", "Gaming", "Música", "Espectáculos"],
    }},
    "S04": {"label": "Consumo y Retail", "industries": {
        "Retail especializado": ["Moda", "Electrónica", "Hogar", "Belleza", "Deporte", "Otros especialistas"],
        "Gran distribución": ["Supermercados", "Hipermercados", "Grandes almacenes"],
        "Comercio electrónico": ["Ecommerce generalista", "Ecommerce vertical", "D2C"],
        "Moda y accesorios": ["Apparel", "Calzado", "Complementos", "Lujo"],
        "Belleza y cuidado personal": ["Cosmética", "Perfumería", "Personal Care"],
        "Hogar": ["Mobiliario", "Decoración", "Electrodomésticos", "Equipamiento doméstico"],
        "Ocio y deporte": ["Sporting Goods", "Fitness Products", "Outdoor", "Hobbies"],
        "Servicios al consumidor": ["Reparación", "Servicios personales", "Suscripciones de consumo"],
        "Restauración organizada": ["Restauración", "Quick Service", "Casual Dining", "Delivery"],
        "Viajes y turismo": ["Agencias", "Tour Operators", "Travel Tech", "Experiencias"],
        "Hoteles": ["Hoteles", "Resorts", "Aparthoteles", "Hospitality Management"],
    }},
    "S05": {"label": "Salud y Ciencias de la Vida", "industries": {
        "Industria farmacéutica": ["Pharma", "Genéricos", "Specialty Pharma", "OTC"],
        "Biotecnología": ["Therapeutics", "Diagnostics", "Research Biotech"],
        "Tecnología médica": ["Medical Devices", "Equipamiento médico", "Instrumentación"],
        "Diagnóstico": ["Laboratorios", "Imaging", "Testing", "Molecular Diagnostics"],
        "Hospitales": ["Hospitales privados", "Clínicas", "Centros especializados"],
        "Atención ambulatoria": ["Clínicas", "Centros médicos", "Day Surgery"],
        "Dental": ["Clínicas dentales", "Laboratorios", "Dental Technology"],
        "Salud mental": ["Clínicas", "Terapia", "Digital Mental Health"],
        "Residencias y dependencia": ["Elder Care", "Residencias", "Home Care"],
        "HealthTech": ["Digital Health", "Telemedicina", "Healthcare Software"],
        "CRO y servicios farmacéuticos": ["Clinical Research", "Regulatory", "Pharmacovigilance"],
        "Distribución sanitaria": ["Distribución farmacéutica", "Medical Supplies"],
        "Salud animal": ["Veterinaria", "Animal Health", "Pet Health"],
    }},
    "S06": {"label": "Industria", "industries": {
        "Maquinaria": ["Maquinaria industrial", "Equipos especializados", "Machine Tools"],
        "Automatización industrial": ["Robotics", "Industrial Automation", "Control Systems"],
        "Componentes industriales": ["Componentes", "Piezas", "Subconjuntos"],
        "Automoción": ["Componentes", "Aftermarket", "Mobility Components"],
        "Aeroespacial y defensa": ["Aerospace", "Defence", "Components"],
        "Química": ["Specialty Chemicals", "Industrial Chemicals", "Coatings"],
        "Materiales": ["Metales", "Vidrio", "Cerámica", "Composites"],
        "Packaging": ["Flexible", "Cartón", "Plástico", "Vidrio", "Packaging especializado"],
        "Papel y productos forestales": ["Paper", "Tissue", "Forestry Products"],
        "Construcción": ["Construcción general", "Especialidades", "Rehabilitación"],
        "Materiales de construcción": ["Cemento", "Hormigón", "Cerámica", "Aislamiento"],
        "Equipamiento profesional": ["Equipamiento comercial", "Industrial Supplies"],
        "Mantenimiento industrial": ["MRO", "Industrial Services", "Field Services"],
        "Fabricación avanzada": ["Additive Manufacturing", "Precision Manufacturing"],
    }},
    "S07": {"label": "Energía y Recursos Naturales", "industries": {
        "Electricidad": ["Generación", "Distribución", "Comercialización"],
        "Energías renovables": ["Solar", "Eólica", "Hidráulica", "Biomasa"],
        "Servicios energéticos": ["ESCO", "Eficiencia energética", "Ingeniería energética"],
        "Oil & Gas": ["Exploración", "Servicios petroleros", "Distribución"],
        "Gas": ["Natural Gas", "LNG", "Infraestructuras"],
        "Almacenamiento energético": ["Baterías", "Storage Systems"],
        "Hidrógeno": ["Green Hydrogen", "Equipment", "Infrastructure"],
        "Gestión del agua": ["Abastecimiento", "Tratamiento", "Desalación"],
        "Residuos": ["Recogida", "Tratamiento", "Recycling", "Waste Tech"],
        "Economía circular": ["Recycling", "Reuse", "Resource Recovery"],
        "Minería": ["Mining", "Minerals", "Extraction"],
        "Servicios ambientales": ["Environmental Consulting", "Remediation", "Monitoring"],
    }},
    "S08": {"label": "Servicios Financieros", "industries": {
        "Banca": ["Retail Banking", "Corporate Banking", "Private Banking"],
        "Financiación": ["Consumer Finance", "SME Finance", "Asset Finance"],
        "Pagos": ["Payments", "Payment Processing", "Acquiring", "Wallets"],
        "Seguros": ["Vida", "No vida", "Salud", "Specialty Insurance"],
        "Mediación de seguros": ["Brokers", "Corredurías", "MGA"],
        "Gestión de activos": ["Asset Management", "Wealth Management"],
        "Capital privado": ["Private Equity", "Venture Capital", "Growth Equity"],
        "Crédito privado": ["Direct Lending", "Private Debt"],
        "Servicios de inversión": ["Brokerage", "Investment Services"],
        "FinTech": ["Embedded Finance", "Neobanking", "Banking Software"],
        "InsurTech": ["Insurance Software", "Digital Insurance"],
        "RegTech": ["Compliance Technology", "AML", "KYC"],
        "Servicios financieros B2B": ["Fund Administration", "Custody", "Financial Infrastructure"],
    }},
    "S09": {"label": "Inmobiliario e Infraestructuras", "industries": {
        "Residencial": ["Promoción", "Alquiler", "Build-to-Rent"],
        "Oficinas": ["Office Property", "Flexible Offices"],
        "Retail inmobiliario": ["Shopping Centres", "Retail Parks"],
        "Industrial y logística": ["Warehouses", "Logistics Property"],
        "Hoteles inmobiliarios": ["Hotel Assets", "Hospitality Real Estate"],
        "Activos alternativos": ["Student Housing", "Senior Living", "Data Centres"],
        "Promoción inmobiliaria": ["Desarrollo residencial", "Comercial", "Mixto"],
        "Gestión de activos": ["Property Management", "Asset Management"],
        "Servicios inmobiliarios": ["Brokerage", "Valuation", "Advisory"],
        "PropTech": ["Property Software", "Transaction Platforms"],
        "Infraestructuras": ["Carreteras", "Ferrocarril", "Puertos", "Infraestructura social"],
        "Infraestructura digital": ["Data Centres", "Towers", "Fibre Infrastructure"],
    }},
    "S10": {"label": "Transporte y Logística", "industries": {
        "Transporte terrestre": ["Carretera", "Autobuses", "Taxi/VTC"],
        "Transporte ferroviario": ["Passenger Rail", "Freight Rail"],
        "Transporte marítimo": ["Shipping", "Ferries", "Maritime Services"],
        "Transporte aéreo": ["Airlines", "Charter", "Aviation Services"],
        "Logística": ["Contract Logistics", "3PL", "4PL"],
        "Transitarios": ["Freight Forwarding", "Customs"],
        "Última milla": ["Last Mile", "Urban Logistics"],
        "Mensajería": ["Parcel", "Courier", "Express"],
        "Movilidad": ["Mobility Services", "Shared Mobility"],
        "Tecnología logística": ["TMS", "Fleet Management", "Logistics Software"],
        "Infraestructuras de transporte": ["Terminales", "Aparcamientos", "Puertos", "Aeropuertos"],
    }},
    "S11": {"label": "Alimentación y Agroindustria", "industries": {
        "Agricultura": ["Cultivos", "Agricultura especializada"],
        "Ganadería": ["Producción animal", "Avicultura"],
        "Pesca y acuicultura": ["Fishing", "Aquaculture"],
        "Alimentación": ["Procesado", "Preparados", "Productos frescos"],
        "Bebidas": ["Refrescos", "Café", "Agua", "Bebidas funcionales"],
        "Panadería y dulces": ["Bakery", "Confectionery", "Snacks"],
        "Lácteos": ["Dairy", "Cheese", "Alternatives"],
        "Carne y proteínas": ["Meat Processing", "Alternative Protein"],
        "Ingredientes": ["Food Ingredients", "Additives"],
        "Distribución alimentaria": ["Food Distribution", "Wholesale"],
        "FoodTech": ["Food Software", "Alternative Food", "Production Tech"],
        "AgTech": ["Precision Agriculture", "Farm Software", "Ag Robotics"],
    }},
}

# ── Dimensiones transversales (registros canónicos)
DIMENSIONS: Dict[str, List[str]] = {
    "verticals": ["Inteligencia Artificial", "SaaS", "AdTech", "MarTech", "FinTech", "InsurTech",
                  "HealthTech", "BioTech", "MedTech", "LegalTech", "HRTech", "PropTech", "EdTech",
                  "FoodTech", "AgTech", "ClimateTech", "CleanTech", "RetailTech", "TravelTech",
                  "Cybersecurity", "IoT", "Robotics", "MobilityTech", "Creator Economy", "Ecommerce",
                  "Digital Health", "Industry 4.0"],
    "business_models": ["B2B", "B2C", "B2B2C", "B2G", "SaaS", "Suscripción", "Licencia", "Transaccional",
                        "Marketplace", "Comisión", "Publicidad", "Servicios profesionales", "Proyecto",
                        "Managed Services", "Usage-based", "Freemium", "Hardware + Software",
                        "Distribución", "Franquicia", "Rental / Leasing"],
    "client_types": ["Grandes empresas", "Mid-Market", "PYME", "Microempresa", "Administraciones públicas",
                     "Consumidor", "Agencias", "Anunciantes", "Publishers", "Retailers",
                     "Instituciones financieras", "Profesionales", "Hospitales", "Farmacéuticas",
                     "Industria", "Distribuidores"],
    "technologies": ["Inteligencia artificial", "Machine Learning", "IA generativa", "Computer Vision",
                     "NLP", "Big Data", "Cloud", "Blockchain", "IoT", "Robótica", "AR/VR",
                     "Ciberseguridad", "Edge Computing", "5G", "Automatización", "Low-Code", "Digital Twin"],
    "value_chain": ["Fabricante", "Desarrollador", "Proveedor tecnológico", "Distribuidor", "Mayorista",
                    "Marketplace", "Prestador de servicios", "Integrador", "Intermediario", "Operador",
                    "Retailer", "Propietario de activos", "Gestor de activos"],
    # Registro inicial de capacidades (starter; se ampliará con la clasificación real)
    "capabilities": ["Estrategia de marca", "Creatividad", "Compra de medios", "Performance", "SEO", "SEM",
                     "Social Media", "Influencer Marketing", "CRM", "Data Analytics", "Programmatic",
                     "Content", "Producción audiovisual", "Customer Experience", "Commerce", "Loyalty",
                     "Data Management", "Analytics", "Workflow Automation", "Cybersecurity",
                     "Cloud Migration", "Software Development", "System Integration", "Artificial Intelligence"],
}


def industry_id(sector_id: str, industry_label: str) -> str:
    return f"IND-{sector_id}-{slug(industry_label)}"


def category_id(sector_id: str, industry_label: str, category_label: str) -> str:
    return f"CAT-{sector_id}-{slug(industry_label)}-{slug(category_label)}"


def dimension_id(dimension: str, label: str) -> str:
    return f"DIM-{dimension}-{slug(label)}"


# Alias curados por nodo → resuelven expresiones habituales de lenguaje natural al nodo correcto
# (evita que "agencias de marketing/viajes" caigan en la categoría genérica "Agencias").
NODE_ALIASES: Dict[str, List[str]] = {
    "S03": ["agencias de marketing", "agencia de marketing", "empresas de marketing"],
    "IND-S04-viajes-y-turismo": ["agencias de viajes", "agencia de viajes",
                                 "agencias de turismo", "agencia de turismo"],
    "IND-S05-industria-farmaceutica": ["laboratorio farmaceutico", "laboratorios farmaceuticos",
                                       "farmaceutica", "farmaceuticas"],
    "IND-S05-dental": ["clinicas dentales", "clinica dental", "dentistas"],
    "CAT-S01-auditoria-y-contabilidad-asesoria-fiscal": ["asesorias fiscales", "asesoria fiscal",
                                                         "gestoria fiscal"],
}


def build_nodes() -> List[Dict]:
    """Genera los documentos de nodo del árbol (sin persistir)."""
    out: List[Dict] = []
    for sid, sec in SEED.items():
        out.append({"id": sid, "level": "sector", "parent_id": None, "label_es": sec["label"],
                    "aliases": NODE_ALIASES.get(sid, []), "status": "active",
                    "taxonomy_version": TAXONOMY_VERSION})
        for ind, cats in sec["industries"].items():
            iid = industry_id(sid, ind)
            out.append({"id": iid, "level": "industry", "parent_id": sid, "label_es": ind,
                        "aliases": NODE_ALIASES.get(iid, []), "status": "active",
                        "taxonomy_version": TAXONOMY_VERSION})
            for cat in cats:
                cid = category_id(sid, ind, cat)
                out.append({"id": cid, "level": "category", "parent_id": iid,
                            "label_es": cat, "aliases": NODE_ALIASES.get(cid, []),
                            "status": "active", "taxonomy_version": TAXONOMY_VERSION})
    return out


def build_dimensions() -> List[Dict]:
    out: List[Dict] = []
    for dim, labels in DIMENSIONS.items():
        for lb in labels:
            out.append({"id": dimension_id(dim, lb), "dimension": dim, "label_es": lb, "aliases": [],
                        "status": "active", "taxonomy_version": TAXONOMY_VERSION})
    return out


_INDEXED = False


async def ensure_indexes() -> None:
    global _INDEXED
    if _INDEXED:
        return
    try:
        from database import db
        await db.taxonomy_nodes.create_index("id", unique=True)
        await db.taxonomy_nodes.create_index([("level", 1), ("parent_id", 1)])
        await db.taxonomy_dimensions.create_index("id", unique=True)
        await db.taxonomy_dimensions.create_index("dimension")
        _INDEXED = True
    except Exception:
        pass


async def build_registry_v1() -> Dict:
    """Siembra idempotente del Registry v1 (por `id`). Devuelve conteos."""
    await ensure_indexes()
    from database import db
    from models import now_iso
    now = now_iso()
    n_nodes = n_dims = 0
    for node in build_nodes():
        await db.taxonomy_nodes.update_one({"id": node["id"]},
            {"$set": {**node, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
        n_nodes += 1
    for d in build_dimensions():
        await db.taxonomy_dimensions.update_one({"id": d["id"]},
            {"$set": {**d, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
        n_dims += 1
    return {"taxonomy_version": TAXONOMY_VERSION, "nodes": n_nodes, "dimensions": n_dims,
            "sectors": len(SEED)}


# ── Lectura
async def get_tree() -> List[Dict]:
    """Árbol jerárquico sector→industria→categoría (desde BBDD si existe, si no desde SEED)."""
    try:
        from database import db
        nodes = [n async for n in db.taxonomy_nodes.find({"status": "active"}, {"_id": 0})]
        if not nodes:
            nodes = build_nodes()
    except Exception:
        nodes = build_nodes()
    by_parent: Dict[Optional[str], List[Dict]] = {}
    for n in nodes:
        by_parent.setdefault(n["parent_id"], []).append(n)
    def _children(pid):
        return [{"id": c["id"], "label_es": c["label_es"], "level": c["level"],
                 "children": _children(c["id"])} for c in sorted(by_parent.get(pid, []), key=lambda x: x["id"])]
    return _children(None)


async def get_dimensions() -> Dict[str, List[Dict]]:
    try:
        from database import db
        rows = [d async for d in db.taxonomy_dimensions.find({"status": "active"}, {"_id": 0})]
        if not rows:
            rows = build_dimensions()
    except Exception:
        rows = build_dimensions()
    out: Dict[str, List[Dict]] = {}
    for d in rows:
        out.setdefault(d["dimension"], []).append({"id": d["id"], "label_es": d["label_es"]})
    return out


async def get_node(node_id: str) -> Optional[Dict]:
    try:
        from database import db
        return await db.taxonomy_nodes.find_one({"id": node_id}, {"_id": 0})
    except Exception:
        return next((n for n in build_nodes() if n["id"] == node_id), None)
