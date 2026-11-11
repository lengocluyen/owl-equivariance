# Figure-export provenance

The original scripts are at the repository root, beside the supplied `figures/` directory, to preserve their relative file paths:

- `generate_figures.py`: descriptive figure export from the archived primary outcome table and existing stability reports;
- `build_presentation_figures.py`: schematic examples and an exact-value presentation redraw using the stored `figures/figure_data/evaluation_ladder.csv`;
- `export_framework_svg.py`: vector PDF export of the editable framework SVG.

They were not run for the public deposit. Use the supplied PDF figures and CSV traces to inspect the article without scientific recomputation.

Optional exporter dependencies include NumPy, Matplotlib, ReportLab, and svglib as imported by the scripts. The vector exporters also need the named TrueType fonts; Arial font files are not redistributed here. `export_framework_svg.py` accepts a `--font-dir` argument for fonts obtained under the user's own license. Exporting a figure is not needed to install the core package or inspect archived results.

The scripts preserve historical labels such as “Figure 1” for the framework; it is Figure 2 in the revised manuscript. Figures 1-3 are schematic, not additional observations, and Figure 6 uses different metric populations rather than successive attrition stages.
