package org.owleq;

import com.fasterxml.jackson.core.type.TypeReference;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.owleq.cli.BuildDatasetCommand;
import org.owleq.io.OntologyIO;
import org.owleq.model.Json;
import org.semanticweb.owlapi.model.OWLOntology;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.Map;

import static org.junit.Assert.*;

/** Checkpoint and build-report provenance for the optimized generator. */
public class BuildCheckpointTest {

    @Rule
    public TemporaryFolder temporary = new TemporaryFolder();

    @Test(timeout = 120000)
    public void successfulBuildLeavesCompleteAtomicCheckpointAndDiagnostics() throws Exception {
        Path root = temporary.newFolder("checkpoint-build").toPath();
        Path source = root.resolve("toy.ofn");
        Path dataset = root.resolve("benchmark.jsonl");
        Path report = root.resolve("build_report.json");
        Path checkpoint = root.resolve("checkpoint.json");
        Path mappings = root.resolve("mappings");

        OWLOntology ontology = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        OntologyIO.save(ontology, source);

        int code = new CommandLine(new BuildDatasetCommand()).execute(
                "--input", source.toString(),
                "--ontology-id", "checkpoint-toy",
                "--ontology-version", "test-v1",
                "--output", dataset.toString(),
                "--report", report.toString(),
                "--checkpoint", checkpoint.toString(),
                "--mappings-dir", mappings.toString(),
                "--positives", "2",
                "--negatives", "2",
                "--conditions", "C0",
                "--distractors", "2",
                "--max-context-axioms", "30",
                "--justification-call-budget", "64",
                "--seed", "17");

        assertEquals(0, code);
        assertTrue(dataset.toFile().isFile());
        assertTrue(report.toFile().isFile());
        assertTrue(checkpoint.toFile().isFile());

        Map<String, Object> checkpointJson = Json.MAPPER.readValue(
                checkpoint.toFile(), new TypeReference<Map<String, Object>>() { });
        assertEquals("COMPLETE", checkpointJson.get("status"));
        assertEquals("complete", checkpointJson.get("stage"));
        assertNotNull(checkpointJson.get("updated_at"));
        assertNotNull(checkpointJson.get("metrics"));

        Map<String, Object> reportJson = Json.MAPPER.readValue(
                report.toFile(), new TypeReference<Map<String, Object>>() { });
        assertEquals("QUICKXPLAIN", reportJson.get("justification_algorithm"));
        assertEquals("SEEDED_SHA256_BOTTOM_K", reportJson.get("candidate_sampling"));
        assertEquals(64, ((Number) reportJson.get(
                "justification_call_budget_per_candidate")).intValue());
        assertNotNull(reportJson.get("justification_reasoner_calls"));
        assertNotNull(reportJson.get("justification_budget_exhausted_candidates"));
    }
}
