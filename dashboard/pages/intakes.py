"""Page 3 - who enters juvenile probation: intake demographics (Section IV) and rates per 100k youth by race and sex."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import (apply_geo, geo_filters, isin_or_all, note, partial_note, period, reset_button, reset_geo,
                      where_label)

PER = 100_000
BREAKDOWNS = {"race/ethnicity": "Race / ethnicity", "gender": "Sex", "age": "Age", "subgroup": "Formal vs informal"}
GROUP_ORDER = {"race/ethnicity": data.RACE_ORDER, "gender": data.SEX_ORDER, "age": data.AGE_ORDER,
               "subgroup": data.SUBGROUP_ORDER}
GROUP_LABEL = {"race/ethnicity": data.RACE_LABEL, "gender": data.SEX_LABEL,
               "age": {a: data.AGE_LABEL.get(a, a) for a in data.AGE_ORDER},
               "subgroup": data.SUBGROUP_LABEL}
GROUP_COLOR = {"race/ethnicity": viz.RACE_COLOR, "gender": viz.SEX_COLOR, "age": viz.AGE_COLOR,
               "subgroup": viz.SUBGROUP_COLOR}


def _rate(n, youth):
    return n / youth * PER if youth else float("nan")


@module.ui
def page_ui():
    years = sorted(int(y) for y in data.wide()["year"].unique())
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_slider("year", "Year", min=years[0], max=years[-1], value=data.default_year(), step=1, sep=""),
            *geo_filters(),
            ui.input_selectize("subgroup", "Case handling", multiple=True, remove_button=True,
                               choices=data.SUBGROUP_LABEL, options={"placeholder": "All", "plugins": ["remove_button"]}),
            ui.hr(),
            ui.input_radio_buttons("breakdown", "Intake trend by", choices=BREAKDOWNS, selected="race/ethnicity"),
            ui.input_radio_buttons("grain", "Trend shown by", choices={"Q": "Quarter", "Y": "Year"}, selected="Y",
                                   inline=True),
            note("Demographics (AOIC Section IV) cover every minor the department took in, reported "
                 "separately for formal cases (a petition was filed) and informal cases (handled without a "
                 "petition). Race/ethnicity is self-reported; 'Other' is any group not listed. Rates are per "
                 "100,000 residents aged 10-17 of the same group (ACS; race groups include Hispanic residents). "
                 "Disparity = Black intake rate ÷ White intake rate."),
            width=310,
        ),
        ui.div(
            ui.tags.strong("Intakes are not admissions. "),
            "An intake (Section IV) is a minor the department processed - interviews, verification and "
            "classification scoring - whether the case went on to a petition, was handled informally or went "
            "nowhere. An admission (Section IX.B, on the Admissions page) is a case added to the active caseload "
            "after a disposition to probation, supervision, continued under supervision or informal supervision.",
            class_="callout",
        ),
        ui.layout_column_wrap(
            ui.value_box("Intakes", ui.output_text("kpi_intakes"), ui.output_text("kpi_intakes_sub"), theme="primary"),
            ui.value_box("Intake rate per 100k youth", ui.output_text("kpi_rate"), ui.output_text("kpi_rate_sub")),
            ui.value_box("Black : White disparity", ui.output_text("kpi_ratio"), ui.output_text("kpi_ratio_sub")),
            ui.value_box("Formal share", ui.output_text("kpi_formal"), "of intakes with a petition filed"),
            fill=False,
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("map_title")), viz.output_plot("map_chart"),
                    ui.card_footer(note("Formal + informal intakes per 100k residents aged 10-17, by county "
                                        "probation department."))),
            ui.card(ui.card_header(ui.output_text("trend_title")), viz.output_plot("trend_chart")),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("race_title")), viz.output_plot("race_chart")),
            ui.card(ui.card_header(ui.output_text("sex_title")), viz.output_plot("sex_chart")),
            ui.card(ui.card_header(ui.output_text("age_title")), viz.output_plot("age_chart"),
                    ui.card_footer(note("Age at intake. No population rate: AOIC single years of age do not "
                                        "match ACS bands."))),
            col_widths={"sm": 12, "xl": [4, 3, 5]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Black : White intake-rate ratio over time"), viz.output_plot("ratio_chart"),
                    ui.card_footer(note("1.0 = parity. Uses the geography and case-handling filters."))),
            ui.card(ui.card_header(ui.output_text("school_title")), viz.output_plot("school_chart"),
                    ui.card_footer(note("Section IV.D, reported for delinquency cases only: minors enrolled in "
                                        "school at intake, as a share of delinquency admissions (Section III.A) "
                                        "handled formally / informally - the closest denominator on the form."))),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
    )


@module.server
def page_server(input, output, session):
    years = sorted(int(y) for y in data.wide()["year"].unique())

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_slider("year", value=data.default_year())
        reset_geo()
        ui.update_selectize("subgroup", selected=[])
        ui.update_radio_buttons("breakdown", selected="race/ethnicity")
        ui.update_radio_buttons("grain", selected="Y")

    @reactive.calc
    def year() -> int:
        return int(input.year())

    @reactive.calc
    def demo_all() -> pd.DataFrame:
        """Section IV rows, case-handling filter applied, every county and year."""
        df = data.section("demographics of intakes")
        return df.loc[isin_or_all(df["subgroup"], input.subgroup())]

    @reactive.calc
    def demo() -> pd.DataFrame:
        return apply_geo(demo_all(), input)

    def _group(df: pd.DataFrame, breakdown: str) -> pd.DataFrame:
        """Counts by group for one breakdown (gender counts double as the intake total)."""
        if breakdown == "subgroup":
            return df.loc[df["breakdown"] == "gender"].groupby("subgroup", observed=True)["value"].sum().rename_axis("group")
        return df.loc[df["breakdown"] == breakdown].groupby("metric", observed=True)["value"].sum().rename_axis("group")

    @reactive.calc
    def demo_year() -> pd.DataFrame:
        d = demo()
        return d.loc[d["year"] == year()]

    @reactive.calc
    def intakes_year() -> float:
        return float(_group(demo_year(), "gender").sum())

    def _youth(group_type: str, y: int) -> pd.Series:
        a = apply_geo(data.youth_for([y], group_type).merge(data.county_circuit(y), on="county"), input)
        return a.groupby("group")["youth"].sum()

    @reactive.calc
    def race_rates() -> pd.DataFrame:
        n = _group(demo_year(), "race/ethnicity").reindex(data.RACE_ORDER).fillna(0)
        yo = _youth("race", year()).reindex(data.RACE_ORDER)
        out = pd.DataFrame({"intakes": n, "youth": yo})
        out["rate"] = out["intakes"] / out["youth"] * PER
        return out

    @reactive.calc
    def ratio_by_year() -> pd.Series:
        d, out = demo(), {}
        for y in years:
            n = _group(d.loc[d["year"] == y], "race/ethnicity")
            yo = _youth("race", y)
            b, w = _rate(n.get("black", 0), yo.get("black", 0)), _rate(n.get("white", 0), yo.get("white", 0))
            out[y] = b / w if w else float("nan")
        return pd.Series(out)

    # ---- KPIs
    @render.text
    def kpi_intakes():
        return viz.fmt_int(intakes_year())

    @render.text
    def kpi_intakes_sub():
        last = data.meta()["last_month"].get(year(), 12)
        n, total = data.reporting(year(), last)
        return (f"formal + informal intakes, {where_label(input)}, {year()}{partial_note(year())} · "
                f"{n} of {total} departments reported")

    @render.text
    def kpi_rate():
        return viz.fmt_int(_rate(intakes_year(), _youth("all", year()).sum()))

    @render.text
    def kpi_rate_sub():
        return f"per {viz.fmt_int(_youth('all', year()).sum())} residents aged 10-17"

    @render.text
    def kpi_ratio():
        r = race_rates()["rate"]
        return f"{r['black'] / r['white']:.1f}×" if r.get("white") else "–"

    @render.text
    def kpi_ratio_sub():
        r = race_rates()["rate"]
        return f"Black {r['black']:,.0f} vs White {r['white']:,.0f} intakes per 100k youth"

    @render.text
    def kpi_formal():
        g = _group(demo_year(), "subgroup")
        return f"{g.get('formal', 0) / g.sum():.1%}" if g.sum() else "–"

    @render.text
    def map_title():
        return f"Intake rate per 100k youth by county, {year()}"

    @render.text
    def trend_title():
        return f"Intakes by {BREAKDOWNS[input.breakdown()].lower()}, {where_label(input)}"

    @render.text
    def race_title():
        return f"Intake rate per 100k youth by race / ethnicity, {year()}"

    @render.text
    def sex_title():
        return f"Intake rate by sex, {year()}"

    @render.text
    def age_title():
        return f"Intakes by age and case handling, {year()}"

    @render.text
    def school_title():
        return f"Enrolled in school at intake, delinquency cases, {year()}"

    # ---- charts
    @viz.render_plot
    def map_chart():
        d = demo_all()
        d = d.loc[(d["year"] == year()) & (d["breakdown"] == "gender")]
        counts = d.groupby("county", observed=True)["value"].sum()
        yo = data.youth_for([year()]).set_index("county")["youth"]
        for dept, counties in data.JOINT.items():
            if dept in counts.index:
                yo[dept] = yo.reindex(counties).sum()
        g = pd.DataFrame({"intakes": counts, "youth": yo.reindex(counts.index)}).dropna()
        if g.empty:
            return viz.empty_figure(height=480)
        g["rate"] = g["intakes"] / g["youth"] * PER
        highlight = list(input.county())[0] if input.county() and len(input.county()) == 1 else None
        fig = viz.choropleth(data.il_counties(), g["rate"], height=480, customdata=g[["intakes", "youth"]].values,
                             hovertemplate="<b>%{location}</b><br>%{z:,.0f} per 100k youth<br>"
                                           "%{customdata[0]:,.0f} intakes / %{customdata[1]:,.0f} residents aged 10-17<extra></extra>",
                             highlight=highlight, outline=data.il_outline())
        top = g["rate"].sort_values(ascending=False).head(5)
        return viz.describe(fig, f"Map of Illinois counties shaded by juvenile intakes per 100,000 residents aged "
                                 f"10-17, {year()}: {len(g)} counties from {g['rate'].min():,.0f} to "
                                 f"{g['rate'].max():,.0f}; highest {viz.alt_values(top.items())}.")

    @viz.render_plot
    def trend_chart():
        b, g = input.breakdown(), input.grain()
        d = demo()
        if b == "subgroup":
            d = d.loc[d["breakdown"] == "gender"]
            col = "subgroup"
        else:
            d = d.loc[d["breakdown"] == b]
            col = "metric"
        piv = d.assign(p=lambda x: period(x["date"], g)).pivot_table(index="p", columns=col, values="value",
                                                                     aggfunc="sum", observed=True).fillna(0)
        piv = piv[[o for o in GROUP_ORDER[b] if o in piv.columns]]
        if piv.empty or not piv.values.sum():
            return viz.empty_figure(height=480)
        labels, colors = GROUP_LABEL[b], GROUP_COLOR[b]
        fig = viz.figure(480, hovermode="x unified", yaxis=dict(tickformat=",.0f", rangemode="tozero"),
                         xaxis=dict(dtick=2, tickformat="d") if g == "Y" else {})
        if g == "Y":
            piv.index = piv.index.year
        viz.stacked_area(fig, piv, colors, lambda c: labels[c])
        viz.mark_view(fig, year() if g == "Y" else pd.Timestamp(year=year(), month=1, day=1), str(year()))
        wip = data.wip_from()
        if wip and g == "Q":
            viz.mark_wip(fig, pd.Timestamp(year=wip, month=1, day=1))
        elif wip and wip - 0.5 > piv.index[0]:
            viz.mark_wip(fig, wip - 0.5)
        last = piv.index[-1]
        when = f"{last}" if g == "Y" else f"Q{last.quarter} {last.year}"
        return viz.describe(fig, f"Stacked area chart of juvenile intakes in {where_label(input)} by "
                                 f"{BREAKDOWNS[b].lower()}, by {'year' if g == 'Y' else 'quarter'}. In {when}: "
                                 f"{viz.alt_values((labels[c], piv.loc[last, c]) for c in piv.columns)}.")

    @viz.render_plot
    def race_chart():
        r = race_rates().dropna(subset=["rate"])
        if r.empty or not r["intakes"].sum():
            return viz.empty_figure(height=300)
        return viz.simple_bar([data.RACE_LABEL[i] for i in r.index], r["rate"].values,
                              [viz.RACE_COLOR[i] for i in r.index], customdata=r[["intakes", "youth"]].values,
                              hovertemplate="<b>%{x}</b><br>%{y:,.0f} per 100k youth<br>"
                                            "%{customdata[0]:,.0f} intakes / %{customdata[1]:,.0f} youth<extra></extra>",
                              alt=f"Bar chart of juvenile intakes per 100,000 residents aged 10-17 by race / ethnicity, "
                                  f"{where_label(input)}, {year()}")

    @viz.render_plot
    def sex_chart():
        n = _group(demo_year(), "gender").reindex(data.SEX_ORDER).fillna(0)
        yo = _youth("sex", year()).reindex(data.SEX_ORDER)
        r = pd.DataFrame({"intakes": n, "youth": yo})
        r["rate"] = r["intakes"] / r["youth"] * PER
        if not r["intakes"].sum():
            return viz.empty_figure(height=300)
        return viz.simple_bar([data.SEX_LABEL[i] for i in r.index], r["rate"].values,
                              [viz.SEX_COLOR[i] for i in r.index], customdata=r[["intakes", "youth"]].values,
                              hovertemplate="<b>%{x}</b><br>%{y:,.0f} per 100k youth<br>"
                                            "%{customdata[0]:,.0f} intakes / %{customdata[1]:,.0f} youth<extra></extra>",
                              alt=f"Bar chart of juvenile intakes per 100,000 residents aged 10-17 by sex, "
                                  f"{where_label(input)}, {year()}")

    @viz.render_plot
    def age_chart():
        d = demo_year()
        d = d.loc[d["breakdown"] == "age"]
        piv = d.pivot_table(index="metric", columns="subgroup", values="value", aggfunc="sum", observed=True) \
               .reindex(data.AGE_ORDER).fillna(0)
        if piv.empty or not piv.values.sum():
            return viz.empty_figure(height=300)
        fig = viz.figure(300, barmode="stack", yaxis=dict(tickformat=",.0f"))
        for sg in data.SUBGROUP_ORDER:
            if sg in piv.columns:
                fig.add_bar(name=data.SUBGROUP_LABEL[sg], x=[data.AGE_LABEL.get(a, a) for a in piv.index], y=piv[sg],
                            marker=viz.bar_marker(viz.SUBGROUP_COLOR[sg]),
                            hovertemplate=f"<b>{data.SUBGROUP_LABEL[sg]}</b>, %{{x}}<br>%{{y:,.0f}} intakes<extra></extra>")
        tot = piv.sum(axis=1)
        return viz.describe(fig, f"Stacked bar chart of juvenile intakes by age, formal vs informal, "
                                 f"{where_label(input)}, {year()}. Totals: "
                                 f"{viz.alt_values((data.AGE_LABEL.get(a, a), v) for a, v in tot.items())}.")

    @viz.render_plot
    def ratio_chart():
        s = ratio_by_year()
        if s.isna().all():
            return viz.empty_figure()
        fig = viz.figure(360, yaxis=dict(rangemode="tozero", ticksuffix="×"), xaxis=dict(dtick=2))
        fig.add_scatter(x=s.index, y=s.values, mode="lines+markers", line=dict(color=viz.SERIES[0], width=2),
                        marker=dict(size=8, color=viz.SERIES[0], line=dict(color=viz.SURFACE, width=2)),
                        hovertemplate="<b>%{x}</b><br>%{y:.2f}× the White intake rate<extra></extra>")
        fig.add_hline(y=1, line=dict(color=viz.AXIS, width=1), annotation_text="parity",
                      annotation_position="bottom right", annotation_font=dict(color=viz.MUTED))
        fig.add_vline(x=year(), line=dict(color=viz.AXIS, width=1))
        fig.update_layout(showlegend=False)
        r = s.dropna()
        return viz.describe(fig, f"Line chart of the Black to White juvenile intake-rate ratio in {where_label(input)}, "
                                 f"yearly {r.index[0]} to {r.index[-1]}: {viz.alt_values(r.items(), '{:.1f}x')}. "
                                 "A horizontal line marks parity at 1.0.")

    @viz.render_plot
    def school_chart():
        d = demo_year()
        enrolled = d.loc[d["breakdown"] == "education"].groupby("subgroup", observed=True)["value"].sum()
        adm = apply_geo(data.section("admissions"), input)
        adm = adm.loc[(adm["year"] == year()) & (adm["metric"] == "delinquency") & isin_or_all(adm["subgroup"], input.subgroup())]
        delinq = adm.groupby("subgroup", observed=True)["value"].sum()
        rows = [(sg, enrolled.get(sg, 0), delinq.get(sg, 0)) for sg in data.SUBGROUP_ORDER if delinq.get(sg, 0)]
        if not rows:
            return viz.empty_figure()
        fig = viz.figure(360, yaxis=dict(tickformat=".0%", range=[0, 1.12]))
        fig.add_bar(x=[data.SUBGROUP_LABEL[sg] for sg, *_ in rows], y=[min(e / n, 1.0) for _, e, n in rows],
                    marker=dict(color=[viz.SUBGROUP_COLOR[sg] for sg, *_ in rows]),
                    text=[f"{min(e / n, 1.0):.0%}" for _, e, n in rows], textposition="outside", textfont=dict(color=viz.INK_2),
                    customdata=[(e, n) for _, e, n in rows],
                    hovertemplate="<b>%{x}</b><br>%{y:.1%} enrolled<br>%{customdata[0]:,.0f} enrolled / "
                                  "%{customdata[1]:,.0f} delinquency admissions<extra></extra>")
        fig.update_layout(showlegend=False)
        return viz.describe(fig, f"Bar chart of the share of delinquency intakes enrolled in school, formal vs "
                                 f"informal, {where_label(input)}, {year()}: "
                                 f"{viz.alt_values(((data.SUBGROUP_LABEL[sg], min(e / n, 1.0)) for sg, e, n in rows), '{:.0%}')}.")
