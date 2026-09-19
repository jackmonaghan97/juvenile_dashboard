"""Page 2 - admissions to active supervision, discharges by reason, violations, court actions and DJJ commitments."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import (GRAIN, apply_geo, geo_filters, isin_or_all, note, period, period_labels, reset_button,
                      reset_geo, where_label)


@module.ui
def page_ui():
    years = sorted(int(y) for y in data.wide()["year"].unique())
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_slider("years", "Years", min=years[0], max=years[-1], value=(years[0], years[-1]), step=1, sep=""),
            ui.input_radio_buttons("grain", "Show by", choices=GRAIN, selected="Q", inline=True),
            *geo_filters(),
            ui.input_selectize("case", "Case type", multiple=True, remove_button=True,
                               choices=data.CASE_LABEL, options={"placeholder": "All", "plugins": ["remove_button"]}),
            note("Admissions = new cases added to the active caseload (Section IX.B), by case type: probation, "
                 "supervision, continued under supervision (CUS), informal, other. Discharges = cases dropped "
                 "from active supervision (IX.F). Successful = scheduled or early termination. Violations = "
                 "written violation reports filed (XV); revocations = court findings of violation on petitions "
                 "to revoke (XVI). DJJ = Illinois Department of Juvenile Justice (X)."),
            width=310,
        ),
        ui.layout_column_wrap(
            ui.value_box("Admissions", ui.output_text("kpi_adm"), ui.output_text("kpi_range"), theme="primary"),
            ui.value_box("Discharges", ui.output_text("kpi_dis"), ui.output_text("kpi_dis_sub")),
            ui.value_box("Violations reported", ui.output_text("kpi_viol"), ui.output_text("kpi_viol_sub")),
            ui.value_box("Revocations", ui.output_text("kpi_rev"), ui.output_text("kpi_rev_sub")),
            ui.value_box("Commitments to DJJ", ui.output_text("kpi_djj"), ui.output_text("kpi_djj_sub")),
            fill=False,
        ),
        ui.card(ui.card_header("Admissions, discharges and net change"), viz.output_plot("flow_chart"),
                ui.card_footer(note("Discharges are drawn below zero; the line is net change (admissions − discharges). "
                                    "Right of the dashed line, some departments have not yet filed and totals are "
                                    "still being reported."))),
        ui.layout_columns(
            ui.card(ui.card_header("Admissions by case type"), viz.output_plot("case_chart")),
            ui.card(ui.card_header("Discharges by reason"), viz.output_plot("reason_chart"),
                    ui.card_footer(note("Colored by outcome: successful, unsuccessful, other."))),
            col_widths={"sm": 12, "xl": [7, 5]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Violations reported, by type"), viz.output_plot("violation_chart")),
            ui.card(ui.card_header("Revocation rate on court actions, by violation type"), viz.output_plot("revocation_chart"),
                    ui.card_footer(note("Share of court hearings on petitions to revoke that found a violation."))),
            ui.card(ui.card_header("Commitments to DJJ, by type"), viz.output_plot("djj_chart"),
                    ui.card_footer(note("Section X. Evaluation = court-ordered evaluation commitment; habitual / "
                                        "violent = Habitual and Violent Juvenile Offender Act commitments."))),
            col_widths={"sm": 12, "xl": [4, 4, 4]},
        ),
        ui.card(ui.card_header("Table view - by year"), ui.output_data_frame("table"),
                ui.card_footer(note("Case-type shares are % of admissions; outcome shares are % of discharges; "
                                    "technical % is share of violations reported; revocation rate is revocations ÷ "
                                    "all court actions on violations."))),
    )


@module.server
def page_server(input, output, session):
    years = sorted(int(y) for y in data.wide()["year"].unique())

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_slider("years", value=(years[0], years[-1]))
        ui.update_radio_buttons("grain", selected="Q")
        reset_geo()
        ui.update_selectize("case", selected=[])

    def _base(sec: str, breakdown=None, case_filter=True) -> pd.DataFrame:
        df = apply_geo(data.section(sec, breakdown), input)
        y0, y1 = input.years()
        df = df.loc[(df["year"] >= y0) & (df["year"] <= y1)]
        if case_filter:
            df = df.loc[isin_or_all(df["case"], input.case())]
        return df

    @reactive.calc
    def adm() -> pd.DataFrame:
        return _base("new cases")

    @reactive.calc
    def dis() -> pd.DataFrame:
        return _base("discharge")

    @reactive.calc
    def viol() -> pd.DataFrame:      # no case-type breakdown in the template
        return _base("reported violations", case_filter=False)

    @reactive.calc
    def court() -> pd.DataFrame:
        return _base("court actions", case_filter=False)

    @reactive.calc
    def djj() -> pd.DataFrame:
        return _base("djj commitments", case_filter=False)

    @reactive.calc
    def flows() -> pd.DataFrame:
        g = input.grain()
        a = adm().assign(p=lambda d: period(d["date"], g)).groupby("p")["value"].sum()
        e = dis().assign(p=lambda d: period(d["date"], g)).groupby("p")["value"].sum()
        out = pd.DataFrame({"Admissions": a, "Discharges": e}).fillna(0).sort_index()
        out["Net change"] = out["Admissions"] - out["Discharges"]
        return out

    @reactive.calc
    def year_label() -> str:
        y0, y1 = input.years()
        return f"{y0}–{y1}" if y0 != y1 else str(y0)

    # ---- KPIs
    @render.text
    def kpi_adm():
        return viz.fmt_int(adm()["value"].sum())

    @render.text
    def kpi_range():
        return f"{year_label()}, {where_label(input)}"

    @render.text
    def kpi_dis():
        return viz.fmt_int(dis()["value"].sum())

    @render.text
    def kpi_dis_sub():
        d = dis()
        tot = d["value"].sum()
        ok = d.loc[d["breakdown"].map(data.DISCHARGE_OUTCOME) == "Successful", "value"].sum()
        return f"{ok / tot:.1%} successful (scheduled or early termination)" if tot else "–"

    @render.text
    def kpi_viol():
        return viz.fmt_int(viol()["value"].sum())

    @render.text
    def kpi_viol_sub():
        v = viol()
        tot = v["value"].sum()
        tech = v.loc[v["metric"] == "technical", "value"].sum()
        return f"{tech / tot:.1%} technical · {1 - tech / tot:.1%} new offense" if tot else "–"

    @render.text
    def kpi_rev():
        c = court()
        return viz.fmt_int(c.loc[c["breakdown"] == "revocation", "value"].sum())

    @render.text
    def kpi_rev_sub():
        c = court()
        tot = c["value"].sum()
        rev = c.loc[c["breakdown"] == "revocation", "value"].sum()
        return f"{rev / tot:.1%} of court actions on violations" if tot else "–"

    @render.text
    def kpi_djj():
        return viz.fmt_int(djj()["value"].sum())

    @render.text
    def kpi_djj_sub():
        d = djj()
        tot = d["value"].sum()
        full = d.loc[d["metric"] == "full", "value"].sum()
        return f"{full / tot:.1%} full commitments" if tot else "–"

    # ---- charts
    @viz.render_plot
    def flow_chart():
        f = flows()
        if f.empty:
            return viz.empty_figure()
        labels = period_labels(f.index, input.grain())
        fig = viz.figure(380, barmode="relative", bargap=0.25, hovermode="x unified", yaxis=dict(tickformat=",.0f"))
        fig.add_bar(name="Admissions", x=labels, y=f["Admissions"], marker=dict(color=viz.FLOW_COLOR["Admissions"]),
                    hovertemplate="%{y:,.0f}")
        fig.add_bar(name="Discharges", x=labels, y=-f["Discharges"], customdata=f["Discharges"],
                    marker=dict(color=viz.FLOW_COLOR["Discharges"]), hovertemplate="%{customdata:,.0f}")
        fig.add_scatter(name="Net change", x=labels, y=f["Net change"], mode="lines+markers",
                        line=dict(color=viz.FLOW_COLOR["Net change"], width=2),
                        marker=dict(size=6, color=viz.FLOW_COLOR["Net change"], line=dict(color=viz.SURFACE, width=1.5)),
                        hovertemplate="%{y:+,.0f}")
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(f) > 12 else 0))
        wip = data.wip_start()
        if wip is not None and (f.index >= wip).any():
            # category axis: bar i sits at x = i, so the boundary falls half a slot before the first WIP period
            viz.mark_wip(fig, int((f.index >= wip).argmax()) - 0.5)
        return viz.describe(fig, f"Bar chart of juvenile probation admissions (above zero) and discharges (below zero) "
                                 f"per {GRAIN[input.grain()].lower()} in {where_label(input)}, {labels[0]} to "
                                 f"{labels[-1]}, with a line for net change. Totals: {f['Admissions'].sum():,.0f} "
                                 f"admissions, {f['Discharges'].sum():,.0f} discharges, net {f['Net change'].sum():+,.0f}.")

    @viz.render_plot
    def case_chart():
        g = input.grain()
        a = adm().assign(p=lambda d: period(d["date"], g))
        piv = a.pivot_table(index="p", columns="case", values="value", aggfunc="sum", observed=True).fillna(0)
        if piv.empty:
            return viz.empty_figure(height=400)
        labels = period_labels(piv.index, g)
        fig = viz.figure(400, barmode="stack", yaxis=dict(tickformat=",.0f"))
        for c in data.CASE_ORDER:
            if c in piv.columns:
                fig.add_bar(name=data.CASE_LABEL[c], x=labels, y=piv[c], marker=viz.bar_marker(viz.CASE_COLOR[c]),
                            hovertemplate=f"<b>{data.CASE_LABEL[c]}</b><br>%{{x}}: %{{y:,.0f}}<extra></extra>")
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(piv) > 12 else 0))
        tot = piv.sum()
        return viz.describe(fig, f"Stacked bar chart of juvenile probation admissions by case type per "
                                 f"{GRAIN[g].lower()}, {labels[0]} to {labels[-1]}. Totals over the period: "
                                 f"{viz.alt_values((data.CASE_LABEL[c], tot[c]) for c in data.CASE_ORDER if c in tot)}.")

    @viz.render_plot
    def reason_chart():
        g = dis().groupby("breakdown", observed=True)["value"].sum().reindex(data.DISCHARGE_ORDER).dropna()
        if g.empty or not g.sum():
            return viz.empty_figure(height=400)
        g = g.sort_values()
        colors = [viz.OUTCOME_COLOR[data.DISCHARGE_OUTCOME[r]] for r in g.index]
        fig = viz.figure(400, margin=dict(l=8, r=70, t=8, b=8),
                         xaxis=dict(tickformat=",.0f", showgrid=True, gridcolor=viz.GRID),
                         yaxis=dict(showgrid=False, tickfont=dict(size=11)))
        fig.add_bar(x=g.values, y=[data.DISCHARGE_LABEL[r] for r in g.index], orientation="h",
                    marker=dict(color=colors), text=[f"{v:,.0f}" for v in g.values], textposition="outside",
                    textfont=dict(color=viz.INK_2, size=11),
                    customdata=[data.DISCHARGE_OUTCOME[r] for r in g.index],
                    hovertemplate="<b>%{y}</b><br>%{x:,.0f} discharges · %{customdata}<extra></extra>")
        fig.update_layout(showlegend=False, xaxis_range=[0, g.max() * 1.25])
        return viz.describe(fig, f"Horizontal bar chart of juvenile probation discharges by reason, {year_label()}, "
                                 f"{where_label(input)}: {viz.alt_values((data.DISCHARGE_LABEL[r], v) for r, v in g[::-1].items())}.")

    @viz.render_plot
    def violation_chart():
        g = input.grain()
        v = viol().assign(p=lambda d: period(d["date"], g))
        piv = v.pivot_table(index="p", columns="metric", values="value", aggfunc="sum", observed=True).fillna(0)
        if piv.empty:
            return viz.empty_figure()
        labels = period_labels(piv.index, g)
        fig = viz.figure(360, barmode="stack", yaxis=dict(tickformat=",.0f"))
        for t, name in (("technical", "Technical"), ("new offense", "New offense")):
            if t in piv.columns:
                fig.add_bar(name=name, x=labels, y=piv[t], marker=viz.bar_marker(viz.VIOLATION_COLOR[t]),
                            hovertemplate=f"<b>{name}</b><br>%{{x}}: %{{y:,.0f}}<extra></extra>")
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(piv) > 12 else 0))
        tot = piv.sum()
        return viz.describe(fig, f"Stacked bar chart of violation reports filed per {GRAIN[g].lower()}, {labels[0]} to "
                                 f"{labels[-1]}, technical vs new offense. Totals: "
                                 f"{viz.alt_values(tot.items())}.")

    @viz.render_plot
    def revocation_chart():
        g = input.grain()
        c = court().assign(p=lambda d: period(d["date"], g))
        piv = c.pivot_table(index="p", columns=["metric", "breakdown"], values="value", aggfunc="sum", observed=True).fillna(0)
        if piv.empty:
            return viz.empty_figure()
        labels = period_labels(piv.index, g)
        fig = viz.figure(360, hovermode="x unified", yaxis=dict(tickformat=".0%", rangemode="tozero"))
        ends = []
        for i, (t, name) in enumerate((("technical", "Technical"), ("new offense", "New offense"))):
            if (t, "revocation") not in piv.columns:
                continue
            tot = piv[t].sum(axis=1)
            rate = (piv[(t, "revocation")] / tot.where(tot > 0)).values
            fig.add_scatter(name=name, x=labels, y=rate, mode="lines+markers",
                            line=dict(color=viz.VIOLATION_COLOR[t], width=2),
                            marker=dict(symbol=viz.SYMBOLS[i], size=7, color=viz.VIOLATION_COLOR[t],
                                        line=dict(color=viz.SURFACE, width=1.5)),
                            hovertemplate="%{y:.1%}")
            ends.append((name, rate[-1]))
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(piv) > 12 else 0))
        return viz.describe(fig, f"Line chart of the share of court actions on violations that found a violation, per "
                                 f"{GRAIN[g].lower()}, {labels[0]} to {labels[-1]}, one line each for technical and "
                                 f"new-offense violations with distinct markers. Latest: {viz.alt_values(ends, '{:.0%}')}.")

    @viz.render_plot
    def djj_chart():
        g = djj().groupby("metric", observed=True)["value"].sum().reindex(data.DJJ_ORDER).dropna()
        if g.empty or not g.sum():
            return viz.empty_figure()
        return viz.simple_bar([data.DJJ_LABEL[c] for c in g.index], g.values, [viz.DJJ_COLOR[c] for c in g.index],
                              height=360, alt=f"Bar chart of commitments to the Department of Juvenile Justice by type, "
                                              f"{year_label()}, {where_label(input)}")

    @render.data_frame
    def table():
        a, d, v, c, j = adm(), dis(), viol(), court(), djj()
        ys = sorted(set(a["year"]) | set(d["year"]))
        adm_tot = a.groupby("year")["value"].sum().reindex(ys).fillna(0)
        adm_typ = a.pivot_table(index="year", columns="case", values="value", aggfunc="sum", observed=True).reindex(ys).fillna(0)
        dis_tot = d.groupby("year")["value"].sum().reindex(ys).fillna(0)
        outcome = d.assign(o=d["breakdown"].map(data.DISCHARGE_OUTCOME))
        dis_out = outcome.pivot_table(index="year", columns="o", values="value", aggfunc="sum").reindex(ys).fillna(0)
        viol_tot = v.groupby("year")["value"].sum().reindex(ys).fillna(0)
        viol_tech = v.loc[v["metric"] == "technical"].groupby("year")["value"].sum().reindex(ys).fillna(0)
        court_tot = c.groupby("year")["value"].sum().reindex(ys).fillna(0)
        rev = c.loc[c["breakdown"] == "revocation"].groupby("year")["value"].sum().reindex(ys).fillna(0)
        djj_tot = j.groupby("year")["value"].sum().reindex(ys).fillna(0)

        def share(num, den):
            return (num / den.where(den > 0)).map(lambda x: "–" if pd.isna(x) else f"{x:.1%}").values

        def col(piv, name):
            return piv[name] if name in piv.columns else pd.Series(0.0, index=ys)

        out = pd.DataFrame({
            "Year": [str(y) for y in ys],
            "Admissions": adm_tot.map("{:,.0f}".format).values,
            "Probation %": share(col(adm_typ, "probation"), adm_tot),
            "Supervision %": share(col(adm_typ, "supervision"), adm_tot),
            "CUS %": share(col(adm_typ, "cus"), adm_tot),
            "Informal %": share(col(adm_typ, "informal"), adm_tot),
            "Discharges": dis_tot.map("{:,.0f}".format).values,
            "Successful %": share(col(dis_out, "Successful"), dis_tot),
            "Unsuccessful %": share(col(dis_out, "Unsuccessful"), dis_tot),
            "Violations": viol_tot.map("{:,.0f}".format).values,
            "Technical %": share(viol_tech, viol_tot),
            "Revocations": rev.map("{:,.0f}".format).values,
            "Revocation rate": share(rev, court_tot),
            "DJJ commitments": djj_tot.map("{:,.0f}".format).values,
        })
        return render.DataGrid(out, width="100%")
