"""Page 1 - active juvenile caseload, rate per 100k youth, case type and supervision level."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import (apply_geo, geo_filters, isin_or_all, note, partial_note, reset_button, reset_geo,
                      where_label)

PER = 100_000
BREAKDOWNS = {"case": "Case type", "level": "Supervision level", "caseload": "Caseload type",
              "petitions": "Petitions filed by type"}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _rate(count: float, youth: float) -> float:
    return count / youth * PER if youth else float("nan")


@module.ui
def page_ui():
    years = sorted(data.wide()["year"].unique())
    y1, y0 = int(years[-1]), data.default_year()
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_slider("year", "Year", min=int(years[0]), max=y1, value=y0, step=1, sep=""),
            ui.input_select("month", "Month (end of)", choices={str(m): n for m, n in enumerate(MONTH_NAMES, 1)},
                            selected=str(data.meta()["last_month"].get(y0, 12))),
            *geo_filters(),
            ui.input_selectize("case", "Case type", multiple=True, remove_button=True,
                               choices=data.CASE_LABEL, options={"placeholder": "All", "plugins": ["remove_button"]}),
            ui.input_selectize("level", "Supervision level", multiple=True, remove_button=True,
                               choices=data.LEVEL_LABEL, options={"placeholder": "All", "plugins": ["remove_button"]}),
            ui.hr(),
            ui.input_radio_buttons("breakdown", "Trend chart by", choices=BREAKDOWNS, selected="case"),
            note("Active caseload = juvenile cases under active supervision on the last day of the month "
                 "(AOIC Section XIII), by case type (probation, supervision, continued under supervision, "
                 "informal, other) and supervision level. Rate = per 100,000 residents aged 10-17 (ACS; "
                 "years after the latest ACS use its last year) of the counties whose department reported "
                 "that month. Administrative cases (Section XII) are open files without regular "
                 "face-to-face contact."),
            width=310,
        ),
        ui.layout_column_wrap(
            ui.value_box("Active caseload", ui.output_text("kpi_pop"), ui.output_text("kpi_pop_sub"), theme="primary"),
            ui.value_box("Rate per 100k youth", ui.output_text("kpi_rate"), ui.output_text("kpi_rate_sub")),
            ui.value_box(ui.output_text("kpi_change_title"), ui.output_text("kpi_change"), ui.output_text("kpi_change_sub")),
            ui.value_box("Administrative caseload", ui.output_text("kpi_admin"), ui.output_text("kpi_admin_sub")),
            fill=False,
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("map_title")), viz.output_plot("map_chart"),
                    ui.card_footer(note("Active caseload per 100k residents aged 10-17, by county probation "
                                        "department. Hatched counties did not report for the month. Greene and "
                                        "Scott reported jointly through 2016 and share one rate for those years."))),
            ui.card(ui.card_header(ui.output_text("table_title")), ui.output_ui("table"),
                    ui.card_footer(note("Click a column header to sort. The statewide row stays on top."))),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("case_title")), viz.output_plot("case_chart")),
            ui.card(ui.card_header(ui.output_text("level_title")), viz.output_plot("level_chart")),
            ui.card(ui.card_header(ui.output_text("petition_title")), viz.output_plot("petition_chart"),
                    ui.card_footer(note("Petitions filed with the juvenile court (Section I.A). MRAI = minor "
                                        "requiring authoritative intervention."))),
            col_widths={"sm": 12, "xl": [4, 4, 4]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Rate per 100k youth over time"), viz.output_plot("rate_chart"),
                    ui.card_footer(note("December of each year (latest month for the current year); residents of "
                                        "counties that did not report that month are excluded."))),
            ui.card(ui.card_header(ui.output_text("trend_title")), viz.output_plot("trend_chart"),
                    ui.card_footer(ui.output_text("trend_note"))),
            col_widths={"sm": 12, "xl": [4, 8]},
        ),
    )


@module.server
def page_server(input, output, session):
    years = sorted(int(y) for y in data.wide()["year"].unique())

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_slider("year", value=data.default_year())
        ui.update_select("month", selected=str(data.meta()["last_month"].get(data.default_year(), 12)))
        reset_geo()
        ui.update_selectize("case", selected=[])
        ui.update_selectize("level", selected=[])
        ui.update_radio_buttons("breakdown", selected="case")

    @reactive.effect
    @reactive.event(input.year)
    def _clamp_month():
        last = data.meta()["last_month"].get(int(input.year()), 12)
        if int(input.month()) > last:
            ui.update_select("month", selected=str(last))

    @reactive.calc
    def year() -> int:
        return int(input.year())

    @reactive.calc
    def month() -> int:
        return min(int(input.month()), data.meta()["last_month"].get(year(), 12))

    @reactive.calc
    def active_all() -> pd.DataFrame:
        """Active caseload rows (Section XIII), case / level filters, every county and month."""
        df = data.section("population", "active")
        return df.loc[isin_or_all(df["case"], input.case()) & isin_or_all(df["level"], input.level())]

    @reactive.calc
    def active() -> pd.DataFrame:
        return apply_geo(active_all(), input)

    @reactive.calc
    def admin() -> pd.DataFrame:
        return apply_geo(data.section("population", "admin"), input)

    @reactive.calc
    def snapshot() -> pd.DataFrame:
        a = active()
        return a.loc[(a["year"] == year()) & (a["month"] == month())]

    def _youth(y: int, m: int) -> pd.DataFrame:
        """Residents aged 10-17 per county for the geography, only counties whose department reported that month."""
        a = data.youth_for([y]).merge(data.county_circuit(y), on="county", how="inner")
        return apply_geo(a.loc[a["county"].isin(data.reporting_counties(y, m))], input)

    @reactive.calc
    def youth_now() -> float:
        return float(_youth(year(), month())["youth"].sum())

    @reactive.calc
    def not_reporting() -> int:
        """Counties in the geography whose department did not report for the month."""
        a = apply_geo(data.county_circuit(year()), input)
        return int((~a["county"].isin(data.reporting_counties(year(), month()) + list(data.JOINT))).sum())

    def _count(df: pd.DataFrame, y: int, m: int) -> float:
        return float(df.loc[(df["year"] == y) & (df["month"] == m), "value"].sum())

    @reactive.calc
    def by_year() -> pd.DataFrame:
        """Caseload and rate for the selected geography at December (or latest month) of every year."""
        a, rows = active(), []
        for y in years:
            m = data.meta()["last_month"].get(y, 12)
            rows.append(dict(year=y, month=m, caseload=_count(a, y, m)))
        out = pd.DataFrame(rows)
        out["youth"] = [float(_youth(y, m)["youth"].sum()) for y, m in zip(out["year"], out["month"])]
        out["rate"] = out["caseload"] / out["youth"] * PER
        return out

    def _when() -> str:
        return f"{MONTH_NAMES[month() - 1]} {year()}"

    # ---- KPIs
    @render.text
    def kpi_pop():
        return viz.fmt_int(snapshot()["value"].sum())

    @render.text
    def kpi_pop_sub():
        n, total = data.reporting(year(), month())
        return f"under active supervision in {where_label(input)}, end of {_when()} · {n} of {total} departments reported"

    @render.text
    def kpi_rate():
        return viz.fmt_int(_rate(snapshot()["value"].sum(), youth_now()))

    @render.text
    def kpi_rate_sub():
        n = not_reporting()
        return (f"per {viz.fmt_int(youth_now())} residents aged 10-17"
                + (f" · {n} non-reporting {'county' if n == 1 else 'counties'} excluded" if n else ""))

    @render.text
    def kpi_change_title():
        return f"Change vs {MONTH_NAMES[month() - 1]} {year() - 1}"

    @render.text
    def kpi_change():
        if year() - 1 not in years:
            return "–"
        delta = snapshot()["value"].sum() - _count(active(), year() - 1, month())
        return f"{'▲' if delta >= 0 else '▼'} {abs(delta):,.0f}"

    @render.text
    def kpi_change_sub():
        prev = _count(active(), year() - 1, month()) if year() - 1 in years else 0
        if not prev:
            return "no prior year"
        return f"{(snapshot()['value'].sum() - prev) / prev:+.1%} from {prev:,.0f}"

    @render.text
    def kpi_admin():
        d = admin()
        return viz.fmt_int(d.loc[(d["year"] == year()) & (d["month"] == month()), "value"].sum())

    @render.text
    def kpi_admin_sub():
        d = admin()
        d = d.loc[(d["year"] == year()) & (d["month"] == month())]
        return f"{d.loc[d['metric'] == 'inactive', 'value'].sum():,.0f} inactive"

    @render.text
    def map_title():
        return f"Active caseload per 100k youth by county, {_when()}"

    @render.text
    def trend_title():
        if input.breakdown() == "petitions":
            return f"Petitions filed by type, {where_label(input)}"
        return f"Active caseload by {BREAKDOWNS[input.breakdown()].lower()}, {where_label(input)}"

    @render.text
    def trend_note():
        what = ("Monthly petitions filed (Section I.A)" if input.breakdown() == "petitions"
                else "Monthly active caseload, end of month")
        wip = data.wip_from()
        return (f"{what}. Months in which fewer than 90% of the year's departments had reported are not shown"
                + (f"; from {wip} on, some departments have not yet filed and totals are still being reported." if wip else "."))

    @render.text
    def case_title():
        return f"Active caseload by case type, {_when()}"

    @render.text
    def level_title():
        return f"Active caseload by supervision level, {_when()}"

    @render.text
    def petition_title():
        return f"Petitions filed by type, {year()}{partial_note(year())}"

    @render.text
    def table_title():
        return f"Table view - by county, {_when()}"

    # ---- charts
    @viz.render_plot
    def map_chart():
        a = active_all()
        a = a.loc[(a["year"] == year()) & (a["month"] == month())]
        counts = a.groupby("county", observed=True)["value"].sum()
        yo = data.youth_for([year()]).set_index("county")["youth"]
        rows = {}
        for dept in data.reporting_departments(year(), month()):
            counties = data.JOINT.get(dept, [dept])           # a joint department covers each county
            youth = yo.reindex(counties).sum()
            for c in counties:
                rows[c] = dict(caseload=counts.get(dept, 0.0), youth=youth, dept=dept)
        g = pd.DataFrame.from_dict(rows, orient="index")
        if g.empty:
            return viz.empty_figure(height=480)
        g["rate"] = g["caseload"] / g["youth"] * PER
        missing = [f["properties"]["name"] for f in data.il_counties()["features"] if f["properties"]["name"] not in g.index]
        highlight = list(input.county())[0] if input.county() and len(input.county()) == 1 else None
        fig = viz.choropleth(data.il_counties(), g["rate"], height=480,
                             customdata=g[["caseload", "youth", "dept"]].values,
                             hovertemplate="<b>%{customdata[2]}</b><br>%{z:,.0f} per 100k youth<br>"
                                           "%{customdata[0]:,.0f} on active supervision / "
                                           "%{customdata[1]:,.0f} residents aged 10-17<extra></extra>",
                             highlight=highlight, missing=missing, missing_label="Did not report",
                             outline=data.il_outline())
        top = g["rate"].sort_values(ascending=False).head(5)
        return viz.describe(fig, f"Map of Illinois counties shaded by active juvenile caseload per 100,000 residents "
                                 f"aged 10-17, {_when()}: {len(g)} counties from {g['rate'].min():,.0f} to "
                                 f"{g['rate'].max():,.0f}; highest {viz.alt_values(top.items())}. "
                                 f"{len(missing)} counties did not report and are hatched.")

    @viz.render_plot
    def trend_chart():
        b = input.breakdown()
        if b == "caseload":
            ad = admin()
            act = active().groupby("date")["value"].sum().rename("Active supervision")
            aa = ad.loc[ad["metric"] == "active"].groupby("date")["value"].sum().rename("Administrative – active")
            ai = ad.loc[ad["metric"] == "inactive"].groupby("date")["value"].sum().rename("Administrative – inactive")
            piv = pd.concat([act, aa, ai], axis=1).fillna(0)
            colors, labels = viz.CASELOAD_COLOR, {c: c for c in piv.columns}
        elif b == "petitions":
            pt = apply_geo(data.section("petitions"), input)
            piv = pt.pivot_table(index="date", columns="metric", values="value", aggfunc="sum", observed=True).fillna(0)
            piv = piv[[o for o in data.PETITION_ORDER if o in piv.columns]]
            colors, labels = viz.PETITION_COLOR, data.PETITION_LABEL
        else:
            col = "case" if b == "case" else "level"
            order = data.CASE_ORDER if b == "case" else data.LEVEL_ORDER
            piv = active().pivot_table(index="date", columns=col, values="value", aggfunc="sum", observed=True).fillna(0)
            piv = piv[[o for o in order if o in piv.columns]]
            colors = viz.CASE_COLOR if b == "case" else viz.LEVEL_COLOR
            labels = data.CASE_LABEL if b == "case" else data.LEVEL_LABEL
        if piv.empty or not piv.values.sum():
            return viz.empty_figure(height=480)
        fig = viz.figure(480, hovermode="x unified", yaxis=dict(tickformat=",.0f", rangemode="tozero"))
        viz.stacked_area(fig, piv, colors, lambda c: labels[c])
        viz.mark_view(fig, pd.Timestamp(year=year(), month=month(), day=1), _when())
        if data.wip_start() is not None:
            viz.mark_wip(fig, data.wip_start())
        last = piv.index[-1]
        what = "petitions filed" if b == "petitions" else "juvenile active caseload"
        return viz.describe(fig, f"Stacked area chart of monthly {what} in {where_label(input)} by "
                                 f"{BREAKDOWNS[b].lower()}, {piv.index[0]:%b %Y} to {last:%b %Y}. "
                                 f"In {last:%b %Y}: {viz.alt_values((labels[c], piv.loc[last, c]) for c in piv.columns)}. "
                                 f"Vertical lines mark {_when()} and, dashed, the start of still-reported data.")

    @viz.render_plot
    def case_chart():
        g = snapshot().groupby("case", observed=True)["value"].sum().reindex(data.CASE_ORDER).dropna()
        if g.empty or not g.sum():
            return viz.empty_figure(height=300)
        return viz.simple_bar([data.CASE_LABEL[o] for o in g.index], g.values, [viz.CASE_COLOR[o] for o in g.index],
                              alt=f"Bar chart of active juvenile caseload by case type, {where_label(input)}, {_when()}")

    @viz.render_plot
    def level_chart():
        g = snapshot().groupby("level", observed=True)["value"].sum().reindex(data.LEVEL_ORDER).dropna()
        if g.empty or not g.sum():
            return viz.empty_figure(height=300)
        return viz.simple_bar([data.LEVEL_LABEL[o] for o in g.index], g.values, [viz.LEVEL_COLOR[o] for o in g.index],
                              alt=f"Bar chart of active juvenile caseload by supervision level, {where_label(input)}, {_when()}")

    @viz.render_plot
    def petition_chart():
        pt = apply_geo(data.section("petitions"), input)
        g = pt.loc[pt["year"] == year()].groupby("metric", observed=True)["value"].sum().reindex(data.PETITION_ORDER).dropna()
        if g.empty or not g.sum():
            return viz.empty_figure(height=300)
        return viz.simple_bar([data.PETITION_LABEL[c] for c in g.index], g.values, [viz.PETITION_COLOR[c] for c in g.index],
                              alt=f"Bar chart of juvenile court petitions filed by type, {where_label(input)}, {year()}")

    @viz.render_plot
    def rate_chart():
        by = by_year()
        if by["rate"].isna().all():
            return viz.empty_figure()
        fig = viz.figure(360, yaxis=dict(rangemode="tozero", tickformat=",.0f"), xaxis=dict(dtick=2))
        fig.add_scatter(x=by["year"], y=by["rate"], mode="lines+markers", line=dict(color=viz.SERIES[0], width=2),
                        marker=dict(size=8, color=viz.SERIES[0], line=dict(color=viz.SURFACE, width=2)),
                        customdata=by[["caseload", "youth"]].values,
                        hovertemplate="<b>%{x}</b><br>%{y:,.0f} per 100k youth<br>"
                                      "%{customdata[0]:,.0f} on active supervision<extra></extra>")
        fig.add_vline(x=year(), line=dict(color=viz.AXIS, width=1))
        fig.update_layout(showlegend=False)
        r = by.dropna(subset=["rate"])
        return viz.describe(fig, f"Line chart of the active juvenile caseload per 100,000 residents aged 10-17 in "
                                 f"{where_label(input)}, yearly {r['year'].iloc[0]} to {r['year'].iloc[-1]}: "
                                 f"{viz.alt_values(zip(r['year'], r['rate']))}.")

    @render.ui
    def table():
        a = active_all()
        a = a.loc[(a["year"] == year()) & (a["month"] == month())]
        w = data.wide()
        depts = sorted(w.loc[w["year"] == year(), "county"].astype(str).unique())   # every sheet that year
        g = a.groupby("county", observed=True).agg(caseload=("value", "sum")).reindex(depts)
        g["probation"] = a.loc[a["case"] == "probation"].groupby("county", observed=True)["value"].sum()
        g["max"] = a.loc[a["level"] == "max"].groupby("county", observed=True)["value"].sum()
        yo = data.youth_for([year()]).set_index("county")["youth"]
        g["youth"] = yo.reindex(g.index)
        for dept, counties in data.JOINT.items():             # a joint department's denominator is its counties
            if dept in g.index:
                g.loc[dept, "youth"] = yo.reindex(counties).sum()
        d = data.section("population", "admin")
        g["admin"] = d.loc[(d["year"] == year()) & (d["month"] == month())].groupby("county", observed=True)["value"].sum()
        reporting = data.reporting_departments(year(), month())
        g.loc[~g.index.isin(reporting), ["caseload", "probation", "max", "admin"]] = float("nan")   # shown as '–'
        g = g.reset_index(names="county")
        sel = apply_geo(g.merge(data.county_circuit(year()), on="county"), input)
        state = pd.DataFrame([dict(county="All Illinois", caseload=g["caseload"].sum(), probation=g["probation"].sum(),
                                   max=g["max"].sum(), youth=g.loc[g["county"].isin(reporting), "youth"].sum(),
                                   admin=g["admin"].sum())])
        out = pd.concat([state, sel.sort_values("caseload", ascending=False)], ignore_index=True)
        out["rate"] = out["caseload"] / out["youth"] * PER
        out["pct_probation"] = out["probation"] / out["caseload"]
        out["pct_max"] = out["max"] / out["caseload"]
        cols = {"County": ("county", None), "Residents 10-17": ("youth", "{:,.0f}"),
                "Active caseload": ("caseload", "{:,.0f}"), "Rate per 100k": ("rate", "{:,.0f}"),
                "% probation": ("pct_probation", "{:.1%}"), "% maximum supervision": ("pct_max", "{:.1%}"),
                "Administrative caseload": ("admin", "{:,.0f}")}
        raw = pd.DataFrame({"County": out["county"]})
        shown = raw.copy()
        for name, (src, fmt) in cols.items():
            if fmt:
                raw[name] = out[src].values
                shown[name] = out[src].map(lambda v: "–" if pd.isna(v) else fmt.format(v)).values
        return viz.sortable_table(shown, raw, pinned_rows=1, height="480px")
