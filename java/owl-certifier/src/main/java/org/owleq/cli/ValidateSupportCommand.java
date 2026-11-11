package org.owleq.cli;

import com.fasterxml.jackson.databind.JsonNode;
import org.owleq.model.BenchmarkItem;
import org.owleq.model.Json;
import org.owleq.proof.SupportValidator;
import picocli.CommandLine;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.Callable;

/**
 * {@code validate-support}: symbolically check the axiom sets a model cited (spec section 33.5).
 *
 * <p>Reads model predictions, resolves each cited context id back to an axiom, and asks the
 * reasoner whether those axioms alone entail the query. Produces the fields the Python layer
 * needs for the proof-level metrics, above all the correct-answer-invalid-proof rate.
 */
@CommandLine.Command(name = "validate-support",
        description = "Deletion-based validation of model-selected proof support.")
public final class ValidateSupportCommand implements Callable<Integer> {

    @CommandLine.Option(names = "--dataset", required = true, description = "Benchmark JSONL.")
    Path dataset;

    @CommandLine.Option(names = "--predictions", required = true,
            description = "Predictions JSONL with orbit_item_id, label, support_axiom_ids.")
    Path predictions;

    @CommandLine.Option(names = "--output", required = true)
    Path output;

    @CommandLine.Option(names = "--limit", defaultValue = "0",
            description = "Validate at most N predictions (0 = all).")
    int limit;

    @Override
    public Integer call() throws Exception {
        Map<String, BenchmarkItem> byId = new HashMap<>();
        for (BenchmarkItem item : Json.readJsonl(dataset, BenchmarkItem.class)) {
            byId.put(item.orbitItemId, item);
        }

        SupportValidator validator = new SupportValidator();
        int validated = 0;
        int validSupport = 0;
        int correctAnswerInvalidProof = 0;
        int missingItems = 0;

        Files.createDirectories(output.toAbsolutePath().getParent());
        try (BufferedReader r = Files.newBufferedReader(predictions, StandardCharsets.UTF_8);
             BufferedWriter w = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
            String line;
            while ((line = r.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                if (limit > 0 && validated >= limit) {
                    break;
                }
                JsonNode pred = Json.MAPPER.readTree(line);
                String id = pred.path("orbit_item_id").asText(null);
                BenchmarkItem item = byId.get(id);
                if (item == null) {
                    missingItems++;
                    continue;
                }

                List<String> cited = new ArrayList<>();
                for (JsonNode n : pred.path("support_axiom_ids")) {
                    cited.add(n.asText());
                }

                SupportValidator.Result res = validator.validate(item, cited);
                validated++;
                if (res.supportValid) {
                    validSupport++;
                }

                boolean answerCorrect = item.task.label.equals(pred.path("label").asText(null));
                // Only entailed items can have a valid proof, so the metric is defined over
                // positives; on a non-entailed item the correct behaviour is an empty support set.
                if (answerCorrect && item.task.positive && !res.supportValid) {
                    correctAnswerInvalidProof++;
                }

                com.fasterxml.jackson.databind.node.ObjectNode out = pred.deepCopy();
                out.put("answer_correct", answerCorrect);
                out.put("support_valid", res.supportValid);
                out.put("support_minimal", res.supportMinimal);
                out.set("resolved_support_ids", Json.MAPPER.valueToTree(res.resolvedIds));
                out.set("unknown_support_ids", Json.MAPPER.valueToTree(res.unknownIds));
                out.set("redundant_support_ids", Json.MAPPER.valueToTree(res.redundantIds));
                if (res.note != null) {
                    out.put("support_note", res.note);
                }
                w.write(Json.MAPPER.writeValueAsString(out));
                w.write("\n");
            }
        }

        System.out.printf("validated %d predictions%n", validated);
        System.out.printf("  valid support:                %d (%.1f%%)%n",
                validSupport, pct(validSupport, validated));
        System.out.printf("  correct answer, invalid proof: %d (%.1f%% of validated)%n",
                correctAnswerInvalidProof, pct(correctAnswerInvalidProof, validated));
        if (missingItems > 0) {
            System.out.printf("  WARNING: %d predictions had no matching dataset item%n", missingItems);
        }
        return 0;
    }

    private static double pct(int n, int d) {
        return d == 0 ? 0.0 : 100.0 * n / d;
    }
}
