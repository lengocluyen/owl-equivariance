package org.owleq.io;

import org.owleq.model.BenchmarkItem;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.io.StringDocumentSource;
import org.semanticweb.owlapi.model.*;

import java.util.*;

/**
 * Rebuilds OWL objects from the functional-syntax strings stored in a benchmark item.
 *
 * <p>This is what lets proof validation run against the dataset alone. The alternative -- keeping
 * a serialized ontology file per item -- would multiply artifacts by the number of orbit members
 * and make the JSONL non-self-contained. Because the stored strings are full-IRI functional
 * syntax produced by OWLAPI itself, the round trip is exact.
 */
public final class ContextParser {

    private ContextParser() {
    }

    /** Parse the item's context axioms, keyed by their context id (A1, A2, ...). */
    public static Map<String, OWLAxiom> parseContext(BenchmarkItem item) {
        StringBuilder doc = new StringBuilder("Ontology(<urn:owleq:ctx>\n");
        for (BenchmarkItem.Axiom a : item.context.axioms) {
            doc.append(a.text).append('\n');
        }
        doc.append(")\n");

        OWLOntology o = parse(doc.toString());
        // Match parsed axioms back to ids by re-rendering: parsing is order-preserving in
        // practice but not guaranteed, so the join is on content, never on position.
        Map<String, OWLAxiom> byRendered = new LinkedHashMap<>();
        Map<String, OWLAxiom> rendered = new HashMap<>();
        for (OWLAxiom ax : o.getAxioms()) {
            rendered.put(OntologyIO.renderAxiom(ax), ax);
        }
        for (BenchmarkItem.Axiom a : item.context.axioms) {
            OWLAxiom ax = rendered.get(a.text.replaceAll("\\s+", " ").trim());
            if (ax != null) {
                byRendered.put(a.id, ax);
            }
        }
        return byRendered;
    }

    /** Parse a single axiom, e.g. the query, by wrapping it in a throwaway ontology. */
    public static OWLAxiom parseAxiom(String functionalSyntax) {
        OWLOntology o = parse("Ontology(<urn:owleq:q>\n" + functionalSyntax + "\n)\n");
        for (OWLAxiom ax : o.getLogicalAxioms()) {
            return ax;
        }
        for (OWLAxiom ax : o.getAxioms()) {
            return ax;
        }
        throw new IllegalArgumentException("no axiom parsed from: " + functionalSyntax);
    }

    private static OWLOntology parse(String document) {
        try {
            OWLOntologyManager m = OWLManager.createOWLOntologyManager();
            return m.loadOntologyFromOntologyDocument(new StringDocumentSource(document));
        } catch (OWLOntologyCreationException e) {
            throw new IllegalArgumentException("could not parse context document", e);
        }
    }
}
