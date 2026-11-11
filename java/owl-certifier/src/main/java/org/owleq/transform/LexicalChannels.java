package org.owleq.transform;

import org.semanticweb.owlapi.model.IRI;
import org.semanticweb.owlapi.vocab.OWLRDFVocabulary;
import org.semanticweb.owlapi.vocab.SKOSVocabulary;

import java.util.*;

/**
 * The separable lexical channels of an ontology (spec section 9.2).
 *
 * <p>The point of the study is that these are independently manipulable: an entity's IRI local
 * name, its label, and its textual definition are three different routes by which natural-language
 * meaning reaches the model. Keeping them in named buckets is what makes the factorial design of
 * section 23 possible.
 */
public enum LexicalChannels {
    LABEL,
    SYNONYM,
    DEFINITION,
    COMMENT;

    private static final Map<IRI, LexicalChannels> BY_IRI = new HashMap<>();

    private static void reg(LexicalChannels c, String... iris) {
        for (String s : iris) {
            BY_IRI.put(IRI.create(s), c);
        }
    }

    static {
        reg(LABEL,
                OWLRDFVocabulary.RDFS_LABEL.getIRI().toString(),
                SKOSVocabulary.PREFLABEL.getIRI().toString(),
                "http://www.w3.org/2004/02/skos/core#prefLabel");
        reg(SYNONYM,
                SKOSVocabulary.ALTLABEL.getIRI().toString(),
                "http://www.geneontology.org/formats/oboInOwl#hasExactSynonym",
                "http://www.geneontology.org/formats/oboInOwl#hasRelatedSynonym",
                "http://www.geneontology.org/formats/oboInOwl#hasNarrowSynonym",
                "http://www.geneontology.org/formats/oboInOwl#hasBroadSynonym",
                "http://www.geneontology.org/formats/oboInOwl#hasSynonym");
        reg(DEFINITION,
                "http://purl.obolibrary.org/obo/IAO_0000115",
                "http://www.geneontology.org/formats/oboInOwl#hasDefinition",
                SKOSVocabulary.DEFINITION.getIRI().toString());
        reg(COMMENT,
                OWLRDFVocabulary.RDFS_COMMENT.getIRI().toString(),
                "http://purl.obolibrary.org/obo/IAO_0000116");
    }

    /** Channel of an annotation property, or empty if the property carries no lexical meaning. */
    public static Optional<LexicalChannels> of(IRI annotationProperty) {
        return Optional.ofNullable(BY_IRI.get(annotationProperty));
    }

    public static IRI rdfsLabel() {
        return OWLRDFVocabulary.RDFS_LABEL.getIRI();
    }
}
