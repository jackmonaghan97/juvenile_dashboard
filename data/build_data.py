"""
Build the dashboard's CSVs. Run:  python data/build_data.py

Reads
    aoic_legacy_juvenile    DuckDB table loaded by the aoic_legacy pipeline (juvenile sheets); when the
                            DuckDB file is locked, the pipeline's CSV copy in data_backups is read instead
    illinois_demo           ACS county population by race / sex / age (DuckDB), or the Census API when locked
Writes
    juvenile.csv            county x year x template row, months as columns (only the sections used)
    youth.csv               residents aged 10-17 per county / year, total and by race and sex
    meta.json               last reported month, departments per year, county list, first WIP year
"""
import json
import os
from pathlib import Path

import pandas as pd
import requests

DB_PATH = r"C:\Users\jackm\OneDrive\Documents\duckdb_cli-windows-amd64\my_database.duckdb"
BACKUP_CSV = Path(r"C:\Users\jackm\OneDrive\Documents\git_projects\data_backups\legacy_statistics\aoic_legacy_juvenile.csv")
DATA_DIR = Path(__file__).resolve().parent
CENSUS_KEY = os.environ.get("CENSUS_API_KEY", "fd064e7df45fb33f4aa671359f50e214d68df1fb")
ACS = "https://api.census.gov/data/{year}/acs/acs5"
# a year is "still being reported" once fewer than this share of the peak department count has a sheet
WIP_SHARE = 0.95

# template sections the dashboard uses (breakdown_category in the map) and the
# breakdowns kept within them
SECTIONS = {
    "petitions":               None,
    "demographics of intakes": None,
    "intakes":                 None,
    "admissions":              None,
    "new cases":               None,
    "readmit admin":           None,
    "transferred in":          None,
    "discharge":               None,
    "population":              ["active", "admin"],
    "population EOM":          None,
    "djj commitments":         None,
    "criminal prosecutions":   None,
    "reported violations":     None,
    "court actions":           None,
}

RACE = {
    "BLACK_OR_AFRICAN_AMERICAN": "black", "WHITE": "white", "HISPANIC_OR_LATINO": "hispanic",
    "ASIAN": "asian", "AMERICAN_INDIAN_OR_ALASKA_NATIVE": "american indian",
    "NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER": "other", "OTHER": "other", "TWO_OR_MORE_RACE": "other",
}
# Illinois juvenile court jurisdiction: ages 10 through 17; ACS bins that cover it
YOUTH_AGES = ("10-14", "15-17")
# B01001 race-table suffix -> illinois_demo race label (same as the census pipeline)
B01001 = {"A": "WHITE", "B": "BLACK_OR_AFRICAN_AMERICAN", "C": "AMERICAN_INDIAN_OR_ALASKA_NATIVE", "D": "ASIAN",
          "E": "NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER", "F": "OTHER", "G": "TWO_OR_MORE_RACE",
          "I": "HISPANIC_OR_LATINO"}
# B01001x cells for ages 10-14 and 15-17: male 005/006, female 020/021
YOUTH_CELLS = {"MALE": ["005", "006"], "FEMALE": ["020", "021"]}


def _connect():
    """DuckDB connection, or None when another program holds the file."""
    try:
        import duckdb
        return duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:                                   # ImportError or the IO lock
        print(f"    DuckDB unavailable ({str(e).splitlines()[0]})")
        return None


def juvenile(con) -> pd.DataFrame:
    """County x year x template row, months as columns."""
    if con is not None:
        keep = " OR ".join(
            f"(breakdown_category = '{sec}'" + (f" AND breakdown IN ({', '.join(repr(b) for b in bds)}))" if bds else ")")
            for sec, bds in SECTIONS.items())
        months = ", ".join(f"SUM(value) FILTER (WHERE month = {m}) AS m{m:02d}" for m in range(1, 13))
        return con.execute(f"""
            SELECT county, circuit, year, breakdown_category AS section, breakdown, metric, subgroup, {months}
            FROM aoic_legacy_juvenile
            WHERE NOT is_total AND ({keep})
            GROUP BY ALL
            ORDER BY county, year, section, breakdown, metric, subgroup""").df()
    print(f"    reading {BACKUP_CSV}")
    df = pd.read_csv(BACKUP_CSV, dtype={"county": "string"})
    df = df.loc[~df["is_total"]]
    keep = pd.Series(False, index=df.index)
    for sec, bds in SECTIONS.items():
        keep |= (df["breakdown_category"] == sec) & (df["breakdown"].isin(bds) if bds else True)
    df = df.loc[keep]
    wide = (df.pivot_table(index=["county", "circuit", "year", "breakdown_category", "breakdown", "metric", "subgroup"],
                           columns="month", values="value", aggfunc="sum")
              .rename(columns=lambda m: f"m{m:02d}").reset_index()
              .rename(columns={"breakdown_category": "section"}))
    return wide.sort_values(["county", "year", "section", "breakdown", "metric", "subgroup"]).reset_index(drop=True)


def _youth_frame(d: pd.DataFrame) -> pd.DataFrame:
    """county / year / race / sex / n (ages 10-17) -> total, by race, by sex. Hispanic overlaps the races."""
    d["race"] = d["race"].map(RACE)
    non_hisp = d.loc[d["race"] != "hispanic"]
    total = non_hisp.groupby(["county", "year"], as_index=False)["n"].sum().assign(group_type="all", group="all")
    by_race = d.groupby(["county", "year", "race"], as_index=False)["n"].sum().rename(columns={"race": "group"}) \
               .assign(group_type="race")
    by_sex = non_hisp.groupby(["county", "year", "sex"], as_index=False)["n"].sum().rename(columns={"sex": "group"}) \
              .assign(group_type="sex")
    by_sex["group"] = by_sex["group"].str.lower()
    out = pd.concat([total, by_race, by_sex], ignore_index=True).rename(columns={"n": "youth"})
    return out[["county", "year", "group_type", "group", "youth"]]


def youth(con) -> pd.DataFrame:
    """Residents aged 10-17 per county-year from illinois_demo, or straight from the ACS API."""
    if con is not None:
        d = con.execute("""
            SELECT REPLACE(county_name, ' County, Illinois', '') AS county, year, race, sex,
                   SUM(TRY_CAST(value AS DOUBLE)) AS n
            FROM illinois_demo
            WHERE year IS NOT NULL AND age IN (SELECT UNNEST(?))
            GROUP BY 1, 2, 3, 4""", [list(YOUTH_AGES)]).df()
        return _youth_frame(d)
    print("    fetching ACS B01001A-I from the Census API")
    rows, year = [], 2010                                    # 2009 is doubled in illinois_demo; start at 2010
    while True:
        r = requests.get(ACS.format(year=year), timeout=120,
                         params={"get": "NAME," + ",".join(f"B01001{s}_{c}E" for s in B01001 for cs in YOUTH_CELLS.values() for c in cs),
                                 "for": "county:*", "in": "state:17", "key": CENSUS_KEY})
        if not r.ok:
            break
        head, *body = r.json()
        for rec in body:
            rec = dict(zip(head, rec))
            county = rec["NAME"].replace(" County, Illinois", "")
            for s, race in B01001.items():
                for sex, cells in YOUTH_CELLS.items():
                    rows.append(dict(county=county, year=year, race=race, sex=sex,
                                     n=sum(float(rec[f"B01001{s}_{c}E"]) for c in cells)))
        year += 1
    return _youth_frame(pd.DataFrame(rows))


def coverage(wide: pd.DataFrame) -> tuple[dict, dict, dict]:
    """
    Departments reporting an active caseload per year-month, departments with a sheet in
    the year's workbooks, and per year the last month with at least 90% of that year's
    peak coverage (reports trail by a few months).
    """
    pop = wide.loc[(wide["section"] == "population") & (wide["breakdown"] == "active")]
    months = [f"m{m:02d}" for m in range(1, 13)]
    by_county = pop.groupby(["year", "county"])[months].sum()
    cov, last, deps = {}, {}, {}
    for y, g in by_county.groupby(level="year"):
        n = (g > 0).sum()                                   # departments with a caseload, per month
        cov[int(y)] = {m + 1: int(v) for m, v in enumerate(n)}
        deps[int(y)] = int(wide.loc[wide["year"] == y, "county"].nunique())
        ok = [m + 1 for m, v in enumerate(n) if v > 0 and v >= 0.9 * n.max()]
        last[int(y)] = max(ok) if ok else 0
    return cov, last, deps


def wip_from(departments: dict) -> int | None:
    """First year from which the data are still being reported (department count under WIP_SHARE of the peak)."""
    peak = max(departments.values())
    low = {y for y, n in departments.items() if n < WIP_SHARE * peak}
    wip = [y for y in low if all(z in low for z in departments if z > y)]
    return min(wip) if wip else None


if __name__ == "__main__":
    con = _connect()
    print("1/3 juvenile.csv")
    wide = juvenile(con)
    wide.to_csv(DATA_DIR / "juvenile.csv", index=False)
    print(f"    {len(wide):,} rows")

    print("2/3 youth.csv")
    y = youth(con)
    y.to_csv(DATA_DIR / "youth.csv", index=False)
    if con is not None:
        con.close()

    print("3/3 meta.json")
    cov, last, deps = coverage(wide)
    meta = {"last_month": last, "coverage": cov, "departments": deps, "wip_from": wip_from(deps),
            "counties": sorted(wide["county"].unique().tolist()),
            "acs_years": [int(y["year"].min()), int(y["year"].max())]}
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print("    last usable month by year:", last)
    print("    departments with a sheet by year:", deps, "| WIP from", meta["wip_from"])
