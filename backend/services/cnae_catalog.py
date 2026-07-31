"""Official CNAE-2009 Catalog — Spanish National Classification of Economic Activities.

Hierarchy: Section (letter) → Division (2-digit) → Group (4-digit)
Source: INE / Real Decreto 475/2007
"""

# ══════════════════════════════════════════
# SECTIONS (A-U) — 21 total
# ══════════════════════════════════════════

CNAE_SECTIONS = [
    {"code": "A", "label": "Agricultura, ganadería, silvicultura y pesca", "divisions": ["01", "02", "03"]},
    {"code": "B", "label": "Industrias extractivas", "divisions": ["05", "06", "07", "08", "09"]},
    {"code": "C", "label": "Industria manufacturera", "divisions": [
        "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23",
        "24", "25", "26", "27", "28", "29", "30", "31", "32", "33"
    ]},
    {"code": "D", "label": "Suministro de energía eléctrica, gas, vapor y aire acondicionado", "divisions": ["35"]},
    {"code": "E", "label": "Suministro de agua, actividades de saneamiento, gestión de residuos y descontaminación", "divisions": ["36", "37", "38", "39"]},
    {"code": "F", "label": "Construcción", "divisions": ["41", "42", "43"]},
    {"code": "G", "label": "Comercio al por mayor y al por menor; reparación de vehículos de motor y motocicletas", "divisions": ["45", "46", "47"]},
    {"code": "H", "label": "Transporte y almacenamiento", "divisions": ["49", "50", "51", "52", "53"]},
    {"code": "I", "label": "Hostelería", "divisions": ["55", "56"]},
    {"code": "J", "label": "Información y comunicaciones", "divisions": ["58", "59", "60", "61", "62", "63"]},
    {"code": "K", "label": "Actividades financieras y de seguros", "divisions": ["64", "65", "66"]},
    {"code": "L", "label": "Actividades inmobiliarias", "divisions": ["68"]},
    {"code": "M", "label": "Actividades profesionales, científicas y técnicas", "divisions": ["69", "70", "71", "72", "73", "74", "75"]},
    {"code": "N", "label": "Actividades administrativas y servicios auxiliares", "divisions": ["77", "78", "79", "80", "81", "82"]},
    {"code": "O", "label": "Administración Pública y defensa; Seguridad Social obligatoria", "divisions": ["84"]},
    {"code": "P", "label": "Educación", "divisions": ["85"]},
    {"code": "Q", "label": "Actividades sanitarias y de servicios sociales", "divisions": ["86", "87", "88"]},
    {"code": "R", "label": "Actividades artísticas, recreativas y de entretenimiento", "divisions": ["90", "91", "92", "93"]},
    {"code": "S", "label": "Otros servicios", "divisions": ["94", "95", "96"]},
    {"code": "T", "label": "Actividades de los hogares como empleadores de personal doméstico; actividades de los hogares como productores de bienes y servicios para uso propio", "divisions": ["97", "98"]},
    {"code": "U", "label": "Actividades de organizaciones y organismos extraterritoriales", "divisions": ["99"]},
]

# ══════════════════════════════════════════
# DIVISIONS (2-digit) — 88 total
# ══════════════════════════════════════════

CNAE_DIVISIONS = {
    "01": {"label": "Agricultura, ganadería, caza y servicios relacionados con las mismas", "section": "A"},
    "02": {"label": "Silvicultura y explotación forestal", "section": "A"},
    "03": {"label": "Pesca y acuicultura", "section": "A"},
    "05": {"label": "Extracción de antracita, hulla y lignito", "section": "B"},
    "06": {"label": "Extracción de crudo de petróleo y gas natural", "section": "B"},
    "07": {"label": "Extracción de minerales metálicos", "section": "B"},
    "08": {"label": "Otras industrias extractivas", "section": "B"},
    "09": {"label": "Actividades de apoyo a las industrias extractivas", "section": "B"},
    "10": {"label": "Industria de la alimentación", "section": "C"},
    "11": {"label": "Fabricación de bebidas", "section": "C"},
    "12": {"label": "Industria del tabaco", "section": "C"},
    "13": {"label": "Industria textil", "section": "C"},
    "14": {"label": "Confección de prendas de vestir", "section": "C"},
    "15": {"label": "Industria del cuero y del calzado", "section": "C"},
    "16": {"label": "Industria de la madera y del corcho, excepto muebles; cestería y espartería", "section": "C"},
    "17": {"label": "Industria del papel", "section": "C"},
    "18": {"label": "Artes gráficas y reproducción de soportes grabados", "section": "C"},
    "19": {"label": "Coquerías y refino de petróleo", "section": "C"},
    "20": {"label": "Industria química", "section": "C"},
    "21": {"label": "Fabricación de productos farmacéuticos", "section": "C"},
    "22": {"label": "Fabricación de productos de caucho y plásticos", "section": "C"},
    "23": {"label": "Fabricación de otros productos minerales no metálicos", "section": "C"},
    "24": {"label": "Metalurgia; fabricación de productos de hierro, acero y ferroaleaciones", "section": "C"},
    "25": {"label": "Fabricación de productos metálicos, excepto maquinaria y equipo", "section": "C"},
    "26": {"label": "Fabricación de productos informáticos, electrónicos y ópticos", "section": "C"},
    "27": {"label": "Fabricación de material y equipo eléctrico", "section": "C"},
    "28": {"label": "Fabricación de maquinaria y equipo n.c.o.p.", "section": "C"},
    "29": {"label": "Fabricación de vehículos de motor, remolques y semirremolques", "section": "C"},
    "30": {"label": "Fabricación de otro material de transporte", "section": "C"},
    "31": {"label": "Fabricación de muebles", "section": "C"},
    "32": {"label": "Otras industrias manufactureras", "section": "C"},
    "33": {"label": "Reparación e instalación de maquinaria y equipo", "section": "C"},
    "35": {"label": "Suministro de energía eléctrica, gas, vapor y aire acondicionado", "section": "D"},
    "36": {"label": "Captación, depuración y distribución de agua", "section": "E"},
    "37": {"label": "Recogida y tratamiento de aguas residuales", "section": "E"},
    "38": {"label": "Recogida, tratamiento y eliminación de residuos; valorización", "section": "E"},
    "39": {"label": "Actividades de descontaminación y otros servicios de gestión de residuos", "section": "E"},
    "41": {"label": "Construcción de edificios", "section": "F"},
    "42": {"label": "Ingeniería civil", "section": "F"},
    "43": {"label": "Actividades de construcción especializada", "section": "F"},
    "45": {"label": "Venta y reparación de vehículos de motor y motocicletas", "section": "G"},
    "46": {"label": "Comercio al por mayor e intermediarios del comercio, excepto de vehículos de motor y motocicletas", "section": "G"},
    "47": {"label": "Comercio al por menor, excepto de vehículos de motor y motocicletas", "section": "G"},
    "49": {"label": "Transporte terrestre y por tubería", "section": "H"},
    "50": {"label": "Transporte marítimo y por vías navegables interiores", "section": "H"},
    "51": {"label": "Transporte aéreo", "section": "H"},
    "52": {"label": "Almacenamiento y actividades anexas al transporte", "section": "H"},
    "53": {"label": "Actividades postales y de correos", "section": "H"},
    "55": {"label": "Servicios de alojamiento", "section": "I"},
    "56": {"label": "Servicios de comidas y bebidas", "section": "I"},
    "58": {"label": "Edición", "section": "J"},
    "59": {"label": "Actividades cinematográficas, de vídeo y de programas de televisión, grabación de sonido y edición musical", "section": "J"},
    "60": {"label": "Actividades de programación y emisión de radio y televisión", "section": "J"},
    "61": {"label": "Telecomunicaciones", "section": "J"},
    "62": {"label": "Programación, consultoría y otras actividades relacionadas con la informática", "section": "J"},
    "63": {"label": "Servicios de información", "section": "J"},
    "64": {"label": "Servicios financieros, excepto seguros y fondos de pensiones", "section": "K"},
    "65": {"label": "Seguros, reaseguros y fondos de pensiones, excepto Seguridad Social obligatoria", "section": "K"},
    "66": {"label": "Actividades auxiliares a los servicios financieros y a los seguros", "section": "K"},
    "68": {"label": "Actividades inmobiliarias", "section": "L"},
    "69": {"label": "Actividades jurídicas y de contabilidad", "section": "M"},
    "70": {"label": "Actividades de las sedes centrales; actividades de consultoría de gestión empresarial", "section": "M"},
    "71": {"label": "Servicios técnicos de arquitectura e ingeniería; ensayos y análisis técnicos", "section": "M"},
    "72": {"label": "Investigación y desarrollo", "section": "M"},
    "73": {"label": "Publicidad y estudios de mercado", "section": "M"},
    "74": {"label": "Otras actividades profesionales, científicas y técnicas", "section": "M"},
    "75": {"label": "Actividades veterinarias", "section": "M"},
    "77": {"label": "Actividades de alquiler", "section": "N"},
    "78": {"label": "Actividades relacionadas con el empleo", "section": "N"},
    "79": {"label": "Actividades de agencias de viajes, operadores turísticos, servicios de reservas y actividades relacionadas con los mismos", "section": "N"},
    "80": {"label": "Actividades de seguridad e investigación", "section": "N"},
    "81": {"label": "Servicios a edificios y actividades de jardinería", "section": "N"},
    "82": {"label": "Actividades administrativas de oficina y otras actividades auxiliares a las empresas", "section": "N"},
    "84": {"label": "Administración Pública y defensa; Seguridad Social obligatoria", "section": "O"},
    "85": {"label": "Educación", "section": "P"},
    "86": {"label": "Actividades sanitarias", "section": "Q"},
    "87": {"label": "Asistencia en establecimientos residenciales", "section": "Q"},
    "88": {"label": "Actividades de servicios sociales sin alojamiento", "section": "Q"},
    "90": {"label": "Actividades de creación, artísticas y espectáculos", "section": "R"},
    "91": {"label": "Actividades de bibliotecas, archivos, museos y otras actividades culturales", "section": "R"},
    "92": {"label": "Actividades de juegos de azar y apuestas", "section": "R"},
    "93": {"label": "Actividades deportivas, recreativas y de entretenimiento", "section": "R"},
    "94": {"label": "Actividades asociativas", "section": "S"},
    "95": {"label": "Reparación de ordenadores, efectos personales y artículos de uso doméstico", "section": "S"},
    "96": {"label": "Otros servicios personales", "section": "S"},
    "97": {"label": "Actividades de los hogares como empleadores de personal doméstico", "section": "T"},
    "98": {"label": "Actividades de los hogares como productores de bienes y servicios para uso propio", "section": "T"},
    "99": {"label": "Actividades de organizaciones y organismos extraterritoriales", "section": "U"},
}

# ══════════════════════════════════════════
# GROUPS (4-digit) — Key groups per division
# ══════════════════════════════════════════

CNAE_GROUPS = {
    # J - Información y comunicaciones
    "5811": {"label": "Edición de libros", "division": "58"},
    "5812": {"label": "Edición de directorios y guías de direcciones postales", "division": "58"},
    "5813": {"label": "Edición de periódicos", "division": "58"},
    "5814": {"label": "Edición de revistas", "division": "58"},
    "5819": {"label": "Otras actividades editoriales", "division": "58"},
    "5821": {"label": "Edición de videojuegos", "division": "58"},
    "5829": {"label": "Edición de otros programas informáticos", "division": "58"},
    "5911": {"label": "Actividades de producción cinematográfica, de vídeo y de programas de televisión", "division": "59"},
    "5912": {"label": "Actividades de postproducción cinematográfica, de vídeo y de programas de televisión", "division": "59"},
    "5913": {"label": "Actividades de distribución cinematográfica, de vídeo y de programas de televisión", "division": "59"},
    "5914": {"label": "Actividades de exhibición cinematográfica", "division": "59"},
    "5920": {"label": "Actividades de grabación de sonido y edición musical", "division": "59"},
    "6010": {"label": "Actividades de radiodifusión", "division": "60"},
    "6020": {"label": "Actividades de programación y emisión de televisión", "division": "60"},
    "6110": {"label": "Telecomunicaciones por cable", "division": "61"},
    "6120": {"label": "Telecomunicaciones inalámbricas", "division": "61"},
    "6130": {"label": "Telecomunicaciones por satélite", "division": "61"},
    "6190": {"label": "Otras actividades de telecomunicaciones", "division": "61"},
    "6201": {"label": "Actividades de programación informática", "division": "62"},
    "6202": {"label": "Actividades de consultoría informática", "division": "62"},
    "6203": {"label": "Gestión de recursos informáticos", "division": "62"},
    "6209": {"label": "Otros servicios relacionados con las tecnologías de la información y la informática", "division": "62"},
    "6311": {"label": "Proceso de datos, hosting y actividades relacionadas", "division": "63"},
    "6312": {"label": "Portales web", "division": "63"},
    "6391": {"label": "Actividades de agencias de noticias", "division": "63"},
    "6399": {"label": "Otros servicios de información n.c.o.p.", "division": "63"},
    # M - Profesionales
    "6910": {"label": "Actividades jurídicas", "division": "69"},
    "6920": {"label": "Actividades de contabilidad, teneduría de libros, auditoría y asesoría fiscal", "division": "69"},
    "7010": {"label": "Actividades de las sedes centrales", "division": "70"},
    "7021": {"label": "Relaciones públicas y comunicación", "division": "70"},
    "7022": {"label": "Otras actividades de consultoría de gestión empresarial", "division": "70"},
    "7111": {"label": "Servicios técnicos de arquitectura", "division": "71"},
    "7112": {"label": "Servicios técnicos de ingeniería y otras actividades relacionadas con el asesoramiento técnico", "division": "71"},
    "7120": {"label": "Ensayos y análisis técnicos", "division": "71"},
    "7211": {"label": "Investigación y desarrollo experimental en biotecnología", "division": "72"},
    "7219": {"label": "Otra investigación y desarrollo experimental en ciencias naturales y técnicas", "division": "72"},
    "7220": {"label": "Investigación y desarrollo experimental en ciencias sociales y humanidades", "division": "72"},
    "7311": {"label": "Agencias de publicidad", "division": "73"},
    "7312": {"label": "Servicios de representación de medios de comunicación", "division": "73"},
    "7320": {"label": "Estudios de mercado y realización de encuestas de opinión pública", "division": "73"},
    "7410": {"label": "Actividades de diseño especializado", "division": "74"},
    "7420": {"label": "Actividades de fotografía", "division": "74"},
    "7430": {"label": "Actividades de traducción e interpretación", "division": "74"},
    "7490": {"label": "Otras actividades profesionales, científicas y técnicas n.c.o.p.", "division": "74"},
    "7500": {"label": "Actividades veterinarias", "division": "75"},
    # G - Comercio
    "4511": {"label": "Venta de automóviles y vehículos de motor ligeros", "division": "45"},
    "4519": {"label": "Venta de otros vehículos de motor", "division": "45"},
    "4520": {"label": "Mantenimiento y reparación de vehículos de motor", "division": "45"},
    "4611": {"label": "Intermediarios del comercio de materias primas agrarias, animales vivos, materias primas textiles y productos semielaborados", "division": "46"},
    "4690": {"label": "Comercio al por mayor no especializado", "division": "46"},
    "4711": {"label": "Comercio al por menor en establecimientos no especializados, con predominio en productos alimenticios, bebidas y tabaco", "division": "47"},
    "4719": {"label": "Otro comercio al por menor en establecimientos no especializados", "division": "47"},
    "4791": {"label": "Comercio al por menor por correspondencia o por Internet", "division": "47"},
    # F - Construcción
    "4110": {"label": "Promoción inmobiliaria", "division": "41"},
    "4121": {"label": "Construcción de edificios residenciales", "division": "41"},
    "4122": {"label": "Construcción de edificios no residenciales", "division": "41"},
    "4211": {"label": "Construcción de carreteras y autopistas", "division": "42"},
    "4221": {"label": "Construcción de redes para fluidos", "division": "42"},
    "4312": {"label": "Preparación de terrenos", "division": "43"},
    "4321": {"label": "Instalaciones eléctricas", "division": "43"},
    "4322": {"label": "Fontanería, instalaciones de sistemas de calefacción y aire acondicionado", "division": "43"},
    "4329": {"label": "Otras instalaciones en obras de construcción", "division": "43"},
    # I - Hostelería
    "5510": {"label": "Hoteles y alojamientos similares", "division": "55"},
    "5520": {"label": "Alojamientos turísticos y otros alojamientos de corta estancia", "division": "55"},
    "5610": {"label": "Restaurantes y puestos de comidas", "division": "56"},
    "5621": {"label": "Provisión de comidas preparadas para eventos", "division": "56"},
    "5629": {"label": "Otros servicios de comidas", "division": "56"},
    "5630": {"label": "Establecimientos de bebidas", "division": "56"},
    # K - Finanzas
    "6411": {"label": "Banco central", "division": "64"},
    "6419": {"label": "Otra intermediación monetaria", "division": "64"},
    "6420": {"label": "Actividades de las sociedades holding", "division": "64"},
    "6430": {"label": "Inversión colectiva, fondos y entidades financieras similares", "division": "64"},
    "6511": {"label": "Seguros de vida", "division": "65"},
    "6512": {"label": "Seguros distintos de los seguros de vida", "division": "65"},
    "6611": {"label": "Administración de mercados financieros", "division": "66"},
    "6619": {"label": "Otras actividades auxiliares a los servicios financieros, excepto seguros y fondos de pensiones", "division": "66"},
    # N - Administrativas
    "7711": {"label": "Alquiler de automóviles y vehículos de motor ligeros", "division": "77"},
    "7810": {"label": "Actividades de agencias de colocación", "division": "78"},
    "7820": {"label": "Actividades de empresas de trabajo temporal", "division": "78"},
    "7911": {"label": "Actividades de agencias de viajes", "division": "79"},
    "7912": {"label": "Actividades de operadores turísticos", "division": "79"},
    "8010": {"label": "Actividades de seguridad privada", "division": "80"},
    "8110": {"label": "Servicios integrales a edificios e instalaciones", "division": "81"},
    "8121": {"label": "Limpieza general de edificios", "division": "81"},
    "8211": {"label": "Servicios administrativos combinados", "division": "82"},
    "8220": {"label": "Actividades de los centros de llamadas", "division": "82"},
    "8230": {"label": "Organización de convenciones y ferias de muestras", "division": "82"},
    # Q - Sanidad
    "8610": {"label": "Actividades hospitalarias", "division": "86"},
    "8621": {"label": "Actividades de medicina general", "division": "86"},
    "8622": {"label": "Actividades de medicina especializada", "division": "86"},
    "8623": {"label": "Actividades odontológicas", "division": "86"},
    "8690": {"label": "Otras actividades sanitarias", "division": "86"},
    "8710": {"label": "Asistencia en establecimientos residenciales con cuidados sanitarios", "division": "87"},
    "8811": {"label": "Actividades de servicios sociales sin alojamiento para personas mayores", "division": "88"},
    # P - Educación
    "8510": {"label": "Educación preprimaria", "division": "85"},
    "8520": {"label": "Educación primaria", "division": "85"},
    "8531": {"label": "Educación secundaria general", "division": "85"},
    "8532": {"label": "Educación secundaria técnica y profesional", "division": "85"},
    "8541": {"label": "Educación postsecundaria no terciaria", "division": "85"},
    "8542": {"label": "Educación terciaria", "division": "85"},
    "8543": {"label": "Educación universitaria", "division": "85"},
    "8544": {"label": "Educación universitaria y de formación profesional de grado superior", "division": "85"},
    "8551": {"label": "Educación deportiva y recreativa", "division": "85"},
    "8552": {"label": "Educación cultural", "division": "85"},
    "8559": {"label": "Otra educación n.c.o.p.", "division": "85"},
    # R - Actividades artísticas
    "9001": {"label": "Artes escénicas", "division": "90"},
    "9002": {"label": "Actividades auxiliares a las artes escénicas", "division": "90"},
    "9003": {"label": "Creación artística y literaria", "division": "90"},
    "9004": {"label": "Gestión de salas de espectáculos", "division": "90"},
    "9104": {"label": "Actividades de los jardines botánicos, parques zoológicos y reservas naturales", "division": "91"},
    "9200": {"label": "Actividades de juegos de azar y apuestas", "division": "92"},
    "9311": {"label": "Gestión de instalaciones deportivas", "division": "93"},
    "9312": {"label": "Actividades de los clubes deportivos", "division": "93"},
    "9313": {"label": "Actividades de los gimnasios", "division": "93"},
    "9319": {"label": "Otras actividades deportivas", "division": "93"},
    "9321": {"label": "Actividades de los parques de atracciones y los parques temáticos", "division": "93"},
    "9329": {"label": "Otras actividades recreativas y de entretenimiento", "division": "93"},
    # A - Agricultura
    "0111": {"label": "Cultivo de cereales (excepto arroz), leguminosas y semillas oleaginosas", "division": "01"},
    "0113": {"label": "Cultivo de hortalizas, raíces y tubérculos", "division": "01"},
    "0121": {"label": "Cultivo de la vid", "division": "01"},
    "0124": {"label": "Cultivo de frutos con hueso y pepitas", "division": "01"},
    "0141": {"label": "Explotación de ganado bovino para la producción de leche", "division": "01"},
    "0150": {"label": "Producción agrícola combinada con la producción ganadera", "division": "01"},
    "0210": {"label": "Silvicultura y otras actividades forestales", "division": "02"},
    "0311": {"label": "Pesca marina", "division": "03"},
    "0321": {"label": "Acuicultura marina", "division": "03"},
    # C - Industria manufacturera (key groups)
    "1011": {"label": "Procesado y conservación de carne", "division": "10"},
    "1039": {"label": "Otro procesado y conservación de frutas y hortalizas", "division": "10"},
    "1071": {"label": "Fabricación de pan y de productos frescos de panadería y pastelería", "division": "10"},
    "1081": {"label": "Fabricación de azúcar", "division": "10"},
    "1101": {"label": "Destilación, rectificación y mezcla de bebidas alcohólicas", "division": "11"},
    "1102": {"label": "Elaboración de vinos", "division": "11"},
    "1105": {"label": "Fabricación de cerveza", "division": "11"},
    "2011": {"label": "Fabricación de gases industriales", "division": "20"},
    "2110": {"label": "Fabricación de productos farmacéuticos de base", "division": "21"},
    "2120": {"label": "Fabricación de especialidades farmacéuticas", "division": "21"},
    "2611": {"label": "Fabricación de componentes electrónicos", "division": "26"},
    "2620": {"label": "Fabricación de ordenadores y equipos periféricos", "division": "26"},
    "2630": {"label": "Fabricación de equipos de telecomunicaciones", "division": "26"},
    "2651": {"label": "Fabricación de instrumentos y aparatos de medida, verificación y navegación", "division": "26"},
    "2910": {"label": "Fabricación de vehículos de motor", "division": "29"},
    "2920": {"label": "Fabricación de carrocerías para vehículos de motor; fabricación de remolques y semirremolques", "division": "29"},
    "2932": {"label": "Fabricación de otros componentes, piezas y accesorios para vehículos de motor", "division": "29"},
    "3011": {"label": "Construcción de barcos y estructuras flotantes", "division": "30"},
    "3030": {"label": "Construcción aeronáutica y espacial y su maquinaria", "division": "30"},
    # D/E - Energía y agua
    "3511": {"label": "Producción de energía eléctrica", "division": "35"},
    "3512": {"label": "Transporte de energía eléctrica", "division": "35"},
    "3513": {"label": "Distribución de energía eléctrica", "division": "35"},
    "3514": {"label": "Comercio de energía eléctrica", "division": "35"},
    "3521": {"label": "Producción de gas", "division": "35"},
    "3530": {"label": "Suministro de vapor y aire acondicionado", "division": "35"},
    "3600": {"label": "Captación, depuración y distribución de agua", "division": "36"},
    "3811": {"label": "Recogida de residuos no peligrosos", "division": "38"},
    "3821": {"label": "Tratamiento y eliminación de residuos no peligrosos", "division": "38"},
    # H - Transporte
    "4910": {"label": "Transporte interurbano de pasajeros por ferrocarril", "division": "49"},
    "4931": {"label": "Transporte terrestre urbano y suburbano de pasajeros", "division": "49"},
    "4941": {"label": "Transporte de mercancías por carretera", "division": "49"},
    "4942": {"label": "Servicios de mudanza", "division": "49"},
    "5010": {"label": "Transporte marítimo de pasajeros", "division": "50"},
    "5110": {"label": "Transporte aéreo de pasajeros", "division": "51"},
    "5210": {"label": "Depósito y almacenamiento", "division": "52"},
    "5221": {"label": "Actividades anexas al transporte terrestre", "division": "52"},
    "5310": {"label": "Actividades postales sometidas a la obligación del servicio universal", "division": "53"},
    # L - Inmobiliarias
    "6810": {"label": "Compraventa de bienes inmobiliarios por cuenta propia", "division": "68"},
    "6820": {"label": "Alquiler de bienes inmobiliarios por cuenta propia", "division": "68"},
    "6831": {"label": "Agentes de la propiedad inmobiliaria", "division": "68"},
    "6832": {"label": "Gestión y administración de la propiedad inmobiliaria", "division": "68"},
    # S - Otros servicios
    "9411": {"label": "Actividades de organizaciones empresariales y patronales", "division": "94"},
    "9412": {"label": "Actividades de organizaciones profesionales", "division": "94"},
    "9420": {"label": "Actividades sindicales", "division": "94"},
    "9511": {"label": "Reparación de ordenadores y equipos periféricos", "division": "95"},
    "9521": {"label": "Reparación de aparatos electrónicos de audio y vídeo de uso doméstico", "division": "95"},
    "9601": {"label": "Lavado y limpieza de prendas textiles y de piel", "division": "96"},
    "9602": {"label": "Peluquería y otros tratamientos de belleza", "division": "96"},
    "9604": {"label": "Actividades de mantenimiento físico", "division": "96"},
    "9609": {"label": "Otros servicios personales n.c.o.p.", "division": "96"},
}


# ══════════════════════════════════════════
# CPV → CNAE MAPPING (Procurement → Sector)
# ══════════════════════════════════════════

CPV_TO_CNAE = {
    # IT & Software
    "72": "62",   # IT services → Programming/consulting
    "48": "62",   # Software packages → Programming
    "30": "26",   # Office machinery → Electronic products
    # Advertising & Marketing
    "79341": "73",  # Advertising → Publicidad
    "79342": "73",
    "79340": "73",
    "793": "73",
    # PR & Communications
    "79416": "70",  # PR → Consultoría de gestión
    # Events
    "79952": "82",  # Event organization
    "79950": "82",
    # Construction
    "45": "41",   # Construction works → Construcción edificios
    "44": "25",   # Construction structures → Productos metálicos
    # Health
    "85": "86",   # Health services → Actividades sanitarias
    "33": "21",   # Medical equipment → Farmacéutica
    # Education
    "80": "85",   # Education → Educación
    # Transport
    "60": "49",   # Transport services → Transporte terrestre
    "63": "52",   # Supporting transport → Almacenamiento/anexas
    # Food
    "15": "10",   # Food products → Industria alimentación
    # Energy
    "09": "35",   # Petroleum products → Energía
    "65": "35",   # Energy → Energía
    # Consulting
    "79": "70",   # Business services → Consultoría gestión
    "73": "72",   # Research → Investigación
    # Publishing / Printing
    "22": "18",   # Printed matter → Artes gráficas
    "79822": "73", # Advertising-related
    # Security
    "79710": "80",  # Security → Seguridad
    # Cleaning
    "90": "81",   # Sewage/refuse → Servicios edificios
    # Financial
    "66": "64",   # Financial services → Servicios financieros
    # Legal
    "79100": "69",  # Legal services → Jurídicas
    # Architecture
    "71": "71",   # Architectural services → Arquitectura/ingeniería
    # Telecom
    "64": "61",   # Post/telecom → Telecomunicaciones
    "32": "61",   # Radio/TV equipment → Telecomunicaciones
}


# ══════════════════════════════════════════
# BUSINESS ARCHETYPES (future — schema only)
# ══════════════════════════════════════════

BUSINESS_ARCHETYPES = [
    {"archetype_id": "saas", "label": "SaaS", "description": "Software as a Service"},
    {"archetype_id": "marketplace", "label": "Marketplace", "description": "Plataforma de intermediación"},
    {"archetype_id": "agencia_creativa", "label": "Agencia Creativa", "description": "Agencia de publicidad, diseño y producción creativa"},
    {"archetype_id": "agencia_medios", "label": "Agencia de Medios", "description": "Planificación y compra de medios"},
    {"archetype_id": "consultoria", "label": "Consultoría", "description": "Servicios profesionales de consultoría"},
    {"archetype_id": "software", "label": "Software", "description": "Desarrollo y venta de software"},
    {"archetype_id": "retail", "label": "Retail", "description": "Comercio minorista"},
    {"archetype_id": "distribuidor", "label": "Distribuidor", "description": "Distribución y logística"},
    {"archetype_id": "fabricante", "label": "Fabricante", "description": "Fabricación industrial"},
    {"archetype_id": "media_owner", "label": "Media Owner", "description": "Propietario de soportes publicitarios"},
    {"archetype_id": "healthcare_provider", "label": "Healthcare Provider", "description": "Servicios sanitarios"},
    {"archetype_id": "holding", "label": "Holding", "description": "Sociedad holding o grupo empresarial"},
    {"archetype_id": "franquicia", "label": "Franquicia", "description": "Modelo de franquicia"},
]


# ══════════════════════════════════════════
# TAXONOMY TYPES (multi-taxonomy support)
# ══════════════════════════════════════════

TAXONOMY_TYPES = [
    "official_cnae",
    "business_archetype",
    "behavioral_cluster",
    "similarity_cluster",
]


def get_section_for_division(division_code: str) -> str | None:
    """Return section letter for a 2-digit division."""
    info = CNAE_DIVISIONS.get(division_code)
    return info["section"] if info else None


def get_division_for_group(group_code: str) -> str | None:
    """Return 2-digit division for a 4-digit group."""
    info = CNAE_GROUPS.get(group_code)
    return info["division"] if info else None


def resolve_cnae_to_section(cnae_code: str) -> str | None:
    """Resolve any CNAE code (section/division/group) to its section letter."""
    if len(cnae_code) == 1 and cnae_code.isalpha():
        return cnae_code.upper()
    if len(cnae_code) == 2:
        return get_section_for_division(cnae_code)
    if len(cnae_code) >= 4:
        div = cnae_code[:2]
        return get_section_for_division(div)
    return None


def resolve_cnae_label(cnae_code: str) -> str | None:
    """Resolve any CNAE code (group 4-digit / division 2-digit / section letter) to its
    Spanish label. Falls back up the hierarchy (group → division → section) so we NEVER
    return a raw English description. Returns None only if the code is unknown."""
    if not cnae_code:
        return None
    code = str(cnae_code).strip().upper()
    # Section letter
    if len(code) == 1 and code.isalpha():
        for sec in CNAE_SECTIONS:
            if sec["code"] == code:
                return sec["label"]
        return None
    digits = "".join(ch for ch in code if ch.isdigit())
    # 4-digit group (exact, then division fallback)
    if len(digits) >= 4:
        grp = digits[:4]
        if grp in CNAE_GROUPS:
            return CNAE_GROUPS[grp]["label"]
        digits = digits[:2]  # fall back to division
    # 2-digit division
    if len(digits) >= 2:
        div = digits[:2].zfill(2)
        if div in CNAE_DIVISIONS:
            return CNAE_DIVISIONS[div]["label"]
        sec_letter = get_section_for_division(div)
        if sec_letter:
            for sec in CNAE_SECTIONS:
                if sec["code"] == sec_letter:
                    return sec["label"]
    return None


def cpv_to_cnae_division(cpv_code: str) -> str | None:
    """Map a CPV code to a CNAE division using longest prefix match."""
    if not cpv_code:
        return None
    # Try longest prefix first
    for length in range(len(cpv_code), 1, -1):
        prefix = cpv_code[:length]
        if prefix in CPV_TO_CNAE:
            return CPV_TO_CNAE[prefix]
    return None


def build_full_catalog():
    """Build full hierarchical catalog for API response."""
    sections = []
    for sec in CNAE_SECTIONS:
        divisions = []
        for div_code in sec["divisions"]:
            div_info = CNAE_DIVISIONS.get(div_code, {})
            groups = []
            for grp_code, grp_info in CNAE_GROUPS.items():
                if grp_info["division"] == div_code:
                    groups.append({
                        "code": grp_code,
                        "label": grp_info["label"],
                        "level": "group",
                    })
            groups.sort(key=lambda g: g["code"])
            divisions.append({
                "code": div_code,
                "label": div_info.get("label", ""),
                "level": "division",
                "groups": groups,
            })
        sections.append({
            "code": sec["code"],
            "label": sec["label"],
            "level": "section",
            "divisions": divisions,
        })
    return sections
