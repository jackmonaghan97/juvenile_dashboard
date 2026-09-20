"""Load the CSVs produced by data/build_data.py once at startup."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MONTH_COLS = [f"m{m:02d}" for m in range(1, 13)]

# IX / XIII case types (a - e on the form)
CASE_ORDER = ["probation", "supervision", "cus", "informal", "other"]
CASE_LABEL = {"probation": "Probation", "supervision": "Supervision", "cus": "Continued under supervision",
              "informal": "Informal", "other": "Other"}
LEVEL_ORDER = ["max", "med", "min", "unclassified"]
LEVEL_LABEL = {"max": "Maximum", "med": "Medium", "min": "Minimum", "unclassified": "Unclassified"}
DISCHARGE_ORDER = ["scheduled termination", "early termination", "absconder/warrant", "revoked-technical",
                   "revoked-new", "alt djj commit", "unsatisfactory", "transferred", "other"]
DISCHARGE_LABEL = {"scheduled termination": "Scheduled termination", "early termination": "Early termination",
                   "absconder/warrant": "Absconder / warrant", "revoked-technical": "Revoked – technical",
                   "revoked-new": "Revoked – new offense", "alt djj commit": "Alternate DJJ commitment",
                   "unsatisfactory": "Unsatisfactory termination", "transferred": "Transferred out",
                   "other": "Other"}
# Justice Counts outcome groups (successful / unsuccessful / other)
DISCHARGE_OUTCOME = {"scheduled termination": "Successful", "early termination": "Successful",
                     "absconder/warrant": "Unsuccessful", "revoked-technical": "Unsuccessful",
                     "revoked-new": "Unsuccessful", "alt djj commit": "Unsuccessful",
                     "unsatisfactory": "Unsuccessful", "transferred": "Other", "other": "Other"}
RACE_ORDER = ["black", "white", "hispanic", "asian", "american indian", "other"]
RACE_LABEL = {"black": "Black", "white": "White", "hispanic": "Hispanic", "asian": "Asian",
              "american indian": "American Indian", "other": "Other"}
SEX_ORDER = ["male", "female"]
SEX_LABEL = {"male": "Male", "female": "Female"}
AGE_ORDER = ["12-under", "13", "14", "15", "16", "17-over"]
AGE_LABEL = {"12-under": "12 and under", "17-over": "17 and over"}
# I.A petition types (also III admissions by petition type)
PETITION_ORDER = ["delinquency", "addiction", "mrai", "truancy", "neglect/abuse", "dependent"]
PETITION_LABEL = {"delinquency": "Delinquency", "addiction": "Addiction", "mrai": "MRAI", "truancy": "Truancy",
                  "neglect/abuse": "Neglect / abuse", "dependent": "Dependent"}
# X commitments to the Department of Juvenile Justice
DJJ_ORDER = ["full", "evaluation", "habitual juvenile offender", "violent juvenile offender"]
DJJ_LABEL = {"full": "Full commitment", "evaluation": "Evaluation", "habitual juvenile offender": "Habitual offender",
             "violent juvenile offender": "Violent offender"}
# IV demographics are reported for formal and informal cases separately
SUBGROUP_ORDER = ["formal", "informal"]
SUBGROUP_LABEL = {"formal": "Formal", "informal": "Informal"}

# departments that file one sheet for several counties -> the census counties they cover
JOINT = {"Greene-Scott": ["Greene", "Scott"]}


@lru_cache
def meta() -> dict:
    m = json.loads((DATA_DIR / "meta.json").read_text())
    m["last_month"] = {int(k): v for k, v in m["last_month"].items()}
    m["coverage"] = {int(y): {int(mo): n for mo, n in d.items()} for y, d in m["coverage"].items()}
    m["departments"] = {int(k): v for k, v in m.get("departments", {}).items()}
    return m


def wip_from() -> int | None:
    """First year whose data are still being reported (departments missing sheets), or None."""
    return meta().get("wip_from")


def wip_start() -> pd.Timestamp | None:
    y = wip_from()
    return pd.Timestamp(year=y, month=1, day=1) if y else None


def default_year() -> int:
    """Latest year reported through December (the current year is usually partial)."""
    complete = [y for y, m in meta()["last_month"].items() if m >= 12]
    return max(complete) if complete else max(meta()["last_month"])


def reporting(year: int, month: int) -> tuple[int, int]:
    """(departments that reported a caseload that month, departments with a sheet that year)."""
    return (meta()["coverage"].get(int(year), {}).get(int(month), 0),
            meta()["departments"].get(int(year), len(meta()["counties"])))


@lru_cache
def wide() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "juvenile.csv")
    for c in ["county", "section", "breakdown", "metric", "subgroup"]:
        df[c] = df[c].astype("category")
    return df


@lru_cache
def long() -> pd.DataFrame:
    """
    One row per county / month / template row, restricted to reported months.
    Adds `case` (probation / supervision / cus / informal / other) and `level` (max /
    med / min / unclassified) parsed from the classification-of-caseload metrics.

    Startup cost matters (the free hosting tier has a sliver of a CPU), so the parsing is
    done once per distinct metric on the wide table and the dates are built arithmetically
    rather than with to_datetime over 2.8M rows.
    """
    w = wide()
    # 'probation max', 'cus unclassified' -> case + level; elsewhere the metric itself may be a case type
    metrics = pd.Series(w["metric"].cat.categories, index=w["metric"].cat.categories).astype(str)
    case_of = metrics.str.extract(r"^(probation|supervision|cus|informal|other)\b")[0]
    level_of = metrics.str.extract(r"(max|med|min|unclassified)$")[0]
    pop = w["section"] == "population"
    m = w["metric"].astype(str)
    case = pd.Series(case_of.reindex(m).values, index=w.index).where(pop, m.where(m.isin(CASE_ORDER)))
    level = pd.Series(level_of.reindex(m).values, index=w.index).where(pop)
    w = w.assign(case=case.astype("category"), level=level.astype("category"))

    df = w.melt(id_vars=["county", "circuit", "year", "section", "breakdown", "metric", "subgroup", "case", "level"],
                value_vars=MONTH_COLS, var_name="month", value_name="value")
    df["month"] = df["month"].str[1:].astype(int)
    last = df["year"].map(meta()["last_month"]).fillna(12)
    df = df.loc[df["month"] <= last].copy()
    df["date"] = ((df["year"].to_numpy() - 1970).astype("datetime64[Y]")
                  + (df["month"].to_numpy() - 1).astype("timedelta64[M]")).astype("datetime64[ns]")
    df["case"] = df["case"].astype("category")
    df["level"] = df["level"].astype("category")
    return df


def section(name: str, breakdown=None) -> pd.DataFrame:
    df = long()
    df = df.loc[df["section"] == name]
    if breakdown is not None:
        df = df.loc[df["breakdown"].isin([breakdown] if isinstance(breakdown, str) else breakdown)]
    return df


@lru_cache
def reported() -> pd.DataFrame:
    """
    One row per department / year / month with `reported` = the department filed an
    active caseload for that month (a blank sheet or a missing sheet both count as not
    reported). Unfiltered, so a case-type / level filter never turns a county "off".
    """
    a = section("population", "active")
    g = a.groupby(["county", "year", "month"], observed=True)["value"].sum(min_count=1).reset_index()
    g["reported"] = g["value"].fillna(0) > 0
    return g[["county", "year", "month", "reported"]]


@lru_cache
def county_circuit(year: int) -> pd.DataFrame:
    """
    county -> circuit for one year (Monroe, Perry, Randolph and Washington moved from the
    20th to the new 24th circuit in 2023, so an all-years mapping would list them twice).
    A joint department's counties take its circuit; a county with no sheet that year
    keeps its most recent circuit so it still belongs to a geography.
    """
    w = wide()[["county", "circuit", "year"]].drop_duplicates()
    w["county"] = w["county"].astype(str)
    this = w.loc[w["year"] == int(year)]
    latest = w.sort_values("year").drop_duplicates("county", keep="last")
    m = pd.concat([this, latest], ignore_index=True)[["county", "circuit"]]
    extra = [dict(county=c, circuit=r.circuit) for r in this.itertuples() for c in JOINT.get(r.county, [])]
    return pd.concat([m, pd.DataFrame(extra, columns=m.columns)], ignore_index=True).drop_duplicates("county")


def reporting_departments(year: int, month: int) -> list[str]:
    """Departments that reported an active caseload for the month."""
    r = reported()
    return r.loc[(r["year"] == int(year)) & (r["month"] == int(month)) & r["reported"], "county"].tolist()


def reporting_counties(year: int, month: int) -> list[str]:
    """Census counties covered by a reporting department (a joint department covers each of its counties)."""
    return [c for d in reporting_departments(year, month) for c in JOINT.get(d, [d])]


@lru_cache
def youth() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "youth.csv")


def youth_for(years, group_type: str | None = "all") -> pd.DataFrame:
    """
    Residents aged 10-17 per county for each requested year; years past the ACS use its
    last year. group_type 'all' (default), 'race', 'sex', or None for every group.
    """
    a = youth()
    if group_type is not None:
        a = a.loc[a["group_type"] == group_type]
    y0, y1 = meta()["acs_years"]
    out = []
    for y in years:
        part = a.loc[a["year"] == min(max(int(y), y0), y1)].copy()
        part["year"] = int(y)
        out.append(part)
    return pd.concat(out, ignore_index=True)


@lru_cache
def il_counties() -> dict:
    return json.loads((DATA_DIR / "il_counties.geojson").read_text())


@lru_cache
def il_outline() -> tuple[list, list]:
    """The state line around the county map (lon / lat lists), for the choropleths."""
    from . import viz
    return viz.outer_boundary(il_counties())


@lru_cache
def circuits() -> dict:
    """circuit code -> label, e.g. 1 -> '1st Circuit', 99 -> 'Cook County'."""
    def ordinal(n):
        return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    codes = sorted(int(c) for c in wide()["circuit"].unique())
    return {c: ("Cook County" if c == 99 else f"{ordinal(c)} Circuit") for c in codes}


def warm_cache() -> None:
    for loader in (meta, wide, long, reported, youth, il_counties, il_outline, circuits):
        loader()
