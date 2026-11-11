package org.owleq.transform;

import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.util.OWLObjectDuplicator;

import java.util.*;
import java.util.stream.Collectors;

/**
 * A typed signature isomorphism pi = (pi_C, pi_OP, pi_DP, pi_I) and its application to
 * ontologies, axioms and queries (spec section 4).
 *
 * <p><b>Why entailment is preserved.</b> Under OWL 2 Direct Semantics an interpretation assigns
 * meaning to vocabulary symbols through the interpretation function; nothing in the semantics
 * depends on which symbol was chosen. A bijective, type-preserving renaming therefore induces a
 * bijection on models, and so {@code O |= q iff pi(O) |= pi(q)}. This is a proof by construction
 * (certificate type {@code BY_CONSTRUCTION}); the reasoner checks in
 * {@link org.owleq.validation.OrbitValidator} are software tests, not the argument.
 *
 * <p><b>Punning.</b> The mapping is keyed on {@link OWLEntity}, i.e. on the pair (IRI, entity
 * type), never on the IRI alone. An IRI used as both a class and an individual is two entities
 * and receives two independent images. This is sound because Direct Semantics interprets the
 * class and individual uses through separate interpretation functions, so splitting a pun is
 * itself an isomorphism. Keying on IRI alone -- what {@code OWLEntityRenamer} does -- would
 * silently merge the two and could change entailments.
 *
 * <p>Each entity type is given its own target namespace, which guarantees injectivity across
 * types and ensures the transform never creates a pun that was not there before.
 */
public final class SignatureIsomorphism {

    public static final List<EntityType<?>> RENAMED_TYPES = Collections.unmodifiableList(
            Arrays.asList(EntityType.CLASS, EntityType.OBJECT_PROPERTY,
                    EntityType.DATA_PROPERTY, EntityType.NAMED_INDIVIDUAL));

    private final String operatorId;
    private final long seed;
    private final String targetNamespace;
    private final AnnotationPolicy annotationPolicy;

    /** entity -> new IRI. The authoritative forward mapping. */
    private final Map<OWLEntity, IRI> forward;
    /** target entity -> original entity, for inverse mapping and answer un-mapping. */
    private final Map<OWLEntity, OWLEntity> backward;

    private final OWLDataFactory df = OWLManager.getOWLDataFactory();

    private SignatureIsomorphism(String operatorId, long seed, String targetNamespace,
                                 AnnotationPolicy policy, Map<OWLEntity, IRI> forward) {
        this.operatorId = operatorId;
        this.seed = seed;
        this.targetNamespace = targetNamespace;
        this.annotationPolicy = policy;
        this.forward = Collections.unmodifiableMap(forward);

        // Injectivity is required per entity type, not globally: a class and an individual are
        // allowed to share a target IRI, because that is a pun and puns are legal. Keying the
        // inverse on the target *entity* enforces exactly the right condition and keeps the
        // identity mapping valid on ontologies that already contain puns.
        Map<OWLEntity, OWLEntity> back = new LinkedHashMap<>();
        for (Map.Entry<OWLEntity, IRI> e : forward.entrySet()) {
            OWLEntity target = df.getOWLEntity(e.getKey().getEntityType(), e.getValue());
            OWLEntity clash = back.put(target, e.getKey());
            if (clash != null) {
                throw new IllegalStateException("mapping is not injective within type "
                        + e.getKey().getEntityType() + ": " + clash + " and " + e.getKey()
                        + " both map to " + e.getValue());
            }
        }
        this.backward = Collections.unmodifiableMap(back);
    }

    // ------------------------------------------------------------------ construction

    public static SignatureIsomorphism build(OWLOntology source, NameStrategy strategy,
                                             AnnotationPolicy policy, long seed,
                                             String targetNamespaceBase) {
        Map<OWLEntity, IRI> forward = new LinkedHashMap<>();
        for (EntityType<?> type : RENAMED_TYPES) {
            List<OWLEntity> entities = signature(source, type);
            if (entities.isEmpty()) {
                continue;
            }
            Map<OWLEntity, String> names = strategy.assign(entities, type, source, seed);
            Map<OWLEntity, String> unique = ensureInjective(entities, names);
            String ns = namespaceFor(targetNamespaceBase, type);
            for (OWLEntity e : entities) {
                forward.put(e, IRI.create(ns + unique.get(e)));
            }
        }
        return new SignatureIsomorphism(strategy.operatorId(), seed, targetNamespaceBase,
                policy, forward);
    }

    /**
     * The identity isomorphism: vocabulary untouched, annotation policy still applied.
     *
     * <p>This is what makes the annotation-only cells of the lexical-channel matrix (C2, C3)
     * possible: they must vary labels while leaving IRIs exactly as they were, so that C0 vs C2
     * isolates the label channel with nothing else moving.
     */
    public static SignatureIsomorphism identity(OWLOntology source, AnnotationPolicy policy) {
        Map<OWLEntity, IRI> forward = new LinkedHashMap<>();
        for (EntityType<?> type : RENAMED_TYPES) {
            for (OWLEntity e : signature(source, type)) {
                forward.put(e, e.getIRI());
            }
        }
        String ns = source.getOntologyID().getOntologyIRI().isPresent()
                ? source.getOntologyID().getOntologyIRI().get().toString() + "#"
                : "urn:owleq:identity#";
        return new SignatureIsomorphism("none", 0L, ns, policy, forward);
    }

    /** Sorted, built-in-free signature of one entity type. Sorting makes the build deterministic. */
    private static List<OWLEntity> signature(OWLOntology o, EntityType<?> type) {
        return o.getSignature().stream()
                .filter(e -> e.getEntityType().equals(type))
                .filter(e -> !e.isBuiltIn())
                .sorted(Comparator.comparing(e -> e.getIRI().toString()))
                .collect(Collectors.toList());
    }

    private static String namespaceFor(String base, EntityType<?> type) {
        return base + Naming.typePrefix(type).toLowerCase(Locale.ROOT) + "#";
    }

    /**
     * Strategies that permute existing names (O4) can collide when two IRIs in different source
     * namespaces share a local name. Disambiguate deterministically rather than failing.
     */
    private static Map<OWLEntity, String> ensureInjective(List<OWLEntity> entities,
                                                          Map<OWLEntity, String> names) {
        Map<String, Integer> counts = new HashMap<>();
        Map<OWLEntity, String> out = new LinkedHashMap<>();
        for (OWLEntity e : entities) {
            String base = names.get(e);
            if (base == null || base.isEmpty()) {
                throw new IllegalStateException("no name assigned for " + e);
            }
            int n = counts.merge(base, 1, Integer::sum);
            out.put(e, n == 1 ? base : base + "_" + n);
        }
        return out;
    }

    // ------------------------------------------------------------------ application

    /** Apply pi to a complete ontology, including the annotation-channel policy. */
    public OWLOntology apply(OWLOntology source) throws OWLOntologyCreationException {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        OWLObjectDuplicator dup = new OWLObjectDuplicator(new LinkedHashMap<>(forward), df);

        Set<OWLAxiom> out = new HashSet<>();
        for (OWLAxiom ax : source.getAxioms()) {
            if (ax instanceof OWLAnnotationAssertionAxiom) {
                out.addAll(rewriteAnnotation((OWLAnnotationAssertionAxiom) ax));
            } else {
                // Axiom annotations travel with the axiom and can leak the source vocabulary
                // (OBO ontologies annotate axioms with provenance strings), so drop them.
                out.add(dup.duplicateObject(ax.getAxiomWithoutAnnotations()));
            }
        }
        if (annotationPolicy.synthesizesLabels()) {
            out.addAll(synthesizeLabels(source));
        }
        // Ontology-level annotations are dropped: they name the source ontology and would
        // reintroduce exactly the identifying signal the transform removes.
        return m.createOntology(out, IRI.create(targetNamespace + "ontology"));
    }

    /**
     * Retarget one annotation assertion, or drop it if its channel is removed by the policy.
     * A subject IRI that is punned yields one assertion per image, preserving all lexical
     * material without inventing an arbitrary tie-break.
     */
    private Set<OWLAxiom> rewriteAnnotation(OWLAnnotationAssertionAxiom ax) {
        if (!(ax.getSubject() instanceof IRI)) {
            return Collections.emptySet();  // anonymous-individual annotations carry no signal here
        }
        Optional<LexicalChannels> channel = LexicalChannels.of(ax.getProperty().getIRI());
        if (channel.isPresent() && annotationPolicy.removed().contains(channel.get())) {
            return Collections.emptySet();
        }
        List<IRI> images = imagesOf((IRI) ax.getSubject());
        if (images.isEmpty()) {
            return Collections.emptySet();  // annotations on non-renamed entities are dropped
        }
        Set<OWLAxiom> out = new HashSet<>();
        for (IRI img : images) {
            out.add(df.getOWLAnnotationAssertionAxiom(ax.getProperty(), img, ax.getValue()));
        }
        return out;
    }

    /** Labels invented by the OPAQUE_LABELS / MISLEADING_LABELS policies. */
    private Set<OWLAxiom> synthesizeLabels(OWLOntology source) {
        Set<OWLAxiom> out = new HashSet<>();
        OWLAnnotationProperty label = df.getOWLAnnotationProperty(LexicalChannels.rdfsLabel());

        if (annotationPolicy == AnnotationPolicy.OPAQUE_LABELS) {
            for (Map.Entry<OWLEntity, IRI> e : forward.entrySet()) {
                out.add(df.getOWLAnnotationAssertionAxiom(label, e.getValue(),
                        df.getOWLLiteral(Naming.localName(e.getValue()))));
            }
            return out;
        }

        // MISLEADING_LABELS: give each entity the label of a confusable neighbour, so the label
        // channel actively contradicts the (untouched) logical structure.
        Map<OWLEntity, String> sourceLabels = labelIndex(source);
        for (EntityType<?> type : RENAMED_TYPES) {
            List<OWLEntity> entities = signature(source, type);
            if (entities.isEmpty()) {
                continue;
            }
            Map<OWLEntity, OWLEntity> shift = Derangement.siblingShift(entities, source);
            for (OWLEntity e : entities) {
                OWLEntity partner = shift.get(e);
                String text = sourceLabels.getOrDefault(partner, Naming.localName(partner));
                out.add(df.getOWLAnnotationAssertionAxiom(label, forward.get(e),
                        df.getOWLLiteral(text)));
            }
        }
        return out;
    }

    private Map<OWLEntity, String> labelIndex(OWLOntology source) {
        Map<IRI, String> byIri = new HashMap<>();
        for (OWLAnnotationAssertionAxiom ax : source.getAxioms(AxiomType.ANNOTATION_ASSERTION)) {
            if (ax.getSubject() instanceof IRI
                    && LexicalChannels.of(ax.getProperty().getIRI()).orElse(null) == LexicalChannels.LABEL
                    && ax.getValue() instanceof OWLLiteral) {
                byIri.putIfAbsent((IRI) ax.getSubject(), ((OWLLiteral) ax.getValue()).getLiteral());
            }
        }
        Map<OWLEntity, String> out = new HashMap<>();
        for (OWLEntity e : forward.keySet()) {
            String l = byIri.get(e.getIRI());
            if (l != null) {
                out.put(e, l);
            }
        }
        return out;
    }

    private List<IRI> imagesOf(IRI subject) {
        List<IRI> out = new ArrayList<>();
        for (Map.Entry<OWLEntity, IRI> e : forward.entrySet()) {
            if (e.getKey().getIRI().equals(subject)) {
                out.add(e.getValue());
            }
        }
        return out;
    }

    // ------------------------------------------------------------------ axioms and queries

    /** pi(alpha) for a single axiom, e.g. a query. */
    public OWLAxiom transform(OWLAxiom axiom) {
        OWLObjectDuplicator dup = new OWLObjectDuplicator(new LinkedHashMap<>(forward), df);
        return dup.duplicateObject(axiom.getAxiomWithoutAnnotations());
    }

    /** pi^-1(alpha): maps a transformed axiom or answer back into the source vocabulary. */
    public OWLAxiom inverse(OWLAxiom transformedAxiom) {
        OWLObjectDuplicator dup = new OWLObjectDuplicator(inverseEntityMap(), df);
        return dup.duplicateObject(transformedAxiom.getAxiomWithoutAnnotations());
    }

    public OWLEntity inverseEntity(OWLEntity transformed) {
        OWLEntity src = backward.get(transformed);
        return src != null ? src : transformed;
    }

    private Map<OWLEntity, IRI> inverseEntityMap() {
        Map<OWLEntity, IRI> inv = new LinkedHashMap<>();
        for (Map.Entry<OWLEntity, IRI> e : forward.entrySet()) {
            OWLEntity target = df.getOWLEntity(e.getKey().getEntityType(), e.getValue());
            inv.put(target, e.getKey().getIRI());
        }
        return inv;
    }

    // ------------------------------------------------------------------ accessors

    public String operatorId() {
        return operatorId;
    }

    public long seed() {
        return seed;
    }

    public AnnotationPolicy annotationPolicy() {
        return annotationPolicy;
    }

    public String targetNamespace() {
        return targetNamespace;
    }

    public Map<OWLEntity, IRI> forwardMap() {
        return forward;
    }

    public int size() {
        return forward.size();
    }

    /** Per-type source-IRI -> target-IRI view, for the mapping manifest. */
    public Map<String, Map<String, String>> byTypeStrings() {
        Map<String, Map<String, String>> out = new LinkedHashMap<>();
        for (EntityType<?> t : RENAMED_TYPES) {
            Map<String, String> m = new TreeMap<>();
            for (Map.Entry<OWLEntity, IRI> e : forward.entrySet()) {
                if (e.getKey().getEntityType().equals(t)) {
                    m.put(e.getKey().getIRI().toString(), e.getValue().toString());
                }
            }
            out.put(Naming.typePrefix(t), m);
        }
        return out;
    }
}
