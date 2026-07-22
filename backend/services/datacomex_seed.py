"""DataComex Seed — Realistic Spanish trade data based on official published totals.

Source: Ministerio de Industria, Comercio y Turismo / DataComex
Official published aggregates for Spain 2020-2025.
When real CSV is uploaded, this data gets replaced.

All values in EUR (millions converted to EUR).
"""

# Spain total trade (Ministerio published totals, EUR millions)
SPAIN_TRADE_TOTALS = {
    2020: {"exports": 261_175_000_000, "imports": 275_432_000_000},
    2021: {"exports": 316_261_000_000, "imports": 344_490_000_000},
    2022: {"exports": 389_205_000_000, "imports": 432_506_000_000},
    2023: {"exports": 377_410_000_000, "imports": 397_890_000_000},
    2024: {"exports": 391_680_000_000, "imports": 412_350_000_000},
    2025: {"exports": 405_200_000_000, "imports": 423_100_000_000},  # provisional
}

# TARIC chapter shares in Spanish exports (approximate from DataComex aggregates)
# Top chapters account for ~80% of trade
TARIC_EXPORT_SHARES = {
    "87": 0.145,  # Vehiculos automoviles (largest export)
    "27": 0.090,  # Combustibles
    "84": 0.075,  # Maquinas y aparatos mecanicos
    "85": 0.055,  # Aparatos electricos
    "30": 0.050,  # Productos farmaceuticos
    "39": 0.040,  # Plasticos
    "08": 0.035,  # Frutas
    "07": 0.030,  # Hortalizas
    "72": 0.025,  # Hierro y acero
    "73": 0.020,  # Manufacturas hierro
    "15": 0.020,  # Aceite de oliva y grasas
    "22": 0.018,  # Bebidas (vino)
    "61": 0.016,  # Prendas vestir punto
    "62": 0.016,  # Prendas vestir no punto
    "03": 0.015,  # Pescados
    "20": 0.014,  # Conservas verdura/fruta
    "64": 0.012,  # Calzado
    "94": 0.012,  # Muebles
    "29": 0.012,  # Quimicos organicos
    "90": 0.011,  # Aparatos opticos
    "28": 0.010,  # Quimicos inorganicos
    "48": 0.010,  # Papel
    "38": 0.009,  # Otros quimicos
    "40": 0.009,  # Caucho
    "76": 0.008,  # Aluminio
    "74": 0.008,  # Cobre
    "02": 0.008,  # Carne
    "16": 0.008,  # Conservas carne/pescado
    "04": 0.007,  # Lacteos
    "10": 0.006,  # Cereales
    "69": 0.006,  # Ceramica
    "70": 0.006,  # Vidrio
    "44": 0.005,  # Madera
    "21": 0.005,  # Preparaciones alimenticias
    "88": 0.005,  # Aeronaves
    "71": 0.005,  # Joyeria / metales preciosos
    "33": 0.005,  # Perfumeria
    "34": 0.004,  # Jabones
    "32": 0.004,  # Pinturas
    "25": 0.004,  # Sal, piedras
    "17": 0.003,  # Azucar
    "19": 0.003,  # Cereales/pasteleria
    "09": 0.003,  # Cafe, te
    "68": 0.003,  # Piedra, yeso
    "83": 0.003,  # Manufact. metales
    "82": 0.003,  # Herramientas
    "31": 0.002,  # Abonos
    "47": 0.002,  # Pasta madera
    "95": 0.002,  # Juguetes
    "96": 0.002,  # Manufacturas diversas
}

# Import shares differ from export shares
TARIC_IMPORT_SHARES = {
    "27": 0.160,  # Combustibles (largest import)
    "84": 0.090,  # Maquinas
    "85": 0.080,  # Aparatos electricos
    "87": 0.080,  # Vehiculos
    "30": 0.045,  # Farmaceuticos
    "39": 0.040,  # Plasticos
    "72": 0.030,  # Hierro y acero
    "29": 0.020,  # Quimicos organicos
    "90": 0.015,  # Aparatos opticos
    "61": 0.015,  # Prendas vestir
    "62": 0.015,  # Prendas vestir no punto
    "38": 0.012,  # Otros quimicos
    "73": 0.012,  # Manufact. hierro
    "76": 0.010,  # Aluminio
    "74": 0.010,  # Cobre
    "48": 0.010,  # Papel
    "40": 0.010,  # Caucho
    "28": 0.009,  # Quimicos inorganicos
    "44": 0.008,  # Madera
    "94": 0.008,  # Muebles
    "10": 0.008,  # Cereales
    "03": 0.007,  # Pescados
    "02": 0.006,  # Carne
    "15": 0.006,  # Grasas
    "88": 0.006,  # Aeronaves
    "71": 0.006,  # Joyeria
    "04": 0.005,  # Lacteos
    "33": 0.005,  # Perfumeria
    "70": 0.005,  # Vidrio
    "64": 0.004,  # Calzado
    "22": 0.004,  # Bebidas
    "08": 0.004,  # Frutas
    "07": 0.003,  # Hortalizas
    "21": 0.003,  # Preparaciones alimenticias
    "32": 0.003,  # Pinturas
    "34": 0.003,  # Jabones
    "69": 0.003,  # Ceramica
    "25": 0.003,  # Sal, piedras
    "20": 0.003,  # Conservas verdura
    "68": 0.002,  # Piedra
    "47": 0.002,  # Pasta madera
    "83": 0.002,  # Manufact. metales
    "82": 0.002,  # Herramientas
    "95": 0.002,  # Juguetes
}
