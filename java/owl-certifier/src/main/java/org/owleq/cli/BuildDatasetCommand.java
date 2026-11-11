package org.owleq.cli;

import org.owleq.io.OntologyIO;
import org.owleq.model.BenchmarkItem;
import org.owleq.model.Json;
import org.owleq.profile.ElFragment;
import org.owleq.profile.ProfileChecker;
import org.owleq.query.ContextBuilder;
import org.owleq.query.DatasetBuilder;
import org.owleq.transform.Condition;
import org.owleq.transform.SignatureIsomorphism;
import org.semanticweb.owlapi.model.OWLOntology;
import picocli.CommandLine;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.Callable;

/** Generate a certified orbit benchmark from one ontology. */
@CommandLine.Command(name = "build-dataset",
        description = "Generate a certified orbit benchmark from one ontology.")
public final class BuildDatasetCommand implements Callable<Integer> {

    @CommandLine.Option(names = "--input", required = true)
    Path input;

    @CommandLine.Option(names = "--ontology-id", required = true)
    String ontologyId;

    @CommandLine.Option(names = "--ontology-version", defaultValue = "unversioned")
    String ontologyVersion;

    @CommandLine.Option(names = "--output", required = true, description = "Benchmark JSONL.")
    Path output;

    @CommandLine.Option(names = "--report", description = "Build report JSON.")
    Path reportPath;

    @CommandLine.Option(names = "--checkpoint",
            description = "Mutable atomic progress JSON. Defaults beside --report or --output.")
    Path checkpointPath;

    @CommandLine.Option(names = "--positives", defaultValue = "50")
    int positives;

    @CommandLine.Option(names = "--negatives", defaultValue = "50")
    int negatives;

    @CommandLine.Option(names = "--instance-queries", defaultValue = "0")
    int instanceQueries;

    @CommandLine.Option(names = "--distractors", defaultValue = "10")
    int distractors;

    @CommandLine.Option(names = "--distractor-kind", defaultValue = "NEIGHBOURHOOD")
    ContextBuilder.DistractorKind distractorKind;

    @CommandLine.Option(names = "--max-context-axioms", defaultValue = "60")
    int maxContextAxioms;

    @CommandLine.Option(names = "--justification-call-budget", defaultValue = "256",
            description = "Maximum new ELK classifications per candidate justification.")
    int justificationCallBudget;

    @CommandLine.Option(names = "--seed", defaultValue = "42")
    long seed;

    @CommandLine.Option(names = "--split", defaultValue = "test")
    String split;

    @CommandLine.Option(names = "--conditions", split = ",",
            description = "Condition ids, e.g. C0,C1,C4,C4S2,C7,C8. Default: minimal pilot.")
    List<String> conditions;

    @CommandLine.Option(names = "--root-only")
    boolean rootOnly;

    @CommandLine.Option(names = "--mappings-dir",
            description = "Where to write one mapping manifest per condition. "
                    + "Defaults to <output-dir>/mappings.")
    Path mappingsDir;

    @CommandLine.Option(names = "--el-fragment",
            description = "Drop axioms outside OWL 2 EL so ELK is a sound oracle.")
    boolean elFragment;

    private BuildCheckpoint checkpoint;
    private Path resolvedCheckpointPath;

    @Override
    public Integer call() throws Exception {
        if (justificationCallBudget < 1) {
            throw new CommandLine.ParameterException(new CommandLine(this),
                    "--justification-call-budget must be at least 1");
        }
        initializeCheckpoint();
        try {
            return executeBuild();
        } catch (Exception e) {
            markFailed("exception", e.getClass().getSimpleName() + ": " + e.getMessage());
            throw e;
        }
    }

    private Integer executeBuild() throws Exception {
        progress("ontology_load:start");
        OWLOntology ontology = rootOnly
                ? OntologyIO.loadRootOnly(input)
                : OntologyIO.load(input);
        progress("ontology_load:complete");

        String fragmentNote = null;
        if (elFragment) {
            progress("el_fragment:start");
            ElFragment.Result fragment = ElFragment.extract(ontology);
            System.out.printf("EL fragment: removed %d of %d logical axioms (%.2f%% retained)%n",
                    fragment.removedAxioms, fragment.originalLogicalAxioms,
                    100.0 * fragment.retainedFraction());
            fragment.removedByType.forEach((key, value) ->
                    System.out.printf("  dropped %-28s %d%n", key, value));
            if (!fragment.inProfile) {
                String error = "could not reduce the ontology to OWL 2 EL";
                System.err.println("ERROR: " + error + "; ELK would not be a sound oracle.");
                markFailed("el_fragment:failed", error);
                return 2;
            }
            ontology = fragment.ontology;
            fragmentNote = String.format("EL fragment: %d of %d logical axioms removed",
                    fragment.removedAxioms, fragment.originalLogicalAxioms);
            progress("el_fragment:complete");
        }

        // This is the first stage at which the failed Uberon attempts went silent. Record the
        // boundary before classification so an external SIGKILL still leaves a useful artifact.
        progress("profile_and_consistency:start");
        ProfileChecker.Stats stats = ProfileChecker.inspect(ontology, true);
        progress("profile_and_consistency:complete");
        if (!"OWL2_EL".equals(stats.profile)) {
            String error = "ontology is " + stats.profile + ", not OWL 2 EL";
            System.err.println("ERROR: " + error + "; re-run with --el-fragment.");
            markFailed("profile_and_consistency:failed", error);
            return 2;
        }
        if (!stats.consistent) {
            String error = "ontology is inconsistent; every query would be entailed";
            System.err.println("ERROR: " + error + ".");
            markFailed("profile_and_consistency:failed", error);
            return 2;
        }

        DatasetBuilder.Config config = new DatasetBuilder.Config();
        config.ontologyId = ontologyId;
        config.ontologyVersion = ontologyVersion;
        config.profile = stats.profile;
        config.positives = positives;
        config.negatives = negatives;
        config.instanceQueries = instanceQueries;
        config.distractors = distractors;
        config.distractorKind = distractorKind;
        config.maxContextAxioms = maxContextAxioms;
        config.justificationCallBudget = justificationCallBudget;
        config.seed = seed;
        config.split = split;
        config.sourceFileSha256 = OntologyIO.sha256File(input);
        config.progress = this::progress;
        if (conditions != null && !conditions.isEmpty()) {
            config.conditions = conditions;
        }

        progress("dataset_builder:start");
        DatasetBuilder builder = new DatasetBuilder(ontology, config);
        List<BenchmarkItem> items = builder.build();
        DatasetBuilder.Report report = builder.report();
        report.preprocessing = fragmentNote;
        progress("dataset_builder:complete");

        progress("artifact_write:start");
        Json.writeJsonlAtomic(output, items);

        Path mapDir = mappingsDir != null
                ? mappingsDir
                : output.toAbsolutePath().getParent().resolve("mappings");
        for (Map.Entry<String, SignatureIsomorphism> entry
                : builder.isomorphisms().entrySet()) {
            SignatureIsomorphism isomorphism = entry.getValue();
            Path file = mapDir.resolve(entry.getKey() + ".mapping.json");
            Map<String, Object> manifest = new LinkedHashMap<>();
            manifest.put("mapping_id", "map:" + ontologyId + ":" + entry.getKey());
            manifest.put("condition", entry.getKey());
            manifest.put("operator", isomorphism.operatorId());
            manifest.put("seed", isomorphism.seed());
            manifest.put("annotation_policy", isomorphism.annotationPolicy().name());
            manifest.put("target_namespace", isomorphism.targetNamespace());
            manifest.put("entity_count", isomorphism.size());
            manifest.put("certificate_type", "BY_CONSTRUCTION");
            manifest.put("source_file_sha256", config.sourceFileSha256);
            manifest.put("source_canonical_sha256", report.sourceCanonicalSha256);
            manifest.put("mapping", isomorphism.byTypeStrings());
            Json.writePrettyAtomic(file, manifest);
            report.mappingFiles.put(entry.getKey(),
                    mapDir.getFileName() + "/" + file.getFileName());
        }

        if (reportPath != null) {
            Json.writePrettyAtomic(reportPath, report);
        }
        progress("artifact_write:complete");

        printSummary(items, report, mapDir);
        if (!report.failures.isEmpty()) {
            System.err.println("FAILURES (first 10):");
            report.failures.stream().limit(10)
                    .forEach(failure -> System.err.println("  " + failure));
            markFailed("validation_failures", report.failures.size() + " failures");
            return 3;
        }

        checkpoint.metrics.put("base_items", report.baseItems);
        checkpoint.metrics.put("emitted", report.emitted);
        checkpoint.metrics.put("justification_reasoner_calls",
                report.justificationReasonerCalls);
        checkpoint.metrics.put("justification_budget_exhausted_candidates",
                report.justificationBudgetExhaustedCandidates);
        checkpoint.status = "COMPLETE";
        checkpoint.stage = "complete";
        writeCheckpoint();
        return 0;
    }

    private void printSummary(List<BenchmarkItem> items, DatasetBuilder.Report report,
                              Path mapDir) {
        System.out.printf("base items: %d%nemitted: %d%ndropped (unverified): %d%n"
                        + "dropped (uncertified context): %d%ndropped (empty context): %d%n",
                report.baseItems, report.emitted, report.droppedUnverified,
                report.droppedUncertified, report.droppedEmptyContext);
        report.byCondition.forEach((key, value) ->
                System.out.printf("  %-6s %d%n", key, value));
        long positive = items.stream().filter(item -> item.task.positive).count();
        System.out.printf("label balance: %d entailed / %d not entailed%n",
                positive, items.size() - positive);
        System.out.printf("context size  positives: n=%d min=%d max=%d mean=%.1f%n",
                report.positiveContexts.n, report.positiveContexts.min,
                report.positiveContexts.max, report.positiveContexts.mean);
        System.out.printf("context size  negatives: n=%d min=%d max=%d mean=%.1f%n",
                report.negativeContexts.n, report.negativeContexts.min,
                report.negativeContexts.max, report.negativeContexts.mean);
        System.out.printf("justification: algorithm=%s calls=%d reasoner_builds=%d "
                        + "cache_hits=%d budget_exhausted=%d%n",
                report.justificationAlgorithm, report.justificationReasonerCalls,
                report.justificationReasonerBuilds, report.justificationCacheHits,
                report.justificationBudgetExhaustedCandidates);
        System.out.printf("mappings written to %s%n", mapDir);
        System.out.printf("checkpoint written to %s%n", resolvedCheckpointPath);
    }

    private void initializeCheckpoint() throws IOException {
        if (checkpointPath != null) {
            resolvedCheckpointPath = checkpointPath;
        } else if (reportPath != null) {
            resolvedCheckpointPath = reportPath.toAbsolutePath().getParent()
                    .resolve("build_checkpoint.json");
        } else {
            resolvedCheckpointPath = output.toAbsolutePath().getParent()
                    .resolve("build_checkpoint.json");
        }
        checkpoint = new BuildCheckpoint();
        checkpoint.startedAt = Instant.now().toString();
        checkpoint.processId = ProcessHandle.current().pid();
        checkpoint.input = input.toString();
        checkpoint.output = output.toString();
        checkpoint.ontologyId = ontologyId;
        checkpoint.ontologyVersion = ontologyVersion;
        checkpoint.parameters.put("positives", positives);
        checkpoint.parameters.put("negatives", negatives);
        checkpoint.parameters.put("instance_queries", instanceQueries);
        checkpoint.parameters.put("conditions", conditions == null
                ? new ArrayList<>(Condition.minimalPilot()) : new ArrayList<>(conditions));
        checkpoint.parameters.put("seed", seed);
        checkpoint.parameters.put("root_only", rootOnly);
        checkpoint.parameters.put("el_fragment", elFragment);
        checkpoint.parameters.put("distractors", distractors);
        checkpoint.parameters.put("max_context_axioms", maxContextAxioms);
        checkpoint.parameters.put("justification_algorithm", "QUICKXPLAIN");
        checkpoint.parameters.put("candidate_sampling", "SEEDED_SHA256_BOTTOM_K");
        checkpoint.parameters.put("justification_call_budget", justificationCallBudget);
        checkpoint.status = "RUNNING";
        checkpoint.stage = "initialized";
        writeCheckpoint();
    }

    private void progress(String stage) {
        System.out.printf("progress: %s time=%s%n", stage, Instant.now());
        checkpoint.status = "RUNNING";
        checkpoint.stage = stage;
        try {
            writeCheckpoint();
        } catch (IOException e) {
            throw new UncheckedIOException("could not update build checkpoint", e);
        }
    }

    private void markFailed(String stage, String error) {
        if (checkpoint == null) {
            return;
        }
        checkpoint.status = "FAILED";
        checkpoint.stage = stage;
        checkpoint.error = error;
        try {
            writeCheckpoint();
        } catch (IOException checkpointError) {
            System.err.println("WARNING: could not write failed checkpoint: "
                    + checkpointError.getMessage());
        }
    }

    private void writeCheckpoint() throws IOException {
        checkpoint.updatedAt = Instant.now().toString();
        Json.writePrettyAtomic(resolvedCheckpointPath, checkpoint);
    }

    /** Mutable runtime provenance; it is not a scientific result or a resumable cache. */
    public static final class BuildCheckpoint {
        public int schemaVersion = 1;
        public String status;
        public String stage;
        public String startedAt;
        public String updatedAt;
        public long processId;
        public String input;
        public String output;
        public String ontologyId;
        public String ontologyVersion;
        public Map<String, Object> parameters = new LinkedHashMap<>();
        public Map<String, Object> metrics = new LinkedHashMap<>();
        public String error;
    }
}
