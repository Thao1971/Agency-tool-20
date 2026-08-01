"""Enrutado de intención: niveles, tolerancia a acentos, sinónimos y comparativo-temporal."""

from services.copilot import intent as I


def test_core_levels_unchanged():
    assert I.classify("¿cuál es el EBITDA?")["level"] == "L0"
    assert I.classify("¿cuánto vale la empresa?")["level"] == "L1"
    assert I.classify("¿qué riesgos legales tiene?")["level"] == "L2"
    assert I.classify("¿deberíamos comprarla?")["level"] == "L3"
    assert I.classify("compara estas dos")["level"] == "L4"


def test_accent_and_case_tolerance():
    # sin acentos y en mayúsculas debe clasificar igual
    assert I.classify("cuanto VALE")["level"] == "L1"
    assert I.classify("VALORACION")["targets"] == ["valuation"]
    assert I.classify("margenes")["level"] in ("L0", "L1")   # 'margenes'→cfo (L1)


def test_new_synonyms():
    assert I.classify("¿merece la pena entrar?")["level"] == "L3"
    assert I.classify("¿qué competidores tiene?")["targets"] == ["market"]
    assert I.classify("banderas rojas")["targets"] == ["risk"]


def test_comparative_temporal_is_L3_evolution():
    for q in ("¿ha mejorado respecto al último análisis?", "compárala con la anterior",
              "¿sigue igual que la última vez?"):
        r = I.classify(q)
        assert r["level"] == "L3" and r["kind"] == "evolution", q
    # "compara estas dos" NO es evolución (es comparar dos oportunidades)
    assert I.classify("compara estas dos")["kind"] is None


def test_extract_entities_multientity():
    ents = I.extract_entities("compara ACME y BETACO")
    assert ents == ["ACME", "BETACO"]
    # acrónimos comunes no cuentan como entidad
    assert "EBITDA" not in I.extract_entities("¿cuál es el EBITDA de ACME?")
    assert I.extract_entities("¿cuál es el EBITDA de ACME?") == ["ACME"]


if __name__ == "__main__":
    for fn in (test_core_levels_unchanged, test_accent_and_case_tolerance, test_new_synonyms,
               test_comparative_temporal_is_L3_evolution, test_extract_entities_multientity):
        fn(); print("OK", fn.__name__)
