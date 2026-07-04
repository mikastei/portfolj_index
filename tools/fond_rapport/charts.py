"""Diagram som base64-PNG för inbäddning i självbärande HTML (inga CDN)."""

from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# Konsekvent färgsättning genom hela rapporten.
STYLE = {
    "REAL": {"color": "#1f4e9c", "linewidth": 2.2, "linestyle": "-"},
    "CUR": {"color": "#e07b39", "linewidth": 1.4, "linestyle": "-"},
    "TGT": {"color": "#2e8b57", "linewidth": 1.4, "linestyle": "-"},
    "BM1": {"color": "#777777", "linewidth": 1.2, "linestyle": "--"},
    "BM2": {"color": "#aaaaaa", "linewidth": 1.2, "linestyle": "--"},
    "BM3": {"color": "#c49a6c", "linewidth": 1.2, "linestyle": ":"},
    # Headline-diagrammet: EGEN (blå, kraftig) mot PA (röd, referensen att slå).
    "EGEN": {"color": "#1f4e9c", "linewidth": 2.6, "linestyle": "-"},
    "PA": {"color": "#b04a4a", "linewidth": 2.2, "linestyle": "-"},
}

CATEGORY_COLORS = ["#1f4e9c", "#e07b39", "#2e8b57", "#b04a4a", "#7a5ca8", "#4aa0b0"]


def _fig_to_base64(fig: plt.Figure) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _new_axes(title: str, ylabel: str) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(9.0, 4.2))
    ax.set_title(title, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, linewidth=0.4, alpha=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(labelsize=8)
    return fig, ax


def line_chart(
    series: list[tuple[str, pd.Series, str]],
    title: str,
    ylabel: str,
    baseline: float | None = None,
) -> str:
    """Linjediagram. series = [(etikett, datumindexerad serie, stilnyckel), ...]."""
    fig, ax = _new_axes(title, ylabel)
    for label, values, style_key in series:
        ax.plot(values.index, values.values, label=label, **STYLE[style_key])
    if baseline is not None:
        ax.axhline(baseline, color="#333333", linewidth=0.7, alpha=0.6)
    ax.legend(fontsize=8, loc="upper left")
    return _fig_to_base64(fig)


def category_chart(series: list[tuple[str, pd.Series]], title: str) -> str:
    """Indexkurvor för kategoriserier, en färg per kategori."""
    fig, ax = _new_axes(title, "Index (bas 100)")
    for i, (label, values) in enumerate(series):
        color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
        ax.plot(values.index, values.values, label=label, color=color, linewidth=1.6)
    ax.axhline(100.0, color="#333333", linewidth=0.7, alpha=0.6)
    ax.legend(fontsize=8, loc="upper left")
    return _fig_to_base64(fig)


EFFECT_COLORS = {"Allokering": "#1f4e9c", "Selektion": "#e07b39", "Interaktion": "#999999"}


def attribution_chart(effects: pd.DataFrame, title: str) -> str:
    """Grupperade staplar: länkade effekter (p.e.) per kategori och komponent."""
    categories = list(effects.index)
    columns = list(effects.columns)
    x = range(len(categories))
    width = 0.8 / len(columns)
    fig, ax = plt.subplots(figsize=(9.0, 4.2))
    for i, column in enumerate(columns):
        offsets = [xi + (i - (len(columns) - 1) / 2) * width for xi in x]
        ax.bar(
            offsets,
            effects[column].values * 100.0,
            width=width,
            label=column,
            color=EFFECT_COLORS.get(column, "#4aa0b0"),
            alpha=0.9,
        )
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories, fontsize=8, rotation=15, ha="right")
    ax.axhline(0.0, color="#333333", linewidth=0.7)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Bidrag (procentenheter)", fontsize=9)
    ax.grid(True, axis="y", linewidth=0.4, alpha=0.5)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8)
    return _fig_to_base64(fig)


def signed_barh_chart(values: pd.Series, title: str, xlabel: str) -> str:
    """Horisontella staplar med tecken (negativa röda, positiva blå)."""
    ordered = values.sort_values()
    colors = ["#b04a4a" if v < 0 else "#1f4e9c" for v in ordered.values]
    fig, ax = plt.subplots(figsize=(9.0, 0.35 * len(ordered) + 1.0))
    ax.barh(ordered.index, ordered.values * 100.0, color=colors, alpha=0.85)
    ax.axvline(0.0, color="#333333", linewidth=0.7)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.grid(True, axis="x", linewidth=0.4, alpha=0.5)
    ax.tick_params(labelsize=8)
    return _fig_to_base64(fig)


def allocation_chart(weights: pd.Series, title: str) -> str:
    """Horisontella staplar för viktsnapshot, sorterade störst först."""
    ordered = weights.sort_values()
    fig, ax = plt.subplots(figsize=(9.0, 0.35 * len(ordered) + 1.0))
    ax.barh(ordered.index, ordered.values * 100.0, color="#1f4e9c", alpha=0.85)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("Vikt (%)", fontsize=9)
    ax.grid(True, axis="x", linewidth=0.4, alpha=0.5)
    ax.tick_params(labelsize=8)
    for y, value in enumerate(ordered.values):
        ax.text(value * 100.0 + 0.3, y, f"{value * 100.0:.1f}", va="center", fontsize=7.5)
    return _fig_to_base64(fig)
