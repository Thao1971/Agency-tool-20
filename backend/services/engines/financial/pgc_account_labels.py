"""Diccionario code -> etiqueta ES para el desglose completo de balance + PyG
de Iberinform (Fase 6, 2026-09-01).

PROCEDENCIA (importante, no son etiquetas inventadas): las etiquetas en español
son las que el propio Iberinform entrega en la columna `ES_Account_ID` de su CSV
de muestra (`backend/tests/fixtures/iberinform_sample/ES_Financial_Detail_Valu8.csv`,
formato "<codigo> - <etiqueta>"), NO se han redactado a mano. Se han cruzado contra
los codigos que aparecen de verdad en el fichero de produccion
(`data/muestra_25000/Datos_BALANCES.tab`, columna BALANCE_SHEET_ITEM) para quedarnos
solo con los que realmente se usan: 212 codigos en produccion caen dentro de balance
+ PyG (excluyendo Estado de Cambios en Patrimonio Neto, codigos >= 50000, fuera del
alcance de esta fase segun la auditoria), de los cuales 198 tienen etiqueta verificada
y 14 no aparecen en la muestra de Iberinform con etiqueta (UNLABELED_CODES) - se
exponen igualmente con su codigo crudo, nunca se inventa un nombre (R15).

Alcance deliberado: NO incluye el Estado de Cambios en Patrimonio Neto (codigos
51000-59999, muy tecnico, no priorizado por la auditoria) ni el Estado de Flujos de
Efectivo (ya expuesto por otra via, `statements.cashflow` / `statements.cash_flow`).
"""

from typing import Dict, Optional, Tuple

# codigo Iberinform -> (etiqueta ES, seccion)
PGC_ACCOUNT_LABELS: Dict[str, Tuple[str, str]] = {
    # ---- Totales ----
    "10000": ("TOTAL ACTIVO (A + B)", "totales"),
    # ---- A) Activo no corriente ----
    "11000": ("A) ACTIVO NO CORRIENTE", "activo_no_corriente"),
    "11100": ("I. Inmovilizado intangible", "activo_no_corriente"),
    "11110": ("1.Desarrollo", "activo_no_corriente"),
    "11120": ("2.Concesiones", "activo_no_corriente"),
    "11130": ("3.Patentes, licencias, marcas y similares", "activo_no_corriente"),
    "11140": ("4.Fondo de comercio", "activo_no_corriente"),
    "11150": ("5.Aplicaciones informáticas", "activo_no_corriente"),
    "11160": ("6.Investigación", "activo_no_corriente"),
    "11170": ("8.Otro inmovilizado intangible", "activo_no_corriente"),
    "11180": ("7. Propiedad intelectual", "activo_no_corriente"),
    "11200": ("II. Inmovilizado material", "activo_no_corriente"),
    "11210": ("1.Terrenos y construcciones", "activo_no_corriente"),
    "11220": ("2.Instalaciones técnicas y otro inmovilizado material", "activo_no_corriente"),
    "11230": ("3.Inmovilizado en curso y anticipos", "activo_no_corriente"),
    "11300": ("III. Inversiones inmobiliarias", "activo_no_corriente"),
    "11310": ("1.Terrenos", "activo_no_corriente"),
    "11320": ("2.Construcciones", "activo_no_corriente"),
    "11400": ("IV. Inversiones en empresas del grupo y asociadas a largo plazo", "activo_no_corriente"),
    "11410": ("1.Instrumentos de patrimonio", "activo_no_corriente"),
    "11420": ("2.Créditos a empresas", "activo_no_corriente"),
    "11450": ("5.Otros activos financieros", "activo_no_corriente"),
    "11500": ("V. Inversiones financieras a largo plazo", "activo_no_corriente"),
    "11510": ("1.Instrumentos de patrimonio", "activo_no_corriente"),
    "11520": ("2.Créditos a terceros", "activo_no_corriente"),
    "11530": ("3.Valores representativos de deuda", "activo_no_corriente"),
    "11550": ("5.Otros activos financieros", "activo_no_corriente"),
    "11560": ("6.Otras inversiones", "activo_no_corriente"),
    "11600": ("VI. Activos por impuesto diferido", "activo_no_corriente"),
    "11700": ("VII. Deudores comerciales no corrientes", "activo_no_corriente"),
    # ---- B) Activo corriente ----
    "12000": ("B) ACTIVO CORRIENTE", "activo_corriente"),
    "12100": ("I. Activos no corrientes mantenidos para la venta", "activo_corriente"),
    "12200": ("II. Existencias", "activo_corriente"),
    "12210": ("1.Comerciales", "activo_corriente"),
    "12220": ("2.Materias primas y otros aprovisionamientos", "activo_corriente"),
    "12221": ("a) Materias primas y otros aprovisionamientos a largo plazo", "activo_corriente"),
    "12222": ("b) Materias primas y otros aprovisionamientos a corto plazo", "activo_corriente"),
    "12230": ("3.Productos en curso", "activo_corriente"),
    "12231": ("a) De ciclo largo de producción", "activo_corriente"),
    "12232": ("b) De ciclo corto de producción", "activo_corriente"),
    "12240": ("4.Productos terminados", "activo_corriente"),
    "12241": ("a) De ciclo largo de produccción", "activo_corriente"),
    "12242": ("b) De ciclo corto de producción", "activo_corriente"),
    "12250": ("5.Subproductos, residuos y materiales recuperados", "activo_corriente"),
    "12260": ("6.Anticipos a proveedores", "activo_corriente"),
    "12300": ("III. Deudores comerciales y otras cuentas a cobrar", "activo_corriente"),
    "12310": ("1.Clientes por ventas y prestaciones de servicios", "activo_corriente"),
    "12311": ("a) Clientes por ventas y prestaciones de servicios a largo plazo", "activo_corriente"),
    "12312": ("b) Clientes por ventas y prestaciones de servicios a corto plazo", "activo_corriente"),
    "12320": ("2.Clientes empresas del grupo y asociadas", "activo_corriente"),
    "12330": ("3.Deudores varios", "activo_corriente"),
    "12340": ("4.Personal", "activo_corriente"),
    "12350": ("5.Activos por impuesto corriente", "activo_corriente"),
    "12360": ("6.Otros créditos con las Administraciones Públicas", "activo_corriente"),
    "12370": ("2. Accionistas (socios) por desembolsos exigidos", "activo_corriente"),
    "12380": ("1. Clientes por ventas y prestaciones de servicios", "activo_corriente"),
    "12381": ("a) Clientes por ventas y prestaciones de servicios a largo plazo", "activo_corriente"),
    "12382": ("b) Clientes por ventas y prestaciones de servicios a corto plazo", "activo_corriente"),
    "12390": ("3. Otros deudores", "activo_corriente"),
    "12400": ("IV. Inversiones en empresas del grupo y asociadas a corto plazo", "activo_corriente"),
    "12420": ("2.Créditos a empresas", "activo_corriente"),
    "12450": ("5.Otros activos financieros", "activo_corriente"),
    "12500": ("V. Inversiones financieras a corto plazo", "activo_corriente"),
    "12510": ("1.Instrumentos de patrimonio", "activo_corriente"),
    "12520": ("2.Créditos a empresas", "activo_corriente"),
    "12530": ("3.Valores representativos de deuda", "activo_corriente"),
    "12540": ("4.Derivados", "activo_corriente"),
    "12550": ("5.Otros activos financieros", "activo_corriente"),
    "12560": ("6.Otras inversiones", "activo_corriente"),
    "12600": ("VI. Periodificaciones a corto plazo", "activo_corriente"),
    "12700": ("VII. Efectivo y otros activos líquidos equivalentes", "activo_corriente"),
    "12710": ("1.Tesorería", "activo_corriente"),
    "12720": ("2.Otros activos líquidos equivalentes", "activo_corriente"),
    # ---- A) Patrimonio neto ----
    "20000": ("A) PATRIMONIO NETO", "patrimonio_neto"),
    "21000": ("A-1) Fondos propios", "patrimonio_neto"),
    "21100": ("I. Capital", "patrimonio_neto"),
    "21110": ("1. Capital escriturado", "patrimonio_neto"),
    "21120": ("2. (Capital no exigido)", "patrimonio_neto"),
    "21200": ("II. Prima de emisión", "patrimonio_neto"),
    "21300": ("III. Reservas", "patrimonio_neto"),
    "21310": ("1. Legal y estatutarias", "patrimonio_neto"),
    "21320": ("2. Otras reservas", "patrimonio_neto"),
    "21330": ("3. Reserva de revalorización", "patrimonio_neto"),
    "21400": ("IV. (Acciones y participaciones en patrimonio propias)", "patrimonio_neto"),
    "21500": ("V. Resultados de ejercicios anteriores", "patrimonio_neto"),
    "21510": ("1. Remanente", "patrimonio_neto"),
    "21520": ("2. (Resultados negativos de ejercicios anteriores)", "patrimonio_neto"),
    "21600": ("VI. Otras aportaciones de socios", "patrimonio_neto"),
    "21700": ("VII. Resultado del ejercicio", "patrimonio_neto"),
    "21800": ("VIII. (Dividendo a cuenta)", "patrimonio_neto"),
    "21900": ("IX. Otros instrumentos de patrimonio neto", "patrimonio_neto"),
    "22000": ("A-2) Ajustes por cambios de valor", "patrimonio_neto"),
    "22100": ("I. Activos financieros disponibles para la venta", "patrimonio_neto"),
    "22200": ("II. Operaciones de cobertura", "patrimonio_neto"),
    "22400": ("IV. Diferencia de conversión", "patrimonio_neto"),
    "22500": ("V. Otros", "patrimonio_neto"),
    "23000": ("A-3) Subvenciones, donaciones y legados recibidos", "patrimonio_neto"),
    # ---- Totales ----
    "30000": ("TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", "totales"),
    # ---- B) Pasivo no corriente ----
    "31000": ("B) PASIVO NO CORRIENTE", "pasivo_no_corriente"),
    "31100": ("I. Provisiones a largo plazo", "pasivo_no_corriente"),
    "31110": ("1. Obligaciones por prestaciones a largo plazo al personal", "pasivo_no_corriente"),
    "31140": ("4. Otras provisiones", "pasivo_no_corriente"),
    "31200": ("II. Deudas a largo plazo", "pasivo_no_corriente"),
    "31210": ("1. Obligaciones y otros valores negociables", "pasivo_no_corriente"),
    "31220": ("1. Deudas con entidades de crédito", "pasivo_no_corriente"),
    "31230": ("2. Acreedores por arrendamiento financiero", "pasivo_no_corriente"),
    "31250": ("5. Otros pasivos financieros", "pasivo_no_corriente"),
    "31290": ("3. Otras deudas a largo plazo", "pasivo_no_corriente"),
    "31300": ("III. Deudas con empresas del grupo y asociadas a largo plazo", "pasivo_no_corriente"),
    "31400": ("IV. Pasivos por impuesto diferido", "pasivo_no_corriente"),
    "31500": ("V. Periodificaciones a largo plazo", "pasivo_no_corriente"),
    "31700": ("VII. Deuda con características especiales a largo plazo", "pasivo_no_corriente"),
    # ---- C) Pasivo corriente ----
    "32000": ("C) PASIVO CORRIENTE", "pasivo_corriente"),
    "32100": ("I. Pasivos vinculados con activos no corrientes mantenidos para la venta", "pasivo_corriente"),
    "32200": ("II. Provisiones a corto plazo", "pasivo_corriente"),
    "32220": ("2. Otras provisiones", "pasivo_corriente"),
    "32300": ("III. Deudas a corto plazo", "pasivo_corriente"),
    "32310": ("1. Obligaciones y otros valores negociables", "pasivo_corriente"),
    "32320": ("1. Deudas con entidades de crédito", "pasivo_corriente"),
    "32330": ("2. Acreedores por arrendamiento financiero", "pasivo_corriente"),
    "32350": ("5. Otros pasivos financieros", "pasivo_corriente"),
    "32390": ("3. Otras deudas a corto plazo", "pasivo_corriente"),
    "32400": ("IV. Deudas con empresas del grupo y asociadas a corto plazo", "pasivo_corriente"),
    "32500": ("V. Acreedores comerciales y otras cuentas a pagar", "pasivo_corriente"),
    "32510": ("1. Proveedores", "pasivo_corriente"),
    "32511": ("a) Proveedores a largo plazo", "pasivo_corriente"),
    "32512": ("b) Proveedores a corto plazo", "pasivo_corriente"),
    "32520": ("2. Proveedores, empresas del grupo y asociadas", "pasivo_corriente"),
    "32530": ("3. Acreedores varios", "pasivo_corriente"),
    "32540": ("4. Personal (remuneraciones pendientes de pago)", "pasivo_corriente"),
    "32550": ("5. Pasivos por impuesto corriente", "pasivo_corriente"),
    "32560": ("6. Otras deudas con las Administraciones Públicas", "pasivo_corriente"),
    "32570": ("7. Anticipos de clientes", "pasivo_corriente"),
    "32580": ("1. Proveedores", "pasivo_corriente"),
    "32581": ("a) Proveedores a largo plazo", "pasivo_corriente"),
    "32582": ("b) Proveedores a corto plazo", "pasivo_corriente"),
    "32590": ("2. Otros acreedores", "pasivo_corriente"),
    "32600": ("VI. Periodificaciones a corto plazo", "pasivo_corriente"),
    "32700": ("VII. Deuda con características especiales a corto plazo", "pasivo_corriente"),
    # ---- A) Resultado de explotacion ----
    "40100": ("1. Importe neto de la cifra de negocios", "resultado_explotacion"),
    "40110": ("a) Ventas", "resultado_explotacion"),
    "40120": ("b) Prestaciones de servicios", "resultado_explotacion"),
    "40130": ("c) Ingresos de carácter financiero de las sociedades holding", "resultado_explotacion"),
    "40200": ("2. Variación de existencias de productos terminados y en curso de fabricación", "resultado_explotacion"),
    "40300": ("3. Trabajos realizados por la empresa para su activo", "resultado_explotacion"),
    "40400": ("4. Aprovisionamientos", "resultado_explotacion"),
    "40410": ("a) Consumo de mercaderías", "resultado_explotacion"),
    "40420": ("b) Consumo de materias primas y otras materias consumibles", "resultado_explotacion"),
    "40430": ("c) Trabajos realizados por otras empresas", "resultado_explotacion"),
    "40440": ("d) Deterioro de mercaderías, materias primas y otros aprovisionamientos", "resultado_explotacion"),
    "40500": ("5. Otros ingresos de explotación", "resultado_explotacion"),
    "40510": ("a) Ingresos accesorios y otros de gestión corriente", "resultado_explotacion"),
    "40520": ("b) Subvenciones de explotación incorporadas al resultado del ejercicio", "resultado_explotacion"),
    "40600": ("6. Gastos de personal", "resultado_explotacion"),
    "40610": ("a) Sueldos, salarios y asimilados", "resultado_explotacion"),
    "40620": ("b) Cargas sociales", "resultado_explotacion"),
    "40630": ("c) Provisiones", "resultado_explotacion"),
    "40700": ("7. Otros gastos de explotación", "resultado_explotacion"),
    "40710": ("a) Servicios exteriores", "resultado_explotacion"),
    "40720": ("b) Tributos", "resultado_explotacion"),
    "40730": ("c) Pérdidas, deterioro y variación de provisiones por operaciones comerciales", "resultado_explotacion"),
    "40740": ("d) Otros gastos de gestión corriente", "resultado_explotacion"),
    "40800": ("8. Amortización del inmovilizado", "resultado_explotacion"),
    "40900": ("9. Imputación de subvenciones de inmovilizado no financiero y otras", "resultado_explotacion"),
    "41000": ("10. Excesos de provisiones", "resultado_explotacion"),
    "41100": ("11. Deterioro y resultado por enajenaciones del inmovilizado", "resultado_explotacion"),
    "41110": ("a) Deterioro y pérdidas", "resultado_explotacion"),
    "41120": ("b) Resultados por enajenaciones y otras", "resultado_explotacion"),
    "41130": ("c) Deterioro y resultados por enajenaciones del inmovilizado de las sociedades holding", "resultado_explotacion"),
    "41300": ("13. Otros resultados", "resultado_explotacion"),
    # ---- B) Resultado financiero ----
    "41400": ("14. Ingresos financieros", "resultado_financiero"),
    "41410": ("a) De participaciones en instrumentos de patrimonio", "resultado_financiero"),
    "41411": ("a 1) En empresas del grupo y asociadas", "resultado_financiero"),
    "41412": ("a 2) En terceros", "resultado_financiero"),
    "41420": ("b) De valores negociables y otros instrumentos financieros", "resultado_financiero"),
    "41421": ("b 1) De empresas del grupo y asociadas", "resultado_financiero"),
    "41422": ("b 2) De terceros", "resultado_financiero"),
    "41430": ("a) Imputación de subvenciones, donaciones y legados de carácter financiero", "resultado_financiero"),
    "41490": ("b) Otros ingresos financieros", "resultado_financiero"),
    "41500": ("15. Gastos financieros", "resultado_financiero"),
    "41510": ("a) Por deudas con empresas del grupo y asociadas", "resultado_financiero"),
    "41520": ("b) Por deudas con terceros", "resultado_financiero"),
    "41530": ("c) Por actualización de provisiones", "resultado_financiero"),
    "41600": ("16. Variación de valor razonable en instrumentos financieros", "resultado_financiero"),
    "41610": ("a) Cartera de negociación y otros", "resultado_financiero"),
    "41620": ("b) Imputación al resultado del ejercicio por activos financieros disponibles para la venta", "resultado_financiero"),
    "41700": ("17. Diferencias de cambio", "resultado_financiero"),
    "41800": ("18. Deterioro y resultado por enajenaciones de instrumentos financieros", "resultado_financiero"),
    "41810": ("a) Deterioros y pérdidas", "resultado_financiero"),
    "41820": ("b) Resultados por enajenaciones y otras", "resultado_financiero"),
    "41900": ("20. Impuestos sobre beneficios", "resultado_financiero"),
    "42100": ("19. Otros ingresos y gastos de carácter financiero", "resultado_financiero"),
    "42130": ("c) Resto de ingresos y gastos", "resultado_financiero"),
    # ---- Subtotales de la cuenta de PyG ----
    "49100": ("A) RESULTADO DE EXPLOTACIÓN (1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12 + 13)", "resultado_totales"),
    "49200": ("B) RESULTADO FINANCIERO (14 + 15 + 16 + 17 + 18 + 19)", "resultado_totales"),
    "49300": ("C) RESULTADO ANTES DE IMPUESTOS (A + B)", "resultado_totales"),
    "49400": ("A.4) RESULTADO DEL EJERCICIO PROCEDENTE DE OPERACIONES CONTINUADAS (A.3 + 20)", "resultado_totales"),
    "49500": ("D) RESULTADO DEL EJERCICIO (C + 20)", "resultado_totales"),
}

# Codigos que aparecen en el fichero de produccion dentro del alcance balance/PyG
# pero sin etiqueta verificada en la muestra de Iberinform - se exponen con su
# codigo crudo (nunca se fabrica un nombre, R15).
UNLABELED_CODES = ['11430', '12430', '12460', '22300', '31120', '31240', '31600', '32210', '32340', '40750', '41200', '42000', '42110', '42120']


def curate_breakdown(accounts: Optional[Dict[str, float]]) -> Optional[Dict[str, Dict]]:
    """`accounts`: dict codigo -> importe, tal cual `norm_financials.<doc>.accounts`.
    Devuelve dict `codigo -> {value, label_es, section}` para cada codigo presente Y
    etiquetado (`PGC_ACCOUNT_LABELS`); los codigos de `UNLABELED_CODES` presentes se
    devuelven con `label_es: None` (para que la Ficha decida si los pinta con el codigo
    crudo o los omite - nunca se les fabrica un nombre). `None` si no hay nada que
    mostrar. R15: nunca inventa ni interpola un importe que Iberinform no entrego."""
    if not accounts:
        return None
    out: Dict[str, Dict] = {}
    for code, val in accounts.items():
        if val is None:
            continue
        meta = PGC_ACCOUNT_LABELS.get(code)
        if meta:
            label, section = meta
            out[code] = {"value": val, "label_es": label, "section": section}
        elif code in UNLABELED_CODES:
            out[code] = {"value": val, "label_es": None, "section": "otros"}
    return out or None
