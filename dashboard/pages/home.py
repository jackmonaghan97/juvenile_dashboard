"""Overview - one large tile per dashboard; clicking a tile opens it."""
from shiny import reactive, ui

# (nav value, title, what it answers, what is inside, data source)
TILES = [
    ("population", "Population & rate",
     "How many minors are under active juvenile probation supervision, how that compares with each "
     "county's population aged 10-17, and what kind of cases they are.",
     ["Active caseload & rate per 100k youth", "County map", "Caseload trend by case type / supervision "
      "level / caseload type / petitions filed", "Case type & supervision level", "Petitions filed by type", "County table"],
     "AOIC juvenile probation monthly reports (Sections XIII, XII, I.A) · U.S. Census ACS"),
    ("flows", "Admissions, discharges & violations",
     "How many cases enter and leave active supervision, how supervision ends, how often violations "
     "are reported and lead to revocation, and how many minors are committed to DJJ.",
     ["Admissions vs. discharges & net change", "Admissions by case type", "Discharges by reason & outcome",
      "Violations by type", "Revocation rate", "Commitments to DJJ", "Yearly table"],
     "AOIC juvenile probation monthly reports (Sections IX, X, XV, XVI)"),
    ("intakes", "Intake demographics & disparities",
     "Who enters juvenile probation: intakes by race/ethnicity, sex, age and formal vs informal handling, "
     "and intake rates per 100,000 youth with the Black : White disparity.",
     ["Intakes & rate per 100k youth", "County map", "Intake trend by group", "Rates by race and sex",
      "Age distribution", "Disparity over time", "School enrollment at intake"],
     "AOIC juvenile probation monthly reports (Section IV) · U.S. Census ACS"),
]


def page_ui():
    tiles = [
        ui.input_action_button(
            f"go_{value}",
            ui.div(
                ui.h2(title, class_="tile-title"),
                ui.p(blurb, class_="tile-blurb"),
                ui.div(*[ui.span(item, class_="tile-chip") for item in items], class_="tile-chips"),
                ui.p(ui.span("Data: ", class_="fw-semibold"), source, class_="tile-source"),
                ui.span("Open dashboard →", class_="tile-cta"),
                class_="tile-body",
            ),
            class_="home-tile",
        )
        for value, title, blurb, items, source in TILES
    ]
    return ui.div(
        ui.div(
            ui.h1("Illinois Juvenile Probation", class_="home-heading"),
            ui.p("Caseloads, admissions and discharges, violations, DJJ commitments and intake demographics reported "
                 "monthly by every county juvenile probation department to the Administrative Office of the Illinois "
                 "Courts (AOIC), 2011 to the present. Pick a dashboard to start; every page has filters in the sidebar.",
                 class_="home-lead"),
            class_="home-intro",
        ),
        ui.layout_column_wrap(*tiles, width=1 / 3, fill=False, heights_equal="all", class_="home-grid"),
        ui.p("Definitions follow the AOIC Juvenile Probation Monthly Report template. "
             "Counties report on a fixed template; a handful of "
             "county-months are blank or unbalanced in the source and appear as gaps.",
             class_="text-muted small mt-3"),
        class_="home",
    )


def page_server(input, nav_id: str = "nav"):
    for value, *_ in TILES:
        def _make(v):
            @reactive.effect
            @reactive.event(input[f"go_{v}"])
            def _go():
                ui.update_navset(nav_id, selected=v)
        _make(value)
