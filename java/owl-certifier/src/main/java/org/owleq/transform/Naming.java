package org.owleq.transform;

import org.semanticweb.owlapi.model.*;

import java.util.*;

/** Small shared helpers for local-name handling. */
public final class Naming {

    private Naming() {
    }

    public static String typePrefix(EntityType<?> t) {
        if (t.equals(EntityType.CLASS)) {
            return "C";
        }
        if (t.equals(EntityType.OBJECT_PROPERTY)) {
            return "OP";
        }
        if (t.equals(EntityType.DATA_PROPERTY)) {
            return "DP";
        }
        if (t.equals(EntityType.NAMED_INDIVIDUAL)) {
            return "I";
        }
        throw new IllegalArgumentException("unsupported entity type: " + t);
    }

    /** Classes and individuals get initial capitals, properties stay lower camel, as is conventional. */
    public static String caseFor(EntityType<?> t, String word) {
        if (t.equals(EntityType.OBJECT_PROPERTY) || t.equals(EntityType.DATA_PROPERTY)) {
            return Character.toLowerCase(word.charAt(0)) + word.substring(1);
        }
        return Character.toUpperCase(word.charAt(0)) + word.substring(1);
    }

    /** IRI local name: the fragment, or the last path segment when there is no fragment. */
    public static String localName(OWLEntity e) {
        return localName(e.getIRI());
    }

    public static String localName(IRI iri) {
        String s = iri.toString();
        int h = s.lastIndexOf('#');
        if (h >= 0 && h < s.length() - 1) {
            return s.substring(h + 1);
        }
        int sl = s.lastIndexOf('/');
        if (sl >= 0 && sl < s.length() - 1) {
            return s.substring(sl + 1);
        }
        return s;
    }

    /**
     * The human-readable name of each entity: its {@code rdfs:label} where one exists,
     * otherwise its IRI local name.
     *
     * <p>Needed because OBO ontologies name entities with opaque accession codes
     * ({@code CL_1000480}). An operator that permutes local names on such an ontology
     * permutes meaningless numbers, which is not a semantic intervention at all -- the
     * meaning lives in the label, so that is what a semantic operator has to move.
     */
    public static Map<OWLEntity, String> displayNames(OWLOntology source) {
        Map<IRI, String> labels = new HashMap<>();
        for (OWLAnnotationAssertionAxiom ax : source.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            if (ax.getSubject() instanceof IRI
                    && ax.getValue() instanceof OWLLiteral
                    && LexicalChannels.of(ax.getProperty().getIRI()).orElse(null)
                    == LexicalChannels.LABEL) {
                labels.putIfAbsent((IRI) ax.getSubject(),
                        ((OWLLiteral) ax.getValue()).getLiteral());
            }
        }
        Map<OWLEntity, String> out = new LinkedHashMap<>();
        for (OWLEntity e : source.getSignature()) {
            String label = labels.get(e.getIRI());
            out.put(e, label != null && !label.trim().isEmpty() ? label : localName(e));
        }
        return out;
    }

    /**
     * Turn a human-readable name into a legal IRI local name: {@code "dendritic cell"}
     * becomes {@code "DendriticCell"}. Keeps the result readable, so a decoy still looks
     * like a concept name rather than becoming another opaque token.
     */
    public static String toLocalName(String display) {
        StringBuilder sb = new StringBuilder();
        for (String part : display.trim().split("[^A-Za-z0-9]+")) {
            if (part.isEmpty()) {
                continue;
            }
            sb.append(Character.toUpperCase(part.charAt(0)));
            if (part.length() > 1) {
                sb.append(part.substring(1));
            }
        }
        String out = sb.toString();
        if (out.isEmpty()) {
            return "X";
        }
        return Character.isDigit(out.charAt(0)) ? "X" + out : out;
    }

    /**
     * Every lowercase token that appears anywhere in the ontology's lexical channels or local
     * names. Generated pseudowords and decoys are checked against this so that a "meaningless"
     * name never accidentally coincides with a real name from the same ontology.
     */
    public static Set<String> lexicalBlocklist(OWLOntology source) {
        Set<String> out = new HashSet<>();
        for (OWLEntity e : source.getSignature()) {
            String ln = localName(e).toLowerCase(Locale.ROOT);
            out.add(ln);
            for (String part : ln.split("[^a-z0-9]+")) {
                if (part.length() > 2) {
                    out.add(part);
                }
            }
        }
        for (OWLAnnotationAssertionAxiom ax : source.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            if (ax.getValue() instanceof OWLLiteral) {
                String lit = ((OWLLiteral) ax.getValue()).getLiteral().toLowerCase(Locale.ROOT);
                for (String part : lit.split("[^a-z0-9]+")) {
                    if (part.length() > 2) {
                        out.add(part);
                    }
                }
            }
        }
        return out;
    }
}
