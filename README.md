# Illinois Juvenile Probation dashboard

A Python Shiny dashboard over the AOIC legacy juvenile-probation monthly statistics
(every county juvenile probation department, 2011 to the present), the juvenile twin of
`probation_dashboard`. The data come from the `aoic_legacy_juvenile` table built by the
`aoic_legacy` pipeline (`legacy_statistics`, `--program juvenile`), plus ACS county
population aged 10-17 from `illinois_demo`.

```
app.py                    Shiny entry point (navbar: overview + three pages)
dashboard/
  data.py                 loads the CSVs once at startup; section / label lookups; reporting helpers
  viz.py                  ICJIA palette, fixed entity colors, plotly base layout, accessible renderer
  common.py               shared circuit / county filters, reset, period helpers
  pages/
    home.py               overview - one tile per dashboard
    population.py         (1) active caseload, rate per 100k youth, case type, supervision level, petitions
    flows.py              (2) admissions, discharges by reason, violations, revocations, DJJ commitments
    intakes.py            (3) intake demographics, Black : White disparity, school enrollment
data/
  build_data.py           rebuilds the CSVs below (DuckDB, or the pipeline's CSV copy + Census API when locked)
  juvenile.csv            county x year x template row, months as columns (only the sections used)
  youth.csv               residents aged 10-17 per county / year: total, by race, by sex
  meta.json               departments reporting per month, last usable month per year, county list, WIP year
  il_counties.geojson     county boundaries for the maps
smoke_test.py             headless check that every output on a running app renders without error
```

## Run locally

```
pip install -r requirements.txt
python data/build_data.py        # DuckDB when free, else data_backups CSV + Census API
shiny run app.py --reload
python smoke_test.py http://127.0.0.1:8000 inputs.json   # optional; see the docstring
```

## Definitions (AOIC Juvenile Probation Monthly Report template)

- **Active caseload** - cases under active supervision on the last day of the month,
  by case type (probation, supervision, continued under supervision (CUS), informal,
  other) and supervision level (maximum / medium / minimum / unclassified), Section XIII.
  **Administrative caseload** (XII) are open files without regular face-to-face contact.
- **Rate** - active caseload per 100,000 residents aged 10-17 (ACS; years after the
  latest ACS use its last year), the ages of Illinois juvenile court jurisdiction. Only
  counties whose department reported an active caseload for the month count toward the
  denominator. Greene-Scott reported jointly through 2016; its caseload is rated against
  both counties' youth and mapped on both.
- **Petitions filed** (I.A) - delinquency, addiction, MRAI (minor requiring authoritative
  intervention), truancy, neglect/abuse, dependent.
- **Admissions** - new cases added to the active caseload (IX.B), by case type.
- **Discharges** - cases dropped from active supervision (IX.F): scheduled termination,
  early termination, absconder/warrant, revoked-technical, revoked-new offense, alternate
  DJJ commitment, unsatisfactory termination, transferred out, other. *Successful* =
  scheduled or early termination; *unsuccessful* = absconder, revoked, alternate DJJ
  commitment, unsatisfactory; *other* = transferred, other.
- **Violations reported** (XV) and **court actions** (XVI) - as on the adult form; the
  revocation rate is findings of violation ÷ all findings.
- **Commitments to DJJ** (X) - full, evaluation, Habitual Juvenile Offender, Violent
  Juvenile Offender.
- **Intakes** (IV) - every minor the department took in, by sex, age (12 and under to 17
  and over) and race/ethnicity, each reported for *formal* (petition filed) and
  *informal* cases; IV.D counts delinquency intakes enrolled in school. Section V
  (intakes completed, full / partial) is loaded but not shown.
- **Disparity** - Black intake rate ÷ White intake rate, per 100,000 youth of the same
  group. ACS race groups include Hispanic residents; Hispanic is also its own group.

## Coverage

Departments report with a lag and the latest months understate statewide totals.
`build_data.py` marks, per year, the last month in which at least 90% of that year's peak
number of departments reported; later months are hidden. Every headline tile shows
"N of M departments reported", where M is the number of departments with a juvenile
sheet in that year's workbooks (101 through 2016, 102 after, 96 in 2025 - the 9th
Circuit's 2025-26 workbooks and the 16th Circuit's 2024 workbook are not publicly
shared). Non-reporting counties are hatched grey on the maps and show "–" in the county
table. Years from which fewer than 95% of the peak department count has a sheet are
marked "still being reported" on the trend charts (dashed line).

## Accessibility

Same conventions as `prison_dashboard`: every chart has alternative text (`role="img"`
+ `aria-label` + hidden paragraph, set with `viz.describe`), the map has a black state
outline and fills of at least 3:1 contrast, stacked area charts have seams and end
labels, and multi-line charts use distinct marker shapes.
