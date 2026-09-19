"""
Illinois juvenile probation dashboard (AOIC legacy monthly statistics).

Run:   shiny run app.py --reload
Data:  python data/build_data.py   (writes the CSVs in data/ from the DuckDB source)
"""
from shiny import App, ui

from dashboard import data, viz
from dashboard.pages import flows, home, intakes, population

data.warm_cache()

NAVY_RGB = ",".join(str(int(viz.NAVY[i:i + 2], 16)) for i in (1, 3, 5))

CSS = f"""
:root {{ --bs-primary: {viz.NAVY}; --bs-primary-rgb: {NAVY_RGB}; --bs-link-color: {viz.BLUE};
         --bs-link-hover-color: {viz.NAVY}; --bs-link-color-rgb: 21,101,192; }}
body {{ background: {viz.PAGE}; }}
.card {{ background: {viz.SURFACE}; border: 1px solid rgba(11,11,11,0.10); box-shadow: none; }}
.card-header {{ background: transparent; border-bottom: 1px solid {viz.GRID};
                font-weight: 600; color: {viz.INK}; }}
.card-footer {{ background: transparent; border-top: 1px solid {viz.GRID}; }}
.bslib-sidebar-layout > .sidebar {{ background: {viz.SURFACE}; }}

/* navbar: ICJIA navy (bg/theme set via navbar_options) */
.navbar .navbar-brand {{ font-weight: 600; }}
.navbar .nav-link.active {{ font-weight: 600; box-shadow: inset 0 -3px 0 {viz.SEQ_BLUE[2]}; }}
/* "|" separators between the dashboard titles */
.navbar .navbar-nav > .nav-item + .nav-item:not(.ms-auto) {{ display: flex; align-items: center; }}
.navbar .navbar-nav > .nav-item + .nav-item:not(.ms-auto)::before {{
    content: "|"; color: rgba(255,255,255,0.45); padding: 0 0.25rem; }}
.navbar .nav-link.text-muted {{ color: rgba(255,255,255,0.6) !important; }}

/* value boxes: compact - the content sets the height, not a minimum */
.bslib-value-box {{ border: 1px solid rgba(11,11,11,0.10); box-shadow: none; min-height: 0; }}
.bslib-value-box.bg-primary {{ background: {viz.NAVY} !important; border-color: {viz.NAVY}; }}
.bslib-value-box .value-box-area {{ padding: 0.7rem 1rem; gap: 0; }}
.bslib-value-box .value-box-title {{ font-size: 0.85rem; margin-bottom: 0.1rem; }}
.bslib-value-box .value-box-value {{ font-weight: 600; font-size: 1.7rem; line-height: 1.15;
                                     margin-bottom: 0.1rem; }}
.bslib-value-box p {{ margin-bottom: 0; font-size: 0.8rem; }}

/* sidebar inputs, all keyed to the same blue */
.sidebar .shiny-input-container {{ margin-bottom: 0.6rem; }}
.sidebar .selectize-control.multi .selectize-input > div {{ background: {viz.BLUE_TINT}; color: {viz.NAVY};
                                                           border: 1px solid #bcd8f5; }}
.sidebar .selectize-input, .sidebar .form-select {{ border-color: {viz.AXIS}; }}
.form-check-input:checked {{ background-color: {viz.BLUE}; border-color: {viz.BLUE}; }}
.irs--shiny .irs-bar {{ background: {viz.BLUE}; border-color: {viz.BLUE}; }}
.irs--shiny .irs-from, .irs--shiny .irs-to, .irs--shiny .irs-single {{ background: {viz.NAVY}; }}
.irs--shiny .irs-handle {{ border-color: {viz.BLUE}; }}
.btn-outline-secondary {{ color: {viz.NAVY}; border-color: {viz.STEEL}; }}
.btn-outline-secondary:hover {{ background: {viz.NAVY}; border-color: {viz.NAVY}; color: #fff; }}

/* overview tiles */
.home {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
.home-heading {{ font-weight: 700; margin-bottom: 0.4rem; color: {viz.NAVY}; }}
.home-lead {{ color: {viz.INK_2}; max-width: 760px; margin-bottom: 1.5rem; }}
.home-tile {{ display: block; width: 100%; text-align: left; white-space: normal;
              background: {viz.SURFACE}; color: {viz.INK}; border: 1px solid rgba(11,11,11,0.12);
              border-radius: 0.6rem; padding: 0; transition: border-color .15s, box-shadow .15s; }}
.home-tile:hover, .home-tile:focus {{ border-color: {viz.BLUE}; box-shadow: 0 0 0 3px rgba(21,101,192,0.15);
                                      background: {viz.SURFACE}; color: {viz.INK}; }}
.tile-body {{ padding: 1.4rem 1.5rem 1.2rem; display: flex; flex-direction: column; gap: 0.6rem; height: 100%; }}
.tile-title {{ font-size: 1.5rem; font-weight: 700; margin: 0; color: {viz.NAVY}; }}
.tile-blurb {{ margin: 0; color: {viz.INK_2}; }}
.tile-chips {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
.tile-chip {{ font-size: 0.78rem; padding: 0.18rem 0.6rem; border-radius: 999px;
              background: #e9e9e6; border: 1px solid #d5d5d0; color: {viz.INK_2}; }}
.tile-source {{ margin: 0; font-size: 0.8rem; color: {viz.MUTED}; }}
.tile-cta {{ margin-top: auto; font-weight: 600; color: {viz.BLUE}; }}

/* definition callout at the top of a page */
.callout {{ background: {viz.BLUE_TINT}; border-left: 4px solid {viz.BLUE}; border-radius: 0.4rem;
            padding: 0.7rem 1rem; margin-bottom: 1rem; color: {viz.INK_2}; font-size: 0.9rem; }}
.callout strong {{ color: {viz.NAVY}; }}

/* sortable tables */
.sortable-wrap {{ overflow: auto; }}
.sortable-table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
.sortable-table th {{ position: sticky; top: 0; background: {viz.SURFACE}; text-align: left;
                      padding: 0.45rem 0.6rem; border-bottom: 2px solid {viz.GRID}; cursor: pointer;
                      user-select: none; white-space: nowrap; color: {viz.INK}; }}
.sortable-table th:hover {{ color: {viz.BLUE}; }}
.sortable-table th::after {{ content: "⇅"; color: {viz.AXIS}; margin-left: 0.35rem; font-size: 0.75rem; }}
.sortable-table th.asc::after {{ content: "▲"; color: {viz.BLUE}; }}
.sortable-table th.desc::after {{ content: "▼"; color: {viz.BLUE}; }}
.sortable-table td {{ padding: 0.35rem 0.6rem; border-bottom: 1px solid {viz.GRID}; white-space: nowrap; }}
.sortable-table td[data-v] {{ text-align: right; font-variant-numeric: tabular-nums; }}
.sortable-table th:not(:first-child) {{ text-align: right; }}
.sortable-table tr.pinned td {{ font-weight: 600; background: {viz.BLUE_TINT};
                                position: sticky; top: 34px; z-index: 1; }}
.sortable-table th {{ z-index: 2; }}
"""

# Plotly's `responsive` config only listens to window resizes. Charts drawn while their
# nav panel is hidden (width 0) or when the sidebar collapses also need a re-fit, so
# watch every card's size and resize the plots inside it.
JS = """
(function () {
  const timers = new WeakMap();
  function refit(el) {
    if (!window.Plotly || !el._fullLayout || !el.offsetWidth) return;
    clearTimeout(timers.get(el));
    timers.set(el, setTimeout(() => Plotly.Plots.resize(el), 100));
  }
  const ro = new ResizeObserver(entries => entries.forEach(e =>
    e.target.querySelectorAll(".plotly-chart").forEach(refit)));
  function observeAll() {
    document.querySelectorAll(".plotly-chart").forEach(el => {
      const box = el.closest(".card") || el.parentElement;
      if (box && !box.dataset.plotRo) { box.dataset.plotRo = "1"; ro.observe(box); }
    });
  }
  document.addEventListener("shiny:value", () => setTimeout(observeAll, 50));
  document.addEventListener("shown.bs.tab", (e) => {
    document.querySelectorAll(".plotly-chart").forEach(refit);
    // ionRangeSlider mis-places a handle when it was built inside a hidden tab (width 0),
    // so the first time a pane is shown re-apply the initial values it was given
    const pane = document.querySelector(e.target.getAttribute("href") || e.target.dataset.bsTarget || "");
    (pane || document).querySelectorAll(".js-range-slider").forEach(el => {
      const irs = window.jQuery && jQuery(el).data("ionRangeSlider");
      if (!irs || el.dataset.irsSynced) return;
      el.dataset.irsSynced = "1";
      irs.update({from: irs.options.from, to: irs.options.to});
      jQuery(el).trigger("change");
    });
  });
})();
"""

app_ui = ui.page_navbar(
    ui.nav_panel("Overview", home.page_ui(), value="home"),
    ui.nav_panel("Population & rate", population.page_ui("population"), value="population"),
    ui.nav_panel("Admissions, discharges & violations", flows.page_ui("flows"), value="flows"),
    ui.nav_panel("Intake demographics & disparities", intakes.page_ui("intakes"), value="intakes"),
    ui.nav_spacer(),
    ui.nav_control(ui.a("Source: AOIC aggregate data", class_="nav-link text-muted small",
                        href="https://sites.google.com/probation.illinoiscourts.gov/aggregatedata/data-home",
                        target="_blank")),
    title="Illinois Juvenile Probation",
    id="nav",
    navbar_options=ui.navbar_options(bg=viz.NAVY, theme="dark", underline=False),
    header=[ui.tags.script(src="/plotly/plotly.min.js"), ui.tags.style(CSS), ui.tags.script(JS),
            ui.tags.script(viz.SORTABLE_JS)],
    fillable=False,
)


def server(input, output, session):
    home.page_server(input, "nav")
    population.page_server("population")
    flows.page_server("flows")
    intakes.page_server("intakes")


# plotly.min.js is served from the installed plotly package, so no CDN is needed
app = App(app_ui, server, static_assets={"/plotly": viz.PLOTLY_JS_DIR})
