package org.owleq.query;

import org.owleq.transform.LexicalChannels;
import org.owleq.transform.Naming;
import org.semanticweb.owlapi.model.*;

import java.util.*;

/**
 * Human-readable text for entities, and the similarity measure used to build lexically matched
 * negatives.
 *
 * <p>Similarity here is a dataset-construction device, not a research claim: its only job is to
 * find a wrong answer that <em>looks</em> like the right one, so that a model cannot separate
 * entailed from non-entailed items by surface form alone.
 */
public final class Lexicon {

    private Lexicon() {
    }

    /** Preferred display text per entity: rdfs:label if present, otherwise the IRI local name. */
    public static Map<OWLEntity, String> index(OWLOntology o) {
        Map<IRI, String> labels = new HashMap<>();
        for (OWLAnnotationAssertionAxiom ax : o.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            if (ax.getSubject() instanceof IRI
                    && ax.getValue() instanceof OWLLiteral
                    && LexicalChannels.of(ax.getProperty().getIRI()).orElse(null)
                    == LexicalChannels.LABEL) {
                labels.putIfAbsent((IRI) ax.getSubject(), ((OWLLiteral) ax.getValue()).getLiteral());
            }
        }
        Map<OWLEntity, String> out = new HashMap<>();
        for (OWLEntity e : o.getSignature()) {
            String l = labels.get(e.getIRI());
            out.put(e, l != null ? l : Naming.localName(e));
        }
        return out;
    }

    /** Every lexical channel an entity carries, after an annotation policy has been applied. */
    public static final class Entry {
        public String label;
        public String definition;
        public final List<String> synonyms = new ArrayList<>();

        public boolean isEmpty() {
            return label == null && definition == null && synonyms.isEmpty();
        }
    }

    /**
     * Per-entity lexical annotations of an ontology, keyed by IRI.
     *
     * <p>Built from the <em>transformed</em> ontology, so it reflects exactly what the
     * condition's annotation policy left behind: an entry is absent when the policy
     * stripped every channel, and carries a misleading label when the policy invented one.
     */
    public static Map<IRI, Entry> annotationIndex(OWLOntology o) {
        Map<IRI, Entry> out = new HashMap<>();
        for (OWLAnnotationAssertionAxiom ax : o.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            if (!(ax.getSubject() instanceof IRI) || !(ax.getValue() instanceof OWLLiteral)) {
                continue;
            }
            Optional<LexicalChannels> channel = LexicalChannels.of(ax.getProperty().getIRI());
            if (!channel.isPresent()) {
                continue;
            }
            String value = ((OWLLiteral) ax.getValue()).getLiteral();
            Entry entry = out.computeIfAbsent((IRI) ax.getSubject(), k -> new Entry());
            switch (channel.get()) {
                case LABEL:
                    if (entry.label == null) {
                        entry.label = value;
                    }
                    break;
                case DEFINITION:
                case COMMENT:
                    if (entry.definition == null) {
                        entry.definition = value;
                    }
                    break;
                case SYNONYM:
                    if (entry.synonyms.size() < 4) {
                        entry.synonyms.add(value);
                    }
                    break;
                default:
                    break;
            }
        }
        return out;
    }

    /**
     * Token-level Jaccard blended with character bigram overlap, in [0,1].
     *
     * <p>Ontology names are usually multi-word ("regulation of cell death"), where token overlap
     * is the dominant signal; the bigram term keeps morphological variants ("neuron" /
     * "neuronal") from scoring zero.
     */
    /** Below this many letters, a name is treated as carrying no lexical signal at all. */
    private static final int MIN_ALPHA = 3;

    public static double similarity(String a, String b) {
        if (a == null || b == null) {
            return 0.0;
        }
        String na = normalize(a);
        String nb = normalize(b);
        // Bare OBO identifiers ("CL_0000540" vs "CL_0000541") share the "cl" token and
        // nearly all their character bigrams while having nothing lexical in common.
        // Scoring them as similar would make the "lexically matched" negative family
        // indistinguishable from a random one.
        if (letterCount(na) < MIN_ALPHA || letterCount(nb) < MIN_ALPHA) {
            return 0.0;
        }
        return 0.6 * jaccard(tokens(a), tokens(b))
                + 0.4 * jaccard(bigrams(na), bigrams(nb));
    }

    /** Lowercased alphabetic content only; camelCase split into words, digits dropped. */
    private static String normalize(String s) {
        return s.replaceAll("([a-z])([A-Z])", "$1 $2")
                .toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z ]", " ")
                .replaceAll("\\s+", " ")
                .trim();
    }

    private static int letterCount(String normalized) {
        return normalized.replace(" ", "").length();
    }

    private static Set<String> tokens(String s) {
        Set<String> out = new HashSet<>();
        for (String t : normalize(s).split("\\s+")) {
            if (!t.isEmpty()) {
                out.add(t);
            }
        }
        return out;
    }

    private static Set<String> bigrams(String s) {
        Set<String> out = new HashSet<>();
        String t = s.replace(" ", "");
        for (int i = 0; i + 2 <= t.length(); i++) {
            out.add(t.substring(i, i + 2));
        }
        return out;
    }

    private static double jaccard(Set<String> a, Set<String> b) {
        if (a.isEmpty() && b.isEmpty()) {
            return 0.0;
        }
        Set<String> inter = new HashSet<>(a);
        inter.retainAll(b);
        Set<String> union = new HashSet<>(a);
        union.addAll(b);
        return union.isEmpty() ? 0.0 : (double) inter.size() / union.size();
    }
}
