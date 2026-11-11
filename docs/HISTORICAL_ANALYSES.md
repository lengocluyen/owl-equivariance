# Excluded historical analyses

The article excludes the archived GLMM and GEE results, adjusted contrasts, significance tests, and variance estimates. An audit found that the exported token-reference dictionary was keyed by base-item ID without model identity. A model's C0 token count could therefore be overwritten by another model's reference. The historical `token_delta` does not consistently implement within-model change from C0.

This affects the interpretation of fitted models using that covariate, not the existence of the archived model responses. The descriptive answer/family/support/repeat values reported in the article do not use that adjustment and were retained without new calculations.

The release keeps historical files unchanged for inspection. In particular, treat the following as **excluded evidence**, not corrected or validated statistical findings:

- `reports/<run>/confirmatory_glmm/`
- `reports/<run>/pooled_correctness_interaction_model/`
- `reports/<run>/pooled_response_validity_interaction_model/`
- Other fitted-model outputs, adjusted contrasts, and inferential reports anywhere in the frozen reports
- The historical `primary_analysis.model-recipe.txt` and analysis recipes in the original experiment manifest

`scripts/analyze_confirmatory_v33.R`, model-fitting CLI paths, and end-to-end collection runners are supplied for traceability. Do not run them merely to inspect the evidence, or assume that their presence means the analysis defect has been corrected. No corrected model, new experiment, bootstrap, or replacement uncertainty estimate was run for this release.

The reporting change was post-outcome. Original plan and run identifiers are retained, not rewritten to make the descriptive analysis appear prospectively specified. The threshold failures and continuation records remain part of the public provenance.
