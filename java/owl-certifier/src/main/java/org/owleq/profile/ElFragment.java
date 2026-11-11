package org.owleq.profile;

import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.OWL2ELProfile;
import org.semanticweb.owlapi.profiles.OWLProfileReport;
import org.semanticweb.owlapi.profiles.OWLProfileViolation;

import java.util.*;

/**
 * Extract the OWL 2 EL fragment of an ontology by removing the axioms that violate the
 * profile (spec section 9.3, "reject or isolate profile violations").
 *
 * <p>Needed because most published ontologies miss EL by a handful of axioms -- one
 * {@code InverseObjectProperties}, a nominal with several individuals -- while being EL
 * everywhere else. Rejecting them outright would restrict the study to one ontology and
 * make cross-domain claims impossible; using them whole with ELK would be worse, because
 * ELK is not complete outside EL and would return unsound labels with no error.
 *
 * <p><b>What this does and does not claim.</b> The result is a different ontology, not a
 * view of the original: dropping axioms removes entailments. Every claim the benchmark
 * makes is about the fragment, which is the ontology actually shipped, hashed and reasoned
 * over. The count and types of dropped axioms are reported so the distance from the
 * published artifact is visible rather than buried.
 */
public final class ElFragment {

    private ElFragment() {
    }

    public static final class Result {
        public final OWLOntology ontology;
        public final int removedAxioms;
        public final int originalLogicalAxioms;
        public final Map<String, Integer> removedByType;
        public final boolean inProfile;

        Result(OWLOntology ontology, int removed, int original,
               Map<String, Integer> removedByType, boolean inProfile) {
            this.ontology = ontology;
            this.removedAxioms = removed;
            this.originalLogicalAxioms = original;
            this.removedByType = removedByType;
            this.inProfile = inProfile;
        }

        public double retainedFraction() {
            return originalLogicalAxioms == 0
                    ? 1.0
                    : (double) (originalLogicalAxioms - removedAxioms) / originalLogicalAxioms;
        }
    }

    /**
     * Iteratively drop violating axioms until the ontology is in OWL 2 EL.
     *
     * <p>Iteration is required: removing one axiom can change which others the profile
     * checker reports, so a single pass is not guaranteed to converge.
     */
    public static Result extract(OWLOntology source) throws OWLOntologyCreationException {
        int original = source.getLogicalAxiomCount();
        Set<OWLAxiom> axioms = new HashSet<>(source.getAxioms());
        Map<String, Integer> removedByType = new TreeMap<>();
        int removed = 0;

        // OWLAPI 4.1.3 returns Guava's Optional here, which has `or` rather than `orElse`.
        IRI iri = source.getOntologyID().getOntologyIRI().isPresent()
                ? source.getOntologyID().getOntologyIRI().get()
                : IRI.create("urn:owleq:el-fragment");

        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology current = manager.createOntology(axioms, iri);

        for (int pass = 0; pass < 16; pass++) {
            OWLProfileReport report = new OWL2ELProfile().checkOntology(current);
            if (report.isInProfile()) {
                return new Result(current, removed, original, removedByType, true);
            }

            Set<OWLAxiom> offending = new HashSet<>();
            for (OWLProfileViolation violation : report.getViolations()) {
                OWLAxiom axiom = violation.getAxiom();
                if (axiom != null && axioms.contains(axiom)) {
                    offending.add(axiom);
                }
            }
            if (offending.isEmpty()) {
                // Violations the checker cannot attribute to a removable axiom (typically
                // declaration-level). Report honestly rather than looping forever.
                return new Result(current, removed, original, removedByType, false);
            }

            for (OWLAxiom axiom : offending) {
                if (axiom.isLogicalAxiom()) {
                    removed++;
                    removedByType.merge(axiom.getAxiomType().getName(), 1, Integer::sum);
                }
            }
            axioms.removeAll(offending);
            manager = OWLManager.createOWLOntologyManager();
            current = manager.createOntology(axioms, iri);
        }
        return new Result(current, removed, original, removedByType, false);
    }
}
