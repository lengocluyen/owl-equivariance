package org.owleq.transform;

import java.util.EnumSet;
import java.util.Set;

/**
 * What happens to the annotation channels when an ontology is transformed (spec section 12.7).
 *
 * <p>Annotation axioms carry no weight under OWL 2 Direct Semantics, so every policy here is
 * trivially entailment-preserving. They are varied precisely because they are logically inert:
 * any change in model behaviour they cause is by definition not a change in reasoning.
 */
public enum AnnotationPolicy {

    /** Everything survives the renaming, attached to the new IRIs. */
    KEEP_ALL,

    /** Labels dropped, definitions and synonyms kept. */
    REMOVE_LABELS,

    /** Definitions and comments dropped, labels kept. */
    REMOVE_DEFINITIONS,

    /** Synonyms dropped, labels and definitions kept. */
    REMOVE_SYNONYMS,

    /** Every lexical channel dropped: the model sees IRIs and logical structure only. */
    REMOVE_ALL_LEXICAL,

    /** Labels replaced by the new (meaningless) local name, other channels dropped. */
    OPAQUE_LABELS,

    /** Labels replaced by another entity's label, other channels dropped. */
    MISLEADING_LABELS;

    /** Channels this policy strips. */
    public Set<LexicalChannels> removed() {
        switch (this) {
            case KEEP_ALL:
                return EnumSet.noneOf(LexicalChannels.class);
            case REMOVE_LABELS:
                return EnumSet.of(LexicalChannels.LABEL);
            case REMOVE_DEFINITIONS:
                return EnumSet.of(LexicalChannels.DEFINITION, LexicalChannels.COMMENT);
            case REMOVE_SYNONYMS:
                return EnumSet.of(LexicalChannels.SYNONYM);
            case REMOVE_ALL_LEXICAL:
            case OPAQUE_LABELS:
            case MISLEADING_LABELS:
                return EnumSet.allOf(LexicalChannels.class);
            default:
                throw new IllegalStateException();
        }
    }

    public boolean synthesizesLabels() {
        return this == OPAQUE_LABELS || this == MISLEADING_LABELS;
    }
}
