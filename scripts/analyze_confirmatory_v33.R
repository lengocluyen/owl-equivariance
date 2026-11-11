#!/usr/bin/env Rscript

# Preregistered v3.3 confirmatory GLMM.
#
# Usage:
#   Rscript scripts/analyze_confirmatory_v33.R \
#     reports/<run>/primary_analysis.csv reports/<run>/confirmatory_glmm
#
# This script deliberately uses only base R plus lme4.  It fits crossed random intercepts
# for ontology and base item nested within ontology.  The Python GEE and variational Bayes
# fits remain sensitivity analyses; this Laplace GLMM is the primary confirmatory model.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("usage: analyze_confirmatory_v33.R ANALYSIS.csv OUTPUT_DIR")
}
if (!requireNamespace("lme4", quietly = TRUE)) {
  stop("R package 'lme4' is required; on Ubuntu install r-cran-lme4")
}

analysis_path <- args[[1]]
output_root <- args[[2]]
dir.create(output_root, recursive = TRUE, showWarnings = FALSE)
d <- read.csv(analysis_path, stringsAsFactors = FALSE, check.names = FALSE)

required <- c(
  "correct", "parsed", "condition", "model", "ontology_id", "base_item_id",
  "task_type", "proof_depth", "context_axioms", "token_delta"
)
missing <- setdiff(required, names(d))
if (length(missing) > 0) {
  stop(sprintf("analysis table is missing required columns: %s", paste(missing, collapse = ", ")))
}
if (length(unique(d$ontology_id)) < 8) {
  stop("v3.3 primary GLMM requires at least eight ontology sources")
}
d$item_cluster <- interaction(d$ontology_id, d$base_item_id, drop = TRUE, sep = "::")
if (length(unique(d$item_cluster)) < 1320) {
  stop("v3.3 primary GLMM requires at least 1,320 base-item clusters")
}
d$condition <- stats::relevel(factor(d$condition), ref = "C0")
d$model <- factor(d$model)
d$ontology_id <- factor(d$ontology_id)
d$task_type <- factor(d$task_type)

safe_name <- function(x) gsub("[^A-Za-z0-9._-]+", "_", x)

write_fit <- function(frame, outcome, destination, pooled = FALSE) {
  dir.create(destination, recursive = TRUE, showWarnings = FALSE)
  notes <- character()
  fixed <- c("condition")

  if (length(unique(frame$task_type[!is.na(frame$task_type)])) >= 2) {
    fixed <- c(fixed, "task_type")
  } else {
    notes <- c(notes, "task_type omitted: fewer than two observed levels")
  }

  for (column in c("proof_depth", "context_axioms", "token_delta")) {
    numeric_value <- suppressWarnings(as.numeric(frame[[column]]))
    if (sum(!is.na(numeric_value)) > 0 && length(unique(numeric_value[!is.na(numeric_value)])) >= 2) {
      scaled_name <- paste0(column, "_z")
      frame[[scaled_name]] <- as.numeric(scale(numeric_value))
      fixed <- c(fixed, scaled_name)
    } else {
      notes <- c(notes, sprintf("%s omitted: missing or constant", column))
    }
  }

  if (pooled) {
    if (length(unique(frame$model)) < 2) stop("pooled GLMM requires at least two models")
    fixed <- c(fixed, "model", "condition:model")
  }

  needed <- unique(c(outcome, "ontology_id", "item_cluster", fixed))
  # Interaction expressions are not column names.
  needed <- setdiff(needed, "condition:model")
  frame <- frame[stats::complete.cases(frame[, needed, drop = FALSE]), , drop = FALSE]
  if (nrow(frame) == 0) stop(sprintf("no complete rows remain for %s", outcome))

  observed <- unique(frame[[outcome]])
  if (length(observed) < 2) {
    writeLines(
      c(
        "fit_status=CONSTANT_OUTCOME",
        sprintf("outcome=%s", outcome),
        sprintf("observed=%s", paste(observed, collapse = ",")),
        notes
      ),
      file.path(destination, "model_status.txt")
    )
    return(invisible(NULL))
  }

  formula_text <- paste0(
    outcome, " ~ ", paste(fixed, collapse = " + "),
    " + (1 | ontology_id) + (1 | item_cluster)"
  )
  formula <- stats::as.formula(formula_text)
  fit <- lme4::glmer(
    formula,
    data = frame,
    family = stats::binomial(link = "logit"),
    nAGQ = 1,
    control = lme4::glmerControl(
      optimizer = "bobyqa",
      optCtrl = list(maxfun = 200000),
      check.conv.singular = "ignore"
    )
  )

  table <- as.data.frame(summary(fit)$coefficients)
  table$term <- rownames(table)
  rownames(table) <- NULL
  names(table)[1:4] <- c("coefficient", "std_error", "z", "p_value")
  table$odds_ratio <- exp(table$coefficient)
  table$ci_low <- table$coefficient - 1.96 * table$std_error
  table$ci_high <- table$coefficient + 1.96 * table$std_error
  table$p_value_holm <- NA_real_
  condition_rows <- grepl("^condition", table$term) & !grepl(":", table$term)
  if (any(condition_rows)) {
    table$p_value_holm[condition_rows] <- stats::p.adjust(
      table$p_value[condition_rows], method = "holm"
    )
  }
  table <- table[, c(
    "term", "coefficient", "odds_ratio", "std_error", "z", "p_value",
    "p_value_holm", "ci_low", "ci_high"
  )]
  utils::write.csv(table, file.path(destination, "model_coefficients.csv"), row.names = FALSE)
  utils::write.csv(
    as.data.frame(lme4::VarCorr(fit)),
    file.path(destination, "random_effect_variances.csv"),
    row.names = FALSE
  )
  capture.output(summary(fit), file = file.path(destination, "model_summary.txt"))
  saveRDS(fit, file.path(destination, "model_fit.rds"))

  convergence <- fit@optinfo$conv$lme4$messages
  status <- c(
    "fit_status=FIT",
    sprintf("outcome=%s", outcome),
    sprintf("formula=%s", formula_text),
    sprintf("observations=%d", nrow(frame)),
    sprintf("base_item_clusters=%d", length(unique(frame$item_cluster))),
    sprintf("ontology_clusters=%d", length(unique(frame$ontology_id))),
    sprintf("singular=%s", lme4::isSingular(fit, tol = 1e-4)),
    sprintf("convergence_messages=%s", paste(convergence, collapse = " | ")),
    notes
  )
  writeLines(status, file.path(destination, "model_status.txt"))
}

models <- sort(unique(d$model))
for (model_name in models) {
  frame <- d[d$model == model_name, , drop = FALSE]
  root <- file.path(output_root, "models", safe_name(model_name))
  write_fit(frame, "correct", file.path(root, "correctness"), pooled = FALSE)
  write_fit(frame, "parsed", file.path(root, "response_validity"), pooled = FALSE)
}
write_fit(d, "correct", file.path(output_root, "pooled_correctness_interaction"), pooled = TRUE)
write_fit(d, "parsed", file.path(output_root, "pooled_response_validity_interaction"), pooled = TRUE)

writeLines(
  c(
    "protocol_id=owleq-jws-2026-08-v33",
    "estimator=lme4::glmer",
    "integration=Laplace (nAGQ=1)",
    "random_intercepts=ontology_id,ontology_id:base_item_id",
    "multiplicity=Holm within condition-vs-C0 fixed-effect family",
    "confirmatory post-hoc power calculation=forbidden"
  ),
  file.path(output_root, "analysis_provenance.txt")
)
