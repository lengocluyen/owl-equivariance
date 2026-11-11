package org.owleq.validation;

import org.owleq.io.OntologyIO;
import org.owleq.reasoner.ReasonerService;
import org.owleq.transform.SignatureIsomorphism;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Software checks that a transform behaved as its construction says it must (spec section 14).
 *
 * <p>These are tests, not the proof. Entailment preservation under a typed signature isomorphism
 * follows from the semantics and holds for every ontology and every query; the reasoner runs here
 * exist to catch implementation defects -- a missed constructor, a mishandled pun, an annotation
 * that leaked into the logical axiom set. A failure means the code is wrong, never that the
 * theorem is.
 */
public final class OrbitValidator {

    public static final class Result {
        public boolean sourceConsistent;
        public boolean targetConsistent;
        public int queriesChecked;
        public int queryMismatches;
        public int sampledChecked;
        public int sampledMismatches;
        public boolean roundTripExact;
        public boolean logicalAxiomCountPreserved;
        public boolean annotationIsolationHolds;
        public final List<String> failures = new ArrayList<>();

        public boolean ok() {
            return sourceConsistent && targetConsistent
                    && queryMismatches == 0 && sampledMismatches == 0
                    && roundTripExact && logicalAxiomCountPreserved;
        }
    }

    private final OWLOntology source;
    private final SignatureIsomorphism iso;

    public OrbitValidator(OWLOntology source, SignatureIsomorphism iso) {
        this.source = source;
        this.iso = iso;
    }

    /**
     * @param queries        the benchmark queries, in the source vocabulary
     * @param sampleSize     extra inferred subsumptions to spot-check beyond the benchmark
     *                       (spec section 14.3)
     * @param annotationOnly true when the condition must not touch logical axioms at all
     */
    public Result validate(List<OWLAxiom> queries, int sampleSize, boolean annotationOnly,
                           long seed) throws OWLOntologyCreationException {
        Result r = new Result();
        OWLOntology target = iso.apply(source);

        try (ReasonerService src = new ReasonerService(source);
             ReasonerService tgt = new ReasonerService(target)) {

            r.sourceConsistent = src.isConsistent();
            r.targetConsistent = tgt.isConsistent();

            for (OWLAxiom q : queries) {
                r.queriesChecked++;
                boolean a = src.isEntailed(q);
                boolean b = tgt.isEntailed(iso.transform(q));
                if (a != b) {
                    r.queryMismatches++;
                    r.failures.add("query label changed: " + OntologyIO.renderAxiom(q)
                            + " source=" + a + " target=" + b);
                }
            }

            // Spot-check beyond the benchmark: entailments the dataset never asks about are
            // where a constructor-handling bug would otherwise hide.
            List<OWLSubClassOfAxiom> inferred = src.inferredSubsumptions();
            Collections.shuffle(inferred, new Random(seed));
            for (OWLSubClassOfAxiom ax : inferred.subList(0, Math.min(sampleSize, inferred.size()))) {
                if (ax.getSuperClass().isOWLThing() || ax.getSubClass().isOWLNothing()) {
                    continue;
                }
                r.sampledChecked++;
                if (!tgt.isEntailed(iso.transform(ax))) {
                    r.sampledMismatches++;
                    r.failures.add("sampled entailment lost: " + OntologyIO.renderAxiom(ax));
                }
            }
        }

        r.logicalAxiomCountPreserved =
                source.getLogicalAxiomCount() == target.getLogicalAxiomCount();
        if (!r.logicalAxiomCountPreserved) {
            r.failures.add("logical axiom count " + source.getLogicalAxiomCount()
                    + " -> " + target.getLogicalAxiomCount());
        }

        r.roundTripExact = roundTrip(target);
        if (!r.roundTripExact) {
            r.failures.add("inverse(transform(O)) != O on the logical axiom set");
        }

        if (annotationOnly) {
            r.annotationIsolationHolds = OntologyIO.canonicalLogicalText(source)
                    .equals(OntologyIO.canonicalLogicalText(target));
            if (!r.annotationIsolationHolds) {
                r.failures.add("annotation-only condition modified logical axioms");
            }
        }
        return r;
    }

    /** inverse(transform(O)) must equal O on logical axioms, modulo serialization. */
    private boolean roundTrip(OWLOntology target) throws OWLOntologyCreationException {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        Set<OWLAxiom> back = target.getLogicalAxioms().stream()
                .map(iso::inverse)
                .collect(Collectors.toSet());
        OWLOntology restored = m.createOntology(back);
        return OntologyIO.canonicalLogicalText(restored)
                .equals(OntologyIO.canonicalLogicalText(source));
    }
}
