"""Document Intelligence Studio — Core models and block types.

Universal document model: Document → Section[] → Block[]
Every block has data_lineage for full traceability.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from models import new_id, now_iso


# ══════════════════════════════════════════
# BLOCK TYPES
# ══════════════════════════════════════════

BLOCK_TYPES = [
    "cover", "text", "kpi", "table", "chart",
    "insight", "image", "divider", "appendix",
]

CHART_TYPES = [
    "bar", "line", "area", "scatter", "bubble",
    "waterfall", "treemap", "histogram",
]


def new_block(block_type: str, **kwargs) -> Dict:
    """Create a new block with data lineage."""
    if block_type not in BLOCK_TYPES:
        raise ValueError(f"Unknown block type: {block_type}")

    block = {
        "block_id": new_id(),
        "block_type": block_type,
        "data": kwargs.get("data", {}),
        "data_lineage": kwargs.get("data_lineage", {
            "source": "manual",
            "dataset": None,
            "query_date": now_iso(),
            "prompt": None,
            "model": None,
        }),
        "created_at": now_iso(),
    }
    return block


def new_section(title: str, order: int, blocks: List[Dict] = None) -> Dict:
    return {
        "section_id": new_id(),
        "title": title,
        "order": order,
        "blocks": blocks or [],
    }


def new_document(title: str, template_id: str = None, brand_id: str = None,
                 created_by: str = None, description: str = "") -> Dict:
    now = now_iso()
    return {
        "document_id": new_id(),
        "title": title,
        "description": description,
        "template_id": template_id,
        "brand_id": brand_id,
        "status": "draft",
        "version": 1,
        "sections": [],
        "metadata": {},
        "created_at": now,
        "updated_at": now,
        "created_by": created_by,
    }


# ══════════════════════════════════════════
# BLOCK BUILDERS (typed constructors)
# ══════════════════════════════════════════

def cover_block(title: str, subtitle: str = "", logo: str = None, bg_image: str = None) -> Dict:
    return new_block("cover", data={
        "title": title, "subtitle": subtitle, "logo": logo, "background_image": bg_image,
    })


def text_block(content: str, style: str = "body") -> Dict:
    return new_block("text", data={"content": content, "style": style})


def kpi_block(title: str, value: Any, unit: str = "", variation: str = None,
              benchmark: str = None, commentary: str = None) -> Dict:
    return new_block("kpi", data={
        "title": title, "value": value, "unit": unit,
        "variation": variation, "benchmark": benchmark, "commentary": commentary,
    })


def table_block(title: str, columns: List[str], rows: List[List[Any]]) -> Dict:
    return new_block("table", data={"title": title, "columns": columns, "rows": rows})


def chart_block(title: str, chart_type: str, dataset: Dict, config: Dict = None) -> Dict:
    return new_block("chart", data={
        "title": title, "chart_type": chart_type, "dataset": dataset, "config": config or {},
    })


def insight_block(title: str, summary: str, importance: str = "medium",
                  source_ref: str = None) -> Dict:
    return new_block("insight", data={
        "title": title, "summary": summary, "importance": importance,
        "source_reference": source_ref,
    })


def divider_block() -> Dict:
    return new_block("divider")
