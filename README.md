# owl-equivariance

Research code and existing results for **Evaluating the Semantic Consistency of Large Language Models for OWL Reasoning**, by Le Ngoc Luyen and Marie-Hélène Abel.

The study evaluates answer correctness, agreement across equivalent OWL presentations, and the logical sufficiency of model-cited axioms. Its completed collection contains 1,460 balanced base problems from nine ontology sources, eleven conditions, and six open-weight models: 96,360 primary responses and 38,544 additional repeat responses.

## Access the evidence

- [Versioned research release](https://github.com/lengocluyen/owl-equivariance/releases/tag/v33-evidence-2026-11-11): compressed evidence bundle and SHA-256 checksum.
- [`results/v33/`](results/v33/): existing descriptive summaries, repeat summaries, panel freeze, model-artifact hashes, environment records, and continuation provenance.
- [`figures/figure_data/`](figures/figure_data/): unchanged plotted values used in the manuscript.
- [`release/ARTIFACT_MANIFEST.json`](release/ARTIFACT_MANIFEST.json): file-level hashes, source-snapshot comparisons, and the explicit omissions list.
- [`docs/RESULTS_GUIDE.md`](docs/RESULTS_GUIDE.md): how to read the stored outputs without running another experiment.

The release preserves included evidence files byte-for-byte. It is a public packaging of an already completed collection, not a new experiment, a retroactive preregistration, or an independently reproduced analysis.

### HPO redistribution limitation

**HP-derived benchmark contexts, mappings, repeat-context files, and raw/validated prediction files are withheld pending clarification of redistribution permission under the custom HPO terms.** HP numerical outcome tables, descriptive summaries, hashes, and construction provenance remain available. The full nine-source data are therefore **not** claimed to be publicly redistributed. The release includes model-visible benchmark data and predictions for the other eight sources. See [data attribution and access](docs/DATA_LICENSES.md).

## Reporting boundaries

- This article reports descriptive findings on the fixed panel, not statistically established model superiority.
- The archived GLMM/GEE regressions and adjusted-effect outputs are **excluded evidence**, because the token-change reference export was not consistently keyed by model. The unmodified `primary_analysis.csv` retains the historical `token_delta` column; it must not be treated as a valid model-specific adjustment.
- `proof_depth` is the size of a selected subset-minimal justification, not derivation depth. Negative items use the matched positive's value as a construction proxy.
- The response-validity threshold failures and post-failure continuation remain disclosed. The historical run identifier contains `confirmatory`; that name is not a claim of unqualified confirmatory success.
- Consistency may include invalid-label agreement. Support validity, support overlap, all-condition correctness, and repeat accuracy use different populations; consult [metric definitions](docs/RESULTS_GUIDE.md).

Historical analysis scripts and outputs are retained for traceability, not endorsed as corrected results. **Do not run a full inference or statistical runner merely to inspect this release.** See [excluded historical analyses](docs/HISTORICAL_ANALYSES.md).

## Code layout

| Location | Purpose |
|---|---|
| `src/owl_equivariance/` | Input rendering, model adapters, parsing, metric definitions, and collection provenance |
| `java/owl-certifier/` | OWL API/ELK certification, bounded context construction, renaming, and support validation |
| `scripts/` | Archived build, collection, continuation, and analysis entry points |
| `configs/` | Original v3.3 manifest, model matrix, and exact frozen panel |
| `generate_figures.py`, `build_presentation_figures.py`, `export_framework_svg.py` | Existing figure-generation/export scripts; not executed for this deposit |
| `tests/` | Author working-tree Python unit tests, supplied separately from inference-time provenance |
| `docs/historical/` | Earlier protocol/design documents; some terminology and plans are superseded by the reporting notes above |

Code is copied from the downloaded research snapshot. The artifact manifest records whether each supplied source file matches the initial and/or continuation source hash. It does not assume that a later wrapper was the exact wrapper present before continuation. Older configuration files needed by the supplied tests come from the author working tree; only the v3.3 panel and manifest define this collection.

## Inspect without inference or statistics

Read the supplied CSV/JSON files directly. To download the large evidence asset:

```sh
gh release download v33-evidence-2026-11-11 \
  --repo lengocluyen/owl-equivariance \
  --pattern 'owleq-v33-public-evidence.tar.gz' --pattern 'SHA256SUMS'
sha256sum -c SHA256SUMS
```

Extract the verified archive in a new directory, then check its included frozen files:

```sh
mkdir evidence-v33
tar -xzf owleq-v33-public-evidence.tar.gz -C evidence-v33
python tools/verify_artifacts.py evidence-v33/release/ARTIFACT_MANIFEST.json --root evidence-v33
```

This verification hashes files only. It does not recalculate performance, fit a model, contact LM Studio, or regenerate predictions.

For code installation/build requirements and optional future reproduction, see [reproducibility notes](docs/REPRODUCIBILITY.md). Model weights and the complete upstream ontology distributions are not bundled. Code licensing does not replace upstream data or model terms.

## License and citation

The supplied project code retains the existing [Apache-2.0 license](LICENSE). Ontology-derived material remains subject to its upstream terms and attribution notices in [DATA_LICENSES.md](docs/DATA_LICENSES.md); it is not relicensed wholesale as Apache-2.0. No journal acceptance, manuscript DOI, or data DOI is asserted. See [`CITATION.cff`](CITATION.cff).
