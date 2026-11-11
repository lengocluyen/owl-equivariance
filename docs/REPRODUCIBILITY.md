# Reproducibility and build notes

## Inspecting this release does not require another model run

Use the stored CSV/JSON summaries, the figure-value traces, and the evidence asset. `tools/verify_artifacts.py` checks file hashes only. The public package is incomplete for exact nine-source item-level inspection because the HPO-derived model-visible data and prediction files are withheld; see `DATA_LICENSES.md`.

## Source identity

The Python package, shell/R entry points, Java sources, and v3.3 configuration are copied from the downloaded research snapshot. `release/ARTIFACT_MANIFEST.json` records actual SHA-256 hashes and comparisons with both initial and continuation source-hash records where available. A mismatch is reported rather than silently relabeled as inference-time code. Python tests are copied from the author working tree; they are not asserted to have been frozen before collection. No unit test with statistical fitting was executed for the deposit.

## Installation and Java build, if needed later

The archived collection records Python 3.12.13 and OpenJDK 25.0.3. The project requires Python 3.11 or newer; its Maven POM targets Java 25. OWL API 4.1.3 and ELK 0.4.3 are pinned together. Maven 3.9.x was used in the project toolchain. Exact recorded Python package versions are retained under `results/v33/provenance/requirements.lock.txt` and the continuation runtime directory.

For a new environment, these are code-install/build commands, not requests to reproduce the collection:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[api]'
bash scripts/build_java.sh -DskipTests package
```

The build requires Java 25 and Maven already on `PATH`, or the script's `OWLEQ_JAVA_HOME`, `OWLEQ_MVN`, and `OWLEQ_M2` overrides. Dependencies and model weights are not vendored. The helper `bootstrap_toolchain.sh` may download tools and must be reviewed before use.

The frozen configurations retain the original inference, model, and proposed analysis settings. An end-to-end runner can contact LM Studio, load/unload models, create new predictions, and invoke excluded historical regressions. It is **not** a safe default for read-only inspection of this release. Any future inference or corrected statistical analysis is a separate study action, not something executed or required by this deposit.

## Upstream inputs

Complete source ontology distributions and model weights are not included. Source versions and hashes are in the frozen panel and build reports. Obtain upstream distributions using the linked maintainers' releases and compare hashes before claiming exact reproduction; a current unversioned download is not necessarily the original input. For HPO, obtain any necessary permission before distributing transformed artifacts. No access request has been sent to its maintainers by this deposit.

## Figure provenance

`generate_figures.py` is the original descriptive figure exporter. `build_presentation_figures.py` creates schematic examples and redraws Figure 6 using the stored `evaluation_ladder.csv`. `export_framework_svg.py` exports the framework graphic. The files remain beside `figures/`, as in the manuscript project, so their relative asset paths are retained. These scripts were not run for this upload. Their generated assets and stored values are supplied directly; they are not evidence that the experiment or statistics were rerun. Optional exporter dependencies and font requirements are described in `analysis/README.md`.
