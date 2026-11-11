package org.owleq.cli;

import org.owleq.io.ContextParser;
import org.owleq.io.OntologyIO;
import org.owleq.model.BenchmarkItem;
import org.owleq.model.Json;
import org.owleq.transform.AnnotationPolicy;
import org.owleq.transform.Condition;
import org.owleq.transform.SignatureIsomorphism;
import org.owleq.validation.OrbitValidator;
import org.semanticweb.owlapi.model.OWLAxiom;
import org.semanticweb.owlapi.model.OWLOntology;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.Callable;

/** {@code validate-orbit}: check label preservation, round trip and annotation isolation. */
@CommandLine.Command(name = "validate-orbit",
        description = "Verify that a condition preserves every query label and round-trips exactly.")
public final class ValidateOrbitCommand implements Callable<Integer> {

    @CommandLine.Option(names = "--source", required = true)
    Path source;

    @CommandLine.Option(names = "--condition", required = true)
    String condition;

    @CommandLine.Option(names = "--queries",
            description = "Benchmark JSONL whose C0 queries are re-checked under the condition.")
    Path queries;

    @CommandLine.Option(names = "--sample", defaultValue = "200",
            description = "Extra inferred subsumptions to spot-check beyond the benchmark.")
    int sample;

    @CommandLine.Option(names = "--report", required = true)
    Path report;

    @CommandLine.Option(names = "--seed", defaultValue = "42")
    long seed;

    @CommandLine.Option(names = "--root-only")
    boolean rootOnly;

    @Override
    public Integer call() throws Exception {
        OWLOntology o = rootOnly ? OntologyIO.loadRootOnly(source) : OntologyIO.load(source);
        Condition c = Condition.of(condition);
        SignatureIsomorphism iso = c.isomorphism(o, "urn:owleq:");

        List<OWLAxiom> qs = new ArrayList<>();
        if (queries != null) {
            for (BenchmarkItem item : Json.readJsonl(queries, BenchmarkItem.class)) {
                // Queries are re-checked in the source vocabulary, so only the untransformed
                // condition is read; every other orbit member is its image under some pi.
                if ("C0".equals(item.transform.lexicalCondition)) {
                    qs.add(ContextParser.parseAxiom(item.task.queryFunctional));
                }
            }
        }

        boolean annotationOnly = "none".equals(c.operator)
                && c.annotationPolicy != AnnotationPolicy.KEEP_ALL;
        OrbitValidator.Result r = new OrbitValidator(o, iso)
                .validate(qs, sample, annotationOnly, seed);
        Json.writePretty(report, r);

        System.out.printf("condition %s: queries %d (%d mismatches), sampled %d (%d mismatches), "
                        + "round-trip %s, axiom count preserved %s%n",
                c.id, r.queriesChecked, r.queryMismatches, r.sampledChecked, r.sampledMismatches,
                r.roundTripExact, r.logicalAxiomCountPreserved);
        if (!r.ok()) {
            r.failures.stream().limit(10).forEach(f -> System.err.println("  " + f));
            return 3;
        }
        System.out.println("OK: preservation holds on every check.");
        return 0;
    }
}
