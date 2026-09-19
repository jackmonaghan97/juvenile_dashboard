"""Filter controls and helpers shared by the pages."""
import pandas as pd
from shiny import ui

from . import data, viz

GRAIN = {"M": "Month", "Q": "Quarter", "Y": "Year"}


def multi_select(id: str, label: str, choices, placeholder: str = "All"):
    """Multi-select dropdown; nothing selected means no filter."""
    return ui.input_selectize(
        id, label, choices=choices, multiple=True, remove_button=True,
        options={"placeholder": placeholder, "plugins": ["remove_button"]},
    )


def geo_filters():
    """Circuit (single) and county (multi) dropdowns."""
    return [
        ui.input_select("circuit", "Judicial circuit",
                        choices={"all": "All circuits", **{str(c): l for c, l in data.circuits().items()}},
                        selected="all"),
        multi_select("county", "County (probation department)", data.meta()["counties"]),
    ]


def reset_geo():
    ui.update_select("circuit", selected="all")
    ui.update_selectize("county", selected=[])


def apply_geo(df: pd.DataFrame, input) -> pd.DataFrame:
    if input.circuit() != "all":
        df = df.loc[df["circuit"] == int(input.circuit())]
    if input.county():
        df = df.loc[df["county"].isin(list(input.county()))]
    return df


def where_label(input) -> str:
    if input.county():
        c = list(input.county())
        return c[0] + " County" if len(c) == 1 else f"{len(c)} counties"
    if input.circuit() != "all":
        return data.circuits()[int(input.circuit())]
    return "Illinois"


def reset_button():
    return ui.input_action_button("reset", "Reset filters", class_="btn-outline-secondary btn-sm w-100 mb-2")


def selected(input, id: str, all_choices) -> list:
    vals = input[id]() if id in input else None
    return list(vals) if vals else list(all_choices)


def isin_or_all(series: pd.Series, vals) -> pd.Series:
    return series.isin(vals) if vals else pd.Series(True, index=series.index)


def period(dates: pd.Series, grain: str) -> pd.Series:
    return dates.dt.to_period(grain).dt.to_timestamp()


def period_labels(index, grain: str) -> list[str]:
    if grain == "Q":
        return [f"Q{d.quarter} {d.year}" for d in index]
    return list(index.strftime({"M": "%b %Y", "Y": "%Y"}[grain]))


def partial_note(year: int) -> str:
    """'' for a complete year, else 'through Aug 2026'."""
    last = data.meta()["last_month"].get(int(year), 12)
    return "" if last >= 12 else f" (through {pd.Timestamp(year=int(year), month=last, day=1):%b %Y})"


def note(text: str):
    return ui.p(text, class_="text-muted small mb-0")


def fmt_pct(x) -> str:
    return "–" if pd.isna(x) else f"{x:.1%}"


def fmt_rate(x) -> str:
    return "–" if pd.isna(x) else f"{x:,.0f}"
