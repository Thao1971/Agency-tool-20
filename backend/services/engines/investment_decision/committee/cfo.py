"""CFO — finanzas y calidad del beneficio. Lee Financial Intelligence (kpis/evolution).
Determinista. Umbrales: margen EBITDA vs bandas; apalancamiento deuda neta/EBITDA;
autonomía financiera (PN/activo)."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence

_FIN = "financial-intelligence"


class CFO(Specialist):
    name = "cfo"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        evo = ev.get("evolution") or {}
        pts = sorted([p for p in (evo.get("points") or []) if p.get("year")], key=lambda x: x["year"])
        last = pts[-1] if pts else {}
        margin = kp.get("ebitda_margin")
        cagr = kp.get("revenue_cagr")
        solvency = kp.get("solvency")
        ebitda = kp.get("ebitda") or last.get("ebitda")
        nfp = last.get("net_financial_position")

        subs, evid, strengths, weaknesses, risks, conditions = [], [], [], [], [], []
        if margin is None and cagr is None and solvency is None:
            return self._abstain("Sin datos financieros suficientes para el CFO.")

        # Margen EBITDA (0..1): <5%→0.2, 10%→0.5, 15%→0.75, ≥20%→1.0
        if margin is not None:
            m = float(margin)
            sm = 0.2 if m < 0.05 else 0.5 if m < 0.10 else 0.75 if m < 0.20 else 1.0
            subs.append(sm)
            evid.append(M.evidence(_FIN, "financial", "ebitda_margin", round(m, 4)))
            (strengths if sm >= 0.75 else weaknesses).append(
                M.finding(f"Margen EBITDA del {m*100:.1f}%.", [evid[-1]]))

        # Crecimiento (CAGR)
        if cagr is not None:
            g = float(cagr)
            sg = 1.0 if g >= 0.10 else 0.7 if g >= 0.03 else 0.4 if g >= 0 else 0.2
            subs.append(sg)
            evid.append(M.evidence(_FIN, "financial", "revenue_cagr", round(g, 4)))
            (strengths if sg >= 0.7 else weaknesses).append(
                M.finding(f"CAGR de ingresos {g*100:+.1f}%.", [evid[-1]]))

        # Apalancamiento deuda neta / EBITDA
        if nfp is not None and ebitda:
            lev = nfp / ebitda
            sl = 1.0 if lev < 0 else 0.85 if lev < 2 else 0.6 if lev < 3 else 0.35 if lev < 4 else 0.15
            subs.append(sl)
            evid.append(M.evidence(_FIN, "financial", "net_debt_ebitda", round(lev, 2)))
            if lev >= 3:
                conditions.append("Ajustar precio o estructura por apalancamiento elevado (deuda neta/EBITDA ≥ 3x).")
                risks.append(M.finding(f"Apalancamiento deuda neta/EBITDA {lev:.1f}x.", [evid[-1]]))

        # Autonomía financiera
        if solvency is not None:
            sv = float(solvency)
            ss = 1.0 if sv >= 0.5 else 0.7 if sv >= 0.3 else 0.4 if sv >= 0.15 else 0.15
            subs.append(ss)
            evid.append(M.evidence(_FIN, "financial", "solvency", round(sv, 4)))

        score = round(sum(subs) / len(subs), 4) if subs else 0.0
        conf = simple_confidence(len(subs), 4)
        rec = M.REC_CONDITIONS if (conditions and rec_from_score(score) == M.REC_PROCEED) else rec_from_score(score)
        return M.opinion(self.name, rec, score, conf, strengths=strengths, weaknesses=weaknesses,
                         risks=risks, conditions=conditions, evidence_list=evid,
                         weight_base=S.COMMITTEE_WEIGHTS[self.name])
