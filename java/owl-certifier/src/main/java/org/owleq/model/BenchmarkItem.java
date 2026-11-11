package org.owleq.model;

import java.util.ArrayList;
import java.util.List;

/**
 * One benchmark instance: a query, its symbolically verified label, and the exact axiom context
 * the model will be shown (spec section 15).
 *
 * <p>An <em>orbit</em> is the set of items sharing a {@code baseItemId}: the original and every
 * transformed variant. All orbit members carry the same {@code label} by construction, which is
 * the property the whole study tests.
 */
public final class BenchmarkItem {

    public String schemaVersion = "1.0";
    public String baseItemId;
    public String orbitItemId;
    public Ontology ontology = new Ontology();
    public Task task = new Task();
    public Transform transform = new Transform();
    public Context context = new Context();
    public Reference reference = new Reference();
    public String split;

    public static final class Ontology {
        public String ontologyId;
        public String version;
        public String profile;
        public String sourceHash;
        public String transformedHash;
    }

    public static final class Task {
        /** ATOMIC_SUBSUMPTION | INSTANCE_CHECKING | EXPRESSION_SUBSUMPTION */
        public String type;
        public String queryFunctional;
        /** Natural-ish rendering of the query, for prompts that do not use functional syntax. */
        public String queryText;
        /** ENTAILED | NOT_ENTAILED */
        public String label;
        public boolean positive;
        /** Size of the smallest justification found; -1 when not computed. */
        public Integer proofDepth;
        /** True when the query axiom is asserted verbatim in the source ontology. */
        public boolean explicit;
        /**
         * For non-entailed items: which matched-negative family this came from
         * (SIBLING, NEARBY_BRANCH, LEXICAL, RANDOM).
         */
        public String negativeKind;
    }

    public static final class Transform {
        /** original | opaque | pseudoword_f0 | random_decoy | adversarial_decoy */
        public String operator;
        public Long seed;
        public String mappingId;
        /** The C0..C9 cell of the lexical-channel matrix (spec section 23). */
        public String lexicalCondition;
        public String annotationPolicy;
    }

    public static final class Context {
        public List<Axiom> axioms = new ArrayList<>();
        /**
         * Lexical annotations for the entities in this context, as they survive the
         * condition's annotation policy.
         *
         * <p>Without this the whole channel decomposition is unmeasurable on OBO
         * ontologies. Their IRIs are already opaque accession numbers
         * ({@code CL_0000540}), so all the human-readable meaning lives in
         * {@code rdfs:label} and the definition annotations. A prompt built only from
         * functional-syntax axioms shows the model no labels at all, which makes C0, C1
         * and C2 the same prompt and the label channel invisible.
         */
        public List<Lexicon> lexicon = new ArrayList<>();
        public String serialization = "FUNCTIONAL";
        /** How the context was built, e.g. LOCALITY_MODULE_BOTTOM or FULL_ONTOLOGY. */
        public String strategy;
        public int distractorCount;
        /**
         * True when the context provably carries the same label as the full ontology.
         * See {@link org.owleq.query.ContextBuilder} for the argument.
         */
        public boolean labelPreservationCertified;
    }

    public static final class Axiom {
        public String id;
        public String text;

        public Axiom() {
        }

        public Axiom(String id, String text) {
            this.id = id;
            this.text = text;
        }
    }

    /** One entity's surviving lexical annotations, keyed by the name used in the axioms. */
    public static final class Lexicon {
        /** IRI local name, i.e. exactly the token the prompt shows for this entity. */
        public String entity;
        public String iri;
        public String label;
        public String definition;
        public List<String> synonyms;
    }

    public static final class Reference {
        /** Each inner list is one justification, as context axiom ids. */
        public List<List<String>> supportAxiomSets = new ArrayList<>();
        public String reasoner;
        public boolean verified;
    }
}
