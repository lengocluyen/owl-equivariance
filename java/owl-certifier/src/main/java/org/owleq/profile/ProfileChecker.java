package org.owleq.profile;

import org.owleq.io.OntologyIO;
import org.owleq.reasoner.ReasonerService;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Profile membership, size statistics and consistency for one ontology (spec section 9.3).
 *
 * <p>Profile matters operationally: ELK is complete for OWL 2 EL and nothing else, so an ontology
 * outside EL would silently produce unsound labels rather than an error. This check is the gate
 * that keeps such an ontology out of the pilot.
 */
public final class ProfileChecker {

    private ProfileChecker() {
    }

    public static final class Stats {
        public String ontologyIri;
        public String hash;
        public int logicalAxioms;
        public int totalAxioms;
        public int classes;
        public int objectProperties;
        public int dataProperties;
        public int individuals;
        public int annotationAssertions;
        public int importsCount;
        /** The most restrictive OWL 2 profile the ontology falls in, or NONE. */
        public String profile;
        public List<String> profileViolations = new ArrayList<>();
        public boolean consistent;
        public List<String> unsatisfiableClasses = new ArrayList<>();
        public Map<String, Integer> axiomTypeCounts = new TreeMap<>();
        public Map<String, Integer> lexicalChannelCounts = new TreeMap<>();
    }

    public static Stats inspect(OWLOntology o, boolean runReasoner) {
        Stats s = new Stats();
        s.ontologyIri = o.getOntologyID().getOntologyIRI().isPresent()
                ? o.getOntologyID().getOntologyIRI().get().toString() : "anonymous";
        s.hash = OntologyIO.ontologyHash(o);
        s.logicalAxioms = o.getLogicalAxiomCount();
        s.totalAxioms = o.getAxiomCount();
        s.classes = o.getClassesInSignature().size();
        s.objectProperties = o.getObjectPropertiesInSignature().size();
        s.dataProperties = o.getDataPropertiesInSignature().size();
        s.individuals = o.getIndividualsInSignature().size();
        s.annotationAssertions = o.getAxioms(AxiomType.ANNOTATION_ASSERTION).size();
        s.importsCount = o.getImportsDeclarations().size();

        for (OWLAxiom ax : o.getLogicalAxioms()) {
            s.axiomTypeCounts.merge(ax.getAxiomType().getName(), 1, Integer::sum);
        }
        for (OWLAnnotationAssertionAxiom ax : o.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            org.owleq.transform.LexicalChannels.of(ax.getProperty().getIRI())
                    .ifPresent(c -> s.lexicalChannelCounts.merge(c.name(), 1, Integer::sum));
        }

        // Report the tightest profile: EL first, since that is the one the pipeline requires.
        OWLProfileReport el = new OWL2ELProfile().checkOntology(o);
        if (el.isInProfile()) {
            s.profile = "OWL2_EL";
        } else {
            OWLProfileReport dl = new OWL2DLProfile().checkOntology(o);
            s.profile = dl.isInProfile() ? "OWL2_DL" : "NONE";
            s.profileViolations = el.getViolations().stream()
                    .map(v -> v.getClass().getSimpleName())
                    .distinct()
                    .sorted()
                    .limit(40)
                    .collect(Collectors.toList());
        }

        if (runReasoner) {
            try (ReasonerService rs = new ReasonerService(o)) {
                s.consistent = rs.isConsistent();
                if (s.consistent) {
                    s.unsatisfiableClasses = rs.unsatisfiableClasses().stream()
                            .map(c -> c.getIRI().toString())
                            .sorted()
                            .limit(200)
                            .collect(Collectors.toList());
                }
            }
        }
        return s;
    }
}
