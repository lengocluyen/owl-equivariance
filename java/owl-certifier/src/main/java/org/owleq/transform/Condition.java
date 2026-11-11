package org.owleq.transform;

import org.semanticweb.owlapi.model.OWLOntology;

import java.util.*;

/**
 * A cell of the lexical-channel experimental matrix (spec section 23): an operator on IRIs paired
 * with a policy on annotations.
 *
 * <p>The design is factorial on purpose. Comparing C0 with C4 only shows that stripping everything
 * hurts; the informative comparisons are the ones that move a single channel:
 *
 * <ul>
 *   <li>C0 vs C1 -- IRI local names, with labels left in place;</li>
 *   <li>C0 vs C2 -- labels, with IRIs left in place;</li>
 *   <li>C4 vs C5 -- identifier morphology, holding meaning constant at zero (the tokenization
 *       control);</li>
 *   <li>C6 vs C7 -- irrelevant words versus actively misleading ones;</li>
 *   <li>C4 vs C8 -- a misleading label attached to a neutral identifier.</li>
 * </ul>
 *
 * <p>{@code C4S2} and {@code C4S3} are C4 under different random seeds. They exist to separate
 * "renaming hurts" from "this particular renaming hurts": two members of the same operator family
 * are logically indistinguishable, so any disagreement between them is the model contradicting
 * itself on identical problems.
 */
public final class Condition {

    public final String id;
    public final String operator;
    public final AnnotationPolicy annotationPolicy;
    public final long seed;
    private final int pseudowordFamily;

    private Condition(String id, String operator, AnnotationPolicy policy, long seed,
                      int pseudowordFamily) {
        this.id = id;
        this.operator = operator;
        this.annotationPolicy = policy;
        this.seed = seed;
        this.pseudowordFamily = pseudowordFamily;
    }

    public boolean isOriginal() {
        return "none".equals(operator) && annotationPolicy == AnnotationPolicy.KEEP_ALL;
    }

    /** Build the isomorphism this condition denotes, over the given source ontology. */
    public SignatureIsomorphism isomorphism(OWLOntology source, String namespaceBase) {
        if ("none".equals(operator)) {
            return SignatureIsomorphism.identity(source, annotationPolicy);
        }
        NameStrategy strategy;
        switch (operator) {
            case "opaque":
                strategy = new NameStrategy.Opaque();
                break;
            case "pseudoword":
                strategy = new NameStrategy.Pseudoword(pseudowordFamily);
                break;
            case "random_decoy":
                strategy = new NameStrategy.RandomDecoy();
                break;
            case "adversarial_decoy":
                strategy = new NameStrategy.AdversarialDecoy();
                break;
            default:
                throw new IllegalArgumentException("unknown operator: " + operator);
        }
        // The target namespace is deliberately identical for every condition and seed.
        // Encoding the condition id or seed here would print them inside every IRI in the
        // prompt ("urn:owleq:c7:42:c#..."), telling the model which experimental cell it is
        // in -- and letting it infer that the names are adversarial, or that two variants
        // are the same problem.
        return SignatureIsomorphism.build(source, strategy, annotationPolicy, seed,
                namespaceBase);
    }

    // ------------------------------------------------------------------ registry

    private static final Map<String, Condition> REGISTRY = new LinkedHashMap<>();

    private static void reg(String id, String op, AnnotationPolicy p, long seed, int family) {
        REGISTRY.put(id, new Condition(id, op, p, seed, family));
    }

    static {
        reg("C0", "none", AnnotationPolicy.KEEP_ALL, 0, 0);
        reg("C1", "opaque", AnnotationPolicy.KEEP_ALL, 42, 0);
        reg("C2", "none", AnnotationPolicy.REMOVE_LABELS, 0, 0);
        reg("C3", "none", AnnotationPolicy.REMOVE_DEFINITIONS, 0, 0);
        reg("C4", "opaque", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 0);
        reg("C4S2", "opaque", AnnotationPolicy.REMOVE_ALL_LEXICAL, 43, 0);
        reg("C4S3", "opaque", AnnotationPolicy.REMOVE_ALL_LEXICAL, 44, 0);
        reg("C5", "pseudoword", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 0);
        reg("C5F1", "pseudoword", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 1);
        reg("C5F2", "pseudoword", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 2);
        reg("C6", "random_decoy", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 0);
        reg("C7", "adversarial_decoy", AnnotationPolicy.REMOVE_ALL_LEXICAL, 42, 0);
        reg("C8", "opaque", AnnotationPolicy.MISLEADING_LABELS, 42, 0);
        reg("C9", "adversarial_decoy", AnnotationPolicy.KEEP_ALL, 42, 0);
    }

    public static Condition of(String id) {
        Condition c = REGISTRY.get(id.toUpperCase(Locale.ROOT));
        if (c == null) {
            throw new IllegalArgumentException("unknown condition " + id
                    + "; known: " + REGISTRY.keySet());
        }
        return c;
    }

    public static List<Condition> of(List<String> ids) {
        List<Condition> out = new ArrayList<>();
        for (String id : ids) {
            out.add(of(id));
        }
        return out;
    }

    /** The minimal pilot set recommended by spec section 23. */
    public static List<String> minimalPilot() {
        return Arrays.asList("C0", "C1", "C4", "C4S2", "C7", "C8");
    }

    @Override
    public String toString() {
        return id + "(" + operator + "/" + annotationPolicy + "/seed=" + seed + ")";
    }
}
