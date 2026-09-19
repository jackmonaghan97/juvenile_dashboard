"""
Shared plotly styling: one palette, fixed entity -> color assignments, a base layout.

Colors follow the entity (a race, a category) and never its rank, so filtering
never repaints the survivors. Categorical hues are assigned in a fixed order.
"""
import functools
import html
import uuid
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import plotly
import plotly.graph_objects as go
from shiny import render, ui

PLOTLY_JS_DIR = Path(plotly.__file__).parent / "package_data"   # holds plotly.min.js

# ---------------------------------------------------------------- palette (light surface)
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# ICJIA brand: navy for chrome (nav, primary tiles, buttons), blue as the first chart hue
NAVY = "#0a3a60"
NAVY_2 = "#0e4471"
BLUE = "#1565c0"
STEEL = "#466c8c"
BLUE_TINT = "#ebf6ff"

SERIES = [BLUE, "#e36209", "#22863a", "#e8a600",
          "#6f42c1", "#d73a49", STEEL, "#8a6d3b"]
SEQ_BLUE = [BLUE_TINT, "#bcd8f5", "#8fbbea", "#5f9bdc", BLUE, NAVY_2, NAVY]
# choropleth fills: every stop is at least 3:1 against the page (WCAG 1.4.11), so the
# lightest counties still stand out from the white county borders and the page
MAP_SCALE = ["#4f95dd", "#2a7bd0", BLUE, "#0c4a8f", NAVY, "#041d33"]
MAP_OUTLINE = INK
# marker shapes cycle with the series colors so lines stay apart without color
SYMBOLS = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon"]
DIVERGING = [[0.0, BLUE], [0.5, "#f0efec"], [1.0, "#d73a49"]]

# ---------------------------------------------------------------- fixed entity colors
def rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,a)' so a tint also shows in the legend swatch."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _ramp(colors: list[str], n: int) -> list[str]:
    """n evenly spaced hex colors interpolated along a list of hex stops."""
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]
    out = []
    for k in range(n):
        t = k / (n - 1) * (len(rgb) - 1)
        i = min(int(t), len(rgb) - 2)
        f = t - i
        out.append("#" + "".join(f"{round(a + (b - a) * f):02x}" for a, b in zip(rgb[i], rgb[i + 1])))
    return out


# colors follow the entity, never its rank, so filtering never repaints the survivors
CASE_COLOR = dict(zip(["probation", "supervision", "cus", "informal", "other"], SERIES[:4] + [MUTED]))
LEVEL_COLOR = dict(zip(["max", "med", "min", "unclassified"], [NAVY, BLUE, "#8fbbea", MUTED]))
CASELOAD_COLOR = {"Active supervision": BLUE, "Administrative – active": "#8fbbea",
                  "Administrative – inactive": AXIS}
OUTCOME_COLOR = {"Successful": SERIES[2], "Unsuccessful": SERIES[5], "Other": MUTED}
VIOLATION_COLOR = {"technical": SERIES[3], "new offense": SERIES[5]}
RACE_COLOR = dict(zip(["black", "white", "hispanic", "asian", "american indian", "other"], SERIES[:5] + [STEEL]))
SEX_COLOR = dict(zip(["male", "female"], SERIES[:2]))
AGE_COLOR = dict(zip(["12-under", "13", "14", "15", "16", "17-over"], _ramp(["#bcd8f5", BLUE, NAVY], 6)))
PETITION_COLOR = dict(zip(["delinquency", "addiction", "mrai", "truancy", "neglect/abuse", "dependent"],
                          SERIES[:5] + [STEEL]))
DJJ_COLOR = dict(zip(["full", "evaluation", "habitual juvenile offender", "violent juvenile offender"],
                     [NAVY, BLUE, "#8fbbea", SERIES[5]]))
SUBGROUP_COLOR = {"formal": NAVY, "informal": "#8fbbea"}
FLOW_COLOR = {"Admissions": SERIES[0], "Discharges": SERIES[1], "Net change": SERIES[2]}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# ---------------------------------------------------------------- base layout
def base_layout(height: int = 360, **overrides) -> dict:
    layout = dict(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=13, color=INK_2),
        margin=dict(l=8, r=16, t=16, b=8),
        hovermode="closest",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=GRID,
                        font=dict(family=FONT, size=12, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    traceorder="normal",
                    font=dict(size=12, color=INK_2), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, linecolor=AXIS, linewidth=1, ticks="",
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED)),
                   zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, gridwidth=1, linecolor="rgba(0,0,0,0)",
                   ticks="", tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED)),
                   zeroline=True, zerolinecolor=AXIS, zerolinewidth=1),
        bargap=0.35,
        bargroupgap=0.08,
    )
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(layout.get(k), dict):
            layout[k] = {**layout[k], **v}
        else:
            layout[k] = v
    return layout


def figure(height: int = 360, **overrides) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**base_layout(height, **overrides))
    return fig


def bar_marker(color: str, gap: bool = True) -> dict:
    """Thin fill with a 2px surface gap so adjacent/stacked segments never touch."""
    m = dict(color=color)
    if gap:
        m.update(line=dict(color=SURFACE, width=2))
    return m


def hatch_lines(geojson: dict, names, spacing: float = 0.07) -> tuple[list, list]:
    """
    45-degree hatching clipped to the named polygons, as one lon / lat pair of lists with
    None breaks between segments (a single scattergeo line trace). Lines are laid out in
    Mercator space so they look diagonal on the map, `spacing` is in degrees of longitude.
    """
    def merc(lat):
        return np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))

    def unmerc(y):
        return np.degrees(2 * np.arctan(np.exp(np.radians(y))) - np.pi / 2)

    r2 = np.sqrt(2)
    lons, lats = [], []
    for feat in geojson["features"]:
        if feat["properties"]["name"] not in set(names):
            continue
        for ring in feat["geometry"]["coordinates"]:      # every ring, outer and holes, clips alike
            pts = np.asarray(ring, dtype=float)
            x, y = pts[:, 0], merc(pts[:, 1])
            u, v = (x + y) / r2, (y - x) / r2               # rotate -45°: hatch lines become v = const
            u0, u1, v0, v1 = u[:-1], u[1:], v[:-1], v[1:]
            for k in np.arange(np.ceil(v.min() / spacing), v.max() / spacing) * spacing:
                hit = (np.minimum(v0, v1) < k) & (k <= np.maximum(v0, v1))
                if not hit.any():
                    continue
                cross = np.sort(u0[hit] + (k - v0[hit]) * (u1[hit] - u0[hit]) / (v1[hit] - v0[hit]))
                for a, b in zip(cross[0::2], cross[1::2]):  # inside the polygon between crossing pairs
                    seg_u, seg_v = np.array([a, b]), np.array([k, k])
                    lons += list((seg_u - seg_v) / r2) + [None]
                    lats += list(unmerc((seg_u + seg_v) / r2)) + [None]
    return lons, lats


def outer_boundary(geojson: dict) -> tuple[list, list]:
    """
    The outline of a set of polygons that tile an area (the state line around the county
    map), as lon / lat lists with None breaks. Every edge shared by two counties appears
    twice and cancels; the edges left over are the outside, chained into loops.
    """
    edges = Counter()
    for feat in geojson["features"]:
        for ring in feat["geometry"]["coordinates"]:
            pts = [tuple(p) for p in ring]
            edges.update(frozenset((a, b)) for a, b in zip(pts[:-1], pts[1:]))
    adj = {}
    for e, n in edges.items():
        if n == 1:
            a, b = tuple(e)
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
    lons, lats, seen = [], [], set()
    for start in adj:
        if start in seen:
            continue
        prev, cur = None, start
        while cur not in seen:
            seen.add(cur)
            lons.append(cur[0]); lats.append(cur[1])
            nxt = [v for v in adj[cur] if v != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        lons += [start[0], None]; lats += [start[1], None]     # close the loop
    return lons, lats


def choropleth(geojson: dict, values, *, height: int = 480, tickformat: str = ",.0f",
               hovertemplate: str, customdata=None, highlight: str | None = None,
               missing=None, missing_label: str = "Not reported",
               outline: tuple[list, list] | None = None) -> go.Figure:
    """
    Illinois county map on MAP_SCALE. `values` is a Series keyed by county. Counties in
    `missing` are drawn grey with a grey outline and diagonal hatching; `outline` (lon /
    lat lists from outer_boundary) is drawn as a black state line.
    """
    n = len(MAP_SCALE) - 1
    fig = go.Figure(go.Choropleth(
        geojson=geojson, featureidkey="properties.name",
        locations=values.index, z=values.values,
        colorscale=[[i / n, c] for i, c in enumerate(MAP_SCALE)],
        marker=dict(line=dict(color=SURFACE, width=0.8)),
        colorbar=dict(thickness=10, len=0.6, outlinewidth=0, tickfont=dict(color=MUTED),
                      tickformat=tickformat),
        customdata=customdata, hovertemplate=hovertemplate,
    ))
    if outline is not None:
        fig.add_scattergeo(lon=outline[0], lat=outline[1], mode="lines", line=dict(color=MAP_OUTLINE, width=1.5),
                           hoverinfo="skip", showlegend=False)
    missing = [m for m in (missing or []) if m not in values.index]
    if missing:
        fig.add_choropleth(geojson=geojson, featureidkey="properties.name", locations=missing,
                           z=[0] * len(missing), showscale=False, colorscale=[[0, "#efefec"], [1, "#efefec"]],
                           marker=dict(line=dict(color=MUTED, width=1.2)),
                           hovertemplate=f"<b>%{{location}}</b><br>{missing_label}<extra></extra>")
        lons, lats = hatch_lines(geojson, missing)
        fig.add_scattergeo(lon=lons, lat=lats, mode="lines", line=dict(color=MUTED, width=1),
                           hoverinfo="skip", showlegend=False)
    if highlight and highlight in values.index:
        fig.add_choropleth(geojson=geojson, featureidkey="properties.name", locations=[highlight],
                           z=[0], showscale=False, colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                           marker=dict(line=dict(color=INK, width=2.5)), hoverinfo="skip")
    fig.update_layout(**base_layout(height, margin=dict(l=0, r=0, t=0, b=0)))
    fig.update_geos(fitbounds="locations", visible=False, bgcolor=SURFACE, projection_type="mercator")
    return fig


def _vline_x(x):
    """add_vline with an annotation cannot take a Timestamp on a date axis; epoch milliseconds work."""
    return x.timestamp() * 1000 if isinstance(x, pd.Timestamp) else x


def mark_view(fig: go.Figure, x, text: str) -> None:
    """Solid vertical line for the period the page is showing, labelled at the bottom."""
    fig.add_vline(x=_vline_x(x), line=dict(color=AXIS, width=1), annotation_text=text,
                  annotation_position="bottom left", annotation_font=dict(color=MUTED, size=11))


def mark_wip(fig: go.Figure, x, text: str = "Still being reported →") -> None:
    """Dashed vertical line from which the data are incomplete, labelled at the top."""
    fig.add_vline(x=_vline_x(x), line=dict(color=MUTED, width=1, dash="dash"), annotation_text=text,
                  annotation_position="top right", annotation_font=dict(color=MUTED, size=11))


def stacked_area(fig: go.Figure, piv: pd.DataFrame, colors: dict, labels=None, *, hover: str = "%{y:,.0f}") -> None:
    """
    Stacked area series with a surface-colored seam between bands and each band's name
    written at its right-hand end, so the stack reads without relying on color alone.
    """
    labels = labels or (lambda c: c)
    cum = piv.cumsum(axis=1)
    for c in piv.columns:
        fig.add_scatter(name=labels(c), x=piv.index, y=piv[c], mode="lines", stackgroup="one",
                        line=dict(width=1.5, color=SURFACE), fillcolor=colors[c], hovertemplate=hover)
    last = piv.index[-1]
    ys = {c: cum.loc[last, c] - piv.loc[last, c] / 2 for c in piv.columns if piv.loc[last, c] > 0}
    gap = 0.045 * float(cum.iloc[-1].max() or 1)             # labels are ~11px; keep them a band apart
    prev = -gap
    for c in sorted(ys, key=ys.get):                          # bottom up: push a label up if it would overlap
        ys[c] = max(ys[c], prev + gap)
        prev = ys[c]
        fig.add_annotation(x=last, y=ys[c], text=labels(c), showarrow=False, xanchor="left", xshift=4,
                           font=dict(size=11, color=INK_2), bgcolor=rgba(SURFACE, 0.85))
    fig.update_layout(margin=dict(r=110))


def describe(fig: go.Figure, text: str) -> go.Figure:
    """Attach alternative text (what the chart shows, not an analysis) for screen readers."""
    fig.update_layout(meta={**(fig.layout.meta or {}), "alt": text})
    return fig


def alt_values(pairs, fmt: str = "{:,.0f}") -> str:
    """'A 1,234; B 567' for the values part of an alt text."""
    return "; ".join(f"{k} {fmt.format(v)}" for k, v in pairs if not pd.isna(v))


def empty_figure(message: str = "No data for this selection", height: int = 360) -> go.Figure:
    fig = figure(height)
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False))
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(color=MUTED, size=14))
    return describe(fig, f"Empty chart: {message.lower()}.")


# ---------------------------------------------------------------- rendering
PLOT_CONFIG = '{"responsive": true, "displayModeBar": false, "scrollZoom": false}'


def plot_html(fig: go.Figure) -> ui.HTML:
    """
    A figure as a div + Plotly.newPlot call; plotly.min.js is loaded once by the page. The
    alt text set with describe() becomes the div's accessible name (role="img") and a
    visually hidden paragraph after it.
    """
    div_id = f"plot-{uuid.uuid4().hex}"
    height = fig.layout.height or 360
    alt = html.escape((fig.layout.meta or {}).get("alt", "Chart"), quote=True)
    return ui.HTML(
        f'<div id="{div_id}" class="plotly-chart" role="img" aria-label="{alt}" '
        f'style="width:100%;height:{height}px"></div>'
        f'<p class="visually-hidden">{alt}</p>'
        f'<script>(function(){{var f={fig.to_json()};'
        f'Plotly.newPlot("{div_id}", f.data, f.layout, {PLOT_CONFIG});}})();</script>'
    )


def output_plot(id: str):
    return ui.output_ui(id)


def render_plot(fn):
    """Decorator: the function returns a go.Figure; it is rendered as HTML."""
    @render.ui
    @functools.wraps(fn)
    def _wrapped():
        return plot_html(fn())
    return _wrapped


def sortable_table(display: pd.DataFrame, sort_values: pd.DataFrame | None = None,
                   pinned_rows: int = 0, height: str = "400px") -> ui.Tag:
    """
    HTML table whose headers sort on click. `display` holds the formatted strings shown;
    `sort_values` (same shape) holds the raw numbers used for ordering, so "1,234" sorts
    numerically. The first `pinned_rows` rows stay on top (e.g. a statewide total).
    """
    sv = display if sort_values is None else sort_values
    head = ui.tags.tr(*[ui.tags.th(c, tabindex="0", title="Click to sort") for c in display.columns])
    rows = []
    for i, (_, row) in enumerate(display.iterrows()):
        cells = []
        for c in display.columns:
            v = sv.iloc[i][c] if c in sv.columns else row[c]
            attrs = {} if isinstance(v, str) else {"data_v": "" if v != v else f"{float(v):.6f}"}
            cells.append(ui.tags.td(str(row[c]), **attrs))
        rows.append(ui.tags.tr(*cells, class_="pinned" if i < pinned_rows else None))
    return ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="sortable-table"),
                  class_="sortable-wrap", style=f"max-height:{height}")


SORTABLE_JS = """
document.addEventListener("click", function (e) {
  const th = e.target.closest(".sortable-table th");
  if (!th) return;
  const table = th.closest("table"), tbody = table.querySelector("tbody");
  const idx = Array.from(th.parentNode.children).indexOf(th);
  const asc = th.dataset.dir !== "asc";
  table.querySelectorAll("th").forEach(h => { h.dataset.dir = ""; h.classList.remove("asc", "desc"); });
  th.dataset.dir = asc ? "asc" : "desc"; th.classList.add(asc ? "asc" : "desc");
  const rows = Array.from(tbody.rows), pinned = rows.filter(r => r.classList.contains("pinned"));
  const key = r => { const c = r.cells[idx]; return "v" in c.dataset ? (c.dataset.v === "" ? null : +c.dataset.v) : c.textContent; };
  const sorted = rows.filter(r => !pinned.includes(r)).sort((a, b) => {
    const x = key(a), y = key(b);
    if (x === null) return 1; if (y === null) return -1;
    const d = typeof x === "number" ? x - y : String(x).localeCompare(String(y));
    return asc ? d : -d;
  });
  pinned.concat(sorted).forEach(r => tbody.appendChild(r));
});
"""


# ---------------------------------------------------------------- formatting
def fmt_int(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:,.0f}"


def simple_bar(x, y, colors, *, height=300, text_fmt="{:,.0f}", hovertemplate=None, customdata=None,
               yaxis=None, alt: str | None = None) -> go.Figure:
    """One categorical bar per x value, colored by entity, value labels on top. `alt` = "Bar chart of ..."."""
    fig = figure(height, yaxis=dict(tickformat=",.0f", **(yaxis or {})))
    fig.add_bar(x=list(x), y=list(y), marker=dict(color=colors),
                text=[text_fmt.format(v) if not pd.isna(v) else "" for v in y], textposition="outside",
                textfont=dict(color=INK_2), customdata=customdata,
                hovertemplate=hovertemplate or "<b>%{x}</b><br>%{y:,.0f}<extra></extra>")
    top = max([v for v in y if not pd.isna(v)] or [0])
    fig.update_layout(showlegend=False, yaxis_range=[0, top * 1.18 if top else 1])
    if alt:
        describe(fig, f"{alt}: {alt_values(zip(x, y), text_fmt)}.")
    return fig
