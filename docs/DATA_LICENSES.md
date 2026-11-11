# Ontology attribution, transformations, and access limits

License check date: 11 November 2026. The software's Apache-2.0 license does **not** relicense upstream ontology content. The full original OWL distributions and model weights are not included.

The benchmark contains derived material: a root-only OWL 2 EL projection, selected bounded contexts and queries, type-preserving full-IRI renaming, and annotation retention/removal/replacement. These are experimental presentations, **not official releases or corrections of the upstream ontologies**. The source projects do not endorse this benchmark. The original source version and hashes are retained in the frozen panel and build metadata.

## Attribution by source

| Source and credited project | Version recorded by this study | Upstream terms | Public distribution in this release |
|---|---|---|---|
| [Evidence and Conclusion Ontology, ECO project](https://obofoundry.org/ontology/eco.html) | `eco-v2026-07-10` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | Derived benchmark, mappings, and existing predictions |
| [Environment Ontology, ENVO project](https://obofoundry.org/ontology/envo.html) | `envo-frozen-a0b91906` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | Derived benchmark, mappings, and existing predictions |
| [Food Ontology, FoodOn Consortium](https://obofoundry.org/ontology/foodon.html) | `foodon-v2025-07-31` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Derived benchmark, mappings, and existing predictions |
| [Gene Ontology, Gene Ontology Consortium](https://obofoundry.org/ontology/go.html) | `go-frozen-6200169c` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Derived benchmark, mappings, and existing predictions |
| [Human Phenotype Ontology, Human Phenotype Ontology Consortium](https://obofoundry.org/ontology/hp.html) | `hp-v2026-06-23` | [Custom HPO terms](https://human-phenotype-ontology.github.io/license.html), also linked by the [release-specific LICENSE.md](https://github.com/obophenotype/human-phenotype-ontology/blob/v2026-06-23/LICENSE.md) | Numerical outcomes, descriptive summaries, and build/hash provenance only; derived model-visible data and raw/validated predictions withheld |
| [Mondo Disease Ontology, Mondo project / Monarch Initiative](https://obofoundry.org/ontology/mondo.html) | `mondo-v2026-07-06` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Derived benchmark, mappings, and existing predictions |
| [Ontology for Biomedical Investigations, OBI Consortium](https://obofoundry.org/ontology/obi.html) | `obi-v2026-07-27` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Derived benchmark, mappings, and existing predictions |
| [Sequence Ontology project](https://obofoundry.org/ontology/so.html) | `so-v2026-08-07` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Derived benchmark, mappings, and existing predictions |
| [Uberon project and contributors](https://obofoundry.org/ontology/uberon.html) | `uberon-v2026-06-23` | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | Derived benchmark, mappings, and existing predictions |

The source OWL headers available to the authors agree with the CC0/CC BY declarations above for the eight redistributed sources. Preserve attribution, source versions, and the transformation notice when reusing derived content. Any separately protected imported material retains its own rights; consult the upstream source projects rather than assuming a blanket software license. The release does not include HPO association databases, OMIM downloads, Orphanet downloads, patient records, or model weights.

## HPO: what is withheld and why

The HPO custom terms place integrity restrictions on changes to content and logical relationships. The [maintainer discussion](https://github.com/obophenotype/human-phenotype-ontology/issues/7252) explicitly distinguishes those terms from standard Creative Commons terms. This release does not assume those terms authorize public redistribution of renamed/annotation-modified benchmark contexts.

Until permission is clarified, the following remain local and are listed by path/hash in the public manifest:

- HP benchmark/context JSONL files, renaming mappings, and repeat-subset contexts;
- HP raw and validated prediction files, which may reproduce ontology-derived text;
- the original complete publication-evidence tarball, because it contains those files.

HP numerical model outcomes and descriptive summaries remain unchanged and public. There is no reduction of the article's nine-source results, replacement of HP, or rerun of any model. This is a distribution limitation, not a modification of the experiment. Permission would need to cover redistribution of the transformed research artifacts; the authors' own approval cannot substitute for the source rights holder's permission.

The study uses Human Phenotype Ontology version `hp-v2026-06-23`; see the [HPO project](https://www.human-phenotype-ontology.org/) and the manuscript's HPO references. No request has been sent to the HPO maintainers as part of this deposit, and no permission is asserted.

## Finding the exact upstream inputs

Use `configs/confirmatory_panel_v33.json` for source version labels, source-file SHA-256 values, canonical hashes, and dataset hashes. For hash-frozen GO and ENVO inputs, an unversioned current download is not sufficient evidence of the original bytes. The maintainers' ontology pages link their release repositories. The public derived contexts allow item-level inspection for eight sources without obtaining the full source OWL distributions.

## Other exclusions

Credentials, local environment files, virtual environments, caches, compiled dependency bundles, unrelated local-model inventories, device-identifier dumps, private manuscript drafts, internal review notes, and language-style references are not research-release contents. Exact included evidence files are unmodified; packaging notes and manifests are additions outside frozen research files.
