from pathlib import Path
from tempfile import TemporaryDirectory
from services.engines.valuation.ecb_risk_free import parse_ecb_csv
from services.engines.valuation.public_comparables import load_export, normalize_rows
from services.engines.valuation.wacc import beta_from_comparables

def test_parses_latest_dated_ecb_observation():
    payload="TIME_PERIOD,OBS_VALUE\n2026-09-18,3.12\n2026-09-19,3.08\n"
    result=parse_ecb_csv(payload)
    assert result["observation_date"]=="2026-09-19"
    assert result["value"]==.0308
    assert result["status"]=="observed"

def test_normalizes_marketscreener_aliases_and_units():
    result=normalize_rows([{
      "Empresa":"Media SA","Ticker":"MED","Sector":"Media",
      "Beta":"1,20","Capitalización":"500M","Deuda financiera":"100M",
      "Enterprise Value":"580M","EBITDA":"50M","Ventas":"300M",
    }],"marketscreener","2026-09-20")
    row=result["records"][0]
    assert row["archetype"]=="media_content"
    assert row["market_cap"]==500_000_000
    assert row["quality"]["beta_ready"] is True
    assert row["quality"]["multiples_ready"] is True

def test_capital_iq_and_marketscreener_share_schema():
    rows=[{"Company Name":"X","Symbol":"X","Industry":"Advertising",
           "Levered Beta":1.1,"Market Capitalization":100,
           "Total Debt":20,"EBITDA":10,"EV":120}]
    a=normalize_rows(rows,"capital_iq","2026-09-20")["records"][0]
    b=normalize_rows(rows,"marketscreener","2026-09-20")["records"][0]
    assert set(a)==set(b)
    assert a["archetype"]=="advertising"

def test_csv_loader_and_beta_pipeline():
    with TemporaryDirectory() as directory:
        path=Path(directory)/"peers.csv"
        path.write_text("Company,Ticker,Industry,Beta,Market Cap,Total Debt\n"
                        "A,A,Advertising,1.1,100,20\n"
                        "B,B,Advertising,1.2,120,30\n"
                        "C,C,Advertising,1.0,90,15\n"
                        "D,D,Advertising,1.3,130,35\n"
                        "E,E,Advertising,1.15,110,25\n")
        result=load_export(path,"capital_iq","2026-09-20")
        beta=beta_from_comparables(result["records"])
        assert result["record_count"]==5
        assert beta["status"]=="observed_comparables"
        assert beta["target_debt_weight"] is not None

def test_marketscreener_spanish_direct_multiples():
    result=normalize_rows([{
      "Empresa":"Prisa","ISIN":"ES0171743901","Sector BME":"Servicios de Consumo",
      "Subsector BME":"Medios de Comunicación y Publicidad",
      "PER 2025":"12,5","VE/EBITDA 2025":7.2,"VE/ventas 2025":1.1,
      "P/VC 2025":2.0,"Fuente MarketScreener":"https://example.test/valoracion/",
    }],"marketscreener","2025-12-31")
    row=result["records"][0]
    assert row["subsector"]=="Medios de Comunicación y Publicidad"
    assert row["archetype"]=="media_content"
    assert row["per"]==12.5
    assert row["ev_ebitda"]==7.2
    assert row["quality"]["multiples_ready"] is True
    assert row["source_url"].endswith("/valoracion/")

def test_xlsx_loader_finds_decorated_header_row():
    from openpyxl import Workbook
    with TemporaryDirectory() as directory:
        path=Path(directory)/"marketscreener.xlsx"
        workbook=Workbook()
        summary=workbook.active
        summary.title="Medianas"
        summary.append(["Resumen"])
        companies=workbook.create_sheet("Empresas")
        companies.append(["Múltiplos de empresas cotizadas"])
        companies.append([])
        companies.append(["Empresa","ISIN","Sector BME","PER 2025"])
        companies.append(["Media SA","ES0000000001","Medios",10.0])
        workbook.save(path)
        result=load_export(path,"marketscreener","2025-12-31")
        assert result["source_sheet"]=="Empresas"
        assert result["header_row"]==3
        assert result["record_count"]==1
        assert result["records"][0]["per"]==10.0
