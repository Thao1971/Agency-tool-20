"""Server-side chart generation for valuation reports using matplotlib → base64 PNG."""

import io
import base64
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Suppress matplotlib GUI backend
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def _fig_to_base64(fig, dpi=150) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', transparent=True)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _style_chart(ax, bg_color='#FAF9F9', text_color='#1B1C1C', grid_color='#ECE9E7'):
    ax.set_facecolor(bg_color)
    ax.figure.set_facecolor(bg_color)
    ax.tick_params(colors=text_color, labelsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(grid_color)
    ax.spines['bottom'].set_color(grid_color)
    ax.yaxis.label.set_color(text_color)
    ax.xaxis.label.set_color(text_color)
    ax.title.set_color(text_color)


def chart_ev_scenarios(ev_low: float, ev_mid: float, ev_high: float,
                       currency: str = "M", accent: str = "#6D5E00") -> str:
    """Bar chart: EV low / mid / high scenarios."""
    fig, ax = plt.subplots(figsize=(5, 2.5))
    _style_chart(ax)

    def fmt(v):
        if abs(v) >= 1_000_000: return f'{v/1e6:.1f}M'
        if abs(v) >= 1_000: return f'{v/1e3:.0f}K'
        return f'{v:.0f}'

    labels = ['Conservative', 'Base Case', 'Optimistic']
    values = [ev_low, ev_mid, ev_high]
    colors = ['#C3C6CB', accent, '#E1C422']

    bars = ax.barh(labels, values, color=colors, height=0.5, edgecolor='none')
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height()/2,
                fmt(val), va='center', fontsize=9, color='#1B1C1C', fontweight='bold')

    ax.set_xlim(0, max(values) * 1.25)
    ax.xaxis.set_visible(False)
    ax.invert_yaxis()
    plt.tight_layout()
    return _fig_to_base64(fig)


def chart_ev_to_equity(ev_mid: float, net_debt: float, equity_mid: float,
                       currency: str = "M", accent: str = "#6D5E00") -> str:
    """Waterfall chart: EV → net debt → equity value."""
    fig, ax = plt.subplots(figsize=(5, 2.5))
    _style_chart(ax)

    def fmt(v):
        if abs(v) >= 1_000_000: return f'{v/1e6:.1f}M'
        if abs(v) >= 1_000: return f'{v/1e3:.0f}K'
        return f'{v:.0f}'

    labels = ['Enterprise\nValue', 'Net Debt', 'Equity\nValue']
    bars = ax.bar(labels, [ev_mid, abs(net_debt), equity_mid], bottom=[0, equity_mid, 0],
                  color=[accent, '#DC2626', '#E1C422'], width=0.5, edgecolor='none')

    positions = [ev_mid / 2, equity_mid + abs(net_debt) / 2, equity_mid / 2]
    texts = [fmt(ev_mid), fmt(-abs(net_debt)), fmt(equity_mid)]
    for i, (pos, txt) in enumerate(zip(positions, texts)):
        ax.text(i, pos, txt, ha='center', va='center', fontsize=9,
                color='white', fontweight='bold')

    ax.yaxis.set_visible(False)
    ax.spines['left'].set_visible(False)
    plt.tight_layout()
    return _fig_to_base64(fig)


def chart_quality_breakdown(breakdown: Dict, accent: str = "#6D5E00") -> str:
    """Horizontal bars: quality score breakdown by dimension."""
    fig, ax = plt.subplots(figsize=(5, 2.5))
    _style_chart(ax)

    labels = list(breakdown.keys())
    values = [breakdown[k] for k in labels]
    # Clean labels
    clean_labels = [k.replace('_', ' ').title() for k in labels]

    colors = [accent if v >= 70 else '#E1C422' if v >= 50 else '#C3C6CB' for v in values]
    bars = ax.barh(clean_labels, values, color=colors, height=0.5, edgecolor='none')

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                f'{val:.0f}', va='center', fontsize=8, color='#44474A')

    ax.set_xlim(0, 105)
    ax.invert_yaxis()
    ax.xaxis.set_visible(False)
    plt.tight_layout()
    return _fig_to_base64(fig)


def chart_financial_history(history: List[Dict], accent: str = "#6D5E00") -> str:
    """Line/bar chart: revenue + EBITDA evolution."""
    if not history or len(history) < 2:
        return ""

    fig, ax1 = plt.subplots(figsize=(5, 2.8))
    _style_chart(ax1)

    years = [str(h.get('year', '')) for h in history]
    revenue = [h.get('revenue', 0) or 0 for h in history]
    ebitda = [h.get('ebitda', 0) or 0 for h in history]

    x = range(len(years))
    width = 0.35

    bars = ax1.bar([i - width/2 for i in x], revenue, width, label='Revenue', color='#C3C6CB', edgecolor='none')
    bars2 = ax1.bar([i + width/2 for i in x], ebitda, width, label='EBITDA', color=accent, edgecolor='none')

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(years, fontsize=8)
    ax1.legend(fontsize=7, frameon=False)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))

    plt.tight_layout()
    return _fig_to_base64(fig)


def chart_cost_structure(costs: Dict, accent: str = "#6D5E00") -> str:
    """Horizontal bar chart: cost breakdown."""
    if not costs:
        return ""

    fig, ax = plt.subplots(figsize=(5, 2.2))
    _style_chart(ax)

    # Filter out zero/none values
    items = [(k.replace('_', ' ').title(), abs(v)) for k, v in costs.items() if v and v != 0]
    if not items:
        plt.close(fig)
        return ""

    items.sort(key=lambda x: x[1], reverse=True)
    labels, values = zip(*items[:6])

    colors_list = [accent, '#E1C422', '#C3C6CB', '#ECE9E7', '#F3F1F0', '#FAF9F9']
    bars = ax.barh(labels, values, color=colors_list[:len(values)], height=0.5, edgecolor='none')

    for bar, val in zip(bars, values):
        label = f'{val/1e6:.1f}M' if val >= 1e6 else f'{val/1e3:.0f}K'
        ax.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height()/2,
                label, va='center', fontsize=8, color='#44474A')

    ax.set_xlim(0, max(values) * 1.3)
    ax.xaxis.set_visible(False)
    ax.invert_yaxis()
    plt.tight_layout()
    return _fig_to_base64(fig)


def chart_benchmark_percentiles(percentiles: Dict, accent: str = "#6D5E00") -> str:
    """Horizontal bars: percentile positioning."""
    if not percentiles:
        return ""

    fig, ax = plt.subplots(figsize=(5, 2))
    _style_chart(ax)

    labels = [k.replace('_', ' ').replace('percentile', '').strip().title() for k in percentiles.keys()]
    values = list(percentiles.values())

    colors = [accent if v >= 70 else '#E1C422' if v >= 50 else '#DC2626' for v in values]
    bars = ax.barh(labels, values, color=colors, height=0.45, edgecolor='none')

    # Add percentile markers
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                f'P{val:.0f}', va='center', fontsize=8, color='#44474A', fontweight='bold')

    ax.set_xlim(0, 105)
    ax.axvline(x=50, color='#C3C6CB', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.invert_yaxis()
    ax.xaxis.set_visible(False)
    plt.tight_layout()
    return _fig_to_base64(fig)
