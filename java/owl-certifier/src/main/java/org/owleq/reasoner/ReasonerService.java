package org.owleq.reasoner;

import org.semanticweb.elk.owlapi.ElkReasonerFactory;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.reasoner.*;
import org.semanticweb.owlapi.util.InferredSubClassAxiomGenerator;

import java.util.*;

/**
 * Thin wrapper over an OWL reasoner used strictly as a symbolic oracle (spec section 3.3).
 *
 * <p>ELK is the default: it is a consequence-based OWL 2 EL reasoner, complete for the fragment
 * the benchmark is built on, and fast enough to classify a transformed ontology per orbit member.
 *
 * <p>ELK implements {@code isEntailed} for only some axiom types and throws
 * {@link UnsupportedEntailmentTypeException} otherwise. Rather than let that surface as a crash
 * halfway through dataset generation, every entailment check routes through
 * {@link #isEntailed(OWLOntology, OWLAxiom)}, which falls back to the classification-based
 * queries ELK does support and reports honestly when a query type is out of scope.
 */
public final class ReasonerService implements AutoCloseable {

    private final OWLOntology ontology;
    private final OWLReasoner reasoner;
    private final String reasonerName;

    public ReasonerService(OWLOntology ontology) {
        this(ontology, "ELK");
    }

    public ReasonerService(OWLOntology ontology, String reasonerName) {
        this.ontology = ontology;
        this.reasonerName = reasonerName;
        OWLReasonerFactory factory = new ElkReasonerFactory();
        this.reasoner = factory.createReasoner(ontology, new SimpleConfiguration());
        // Most benchmark sources and all justification subsets are TBox-only. Asking ELK to
        // prepare class assertions for an ontology with no individuals adds work to every
        // QuickXplain subset check without changing a single answer.
        if (ontology.getIndividualsInSignature().isEmpty()) {
            this.reasoner.precomputeInferences(InferenceType.CLASS_HIERARCHY);
        } else {
            this.reasoner.precomputeInferences(InferenceType.CLASS_HIERARCHY,
                    InferenceType.CLASS_ASSERTIONS);
        }
    }

    public String reasonerName() {
        return reasonerName;
    }

    public OWLReasoner raw() {
        return reasoner;
    }

    public boolean isConsistent() {
        return reasoner.isConsistent();
    }

    public Set<OWLClass> unsatisfiableClasses() {
        Set<OWLClass> out = new HashSet<>(reasoner.getUnsatisfiableClasses().getEntities());
        out.remove(ontology.getOWLOntologyManager().getOWLDataFactory().getOWLNothing());
        return out;
    }

    /**
     * Entailment check for the supported query shapes.
     *
     * @throws UnsupportedQueryException when the reasoner cannot decide this axiom type, so the
     *                                   caller can drop the item instead of guessing a label.
     */
    public boolean isEntailed(OWLAxiom query) {
        try {
            return reasoner.isEntailed(query);
        } catch (UnsupportedEntailmentTypeException | UnsupportedOperationException e) {
            return fallback(query);
        }
    }

    private boolean fallback(OWLAxiom query) {
        if (query instanceof OWLSubClassOfAxiom) {
            OWLSubClassOfAxiom sc = (OWLSubClassOfAxiom) query;
            if (sc.getSubClass().isAnonymous()) {
                throw new UnsupportedQueryException("anonymous subclass side: " + query);
            }
            OWLClass sub = sc.getSubClass().asOWLClass();
            OWLClassExpression sup = sc.getSuperClass();
            if (!sup.isAnonymous()) {
                return reasoner.getSuperClasses(sub, false).containsEntity(sup.asOWLClass())
                        || reasoner.getEquivalentClasses(sub).contains(sup.asOWLClass());
            }
            // Complex right-hand side: ELK answers subsumption against a complex expression
            // through the sub-class query, which it does support for EL expressions.
            return reasoner.getSubClasses(sup, false).containsEntity(sub)
                    || reasoner.getEquivalentClasses(sup).contains(sub);
        }
        if (query instanceof OWLClassAssertionAxiom) {
            OWLClassAssertionAxiom ca = (OWLClassAssertionAxiom) query;
            if (ca.getIndividual().isAnonymous()) {
                throw new UnsupportedQueryException("anonymous individual: " + query);
            }
            return reasoner.getInstances(ca.getClassExpression(), false)
                    .containsEntity(ca.getIndividual().asOWLNamedIndividual());
        }
        throw new UnsupportedQueryException("reasoner cannot decide: " + query.getAxiomType());
    }

    /** Static convenience: build a reasoner over {@code o}, decide {@code q}, dispose. */
    public static boolean isEntailed(OWLOntology o, OWLAxiom q) {
        try (ReasonerService rs = new ReasonerService(o)) {
            return rs.isEntailed(q);
        }
    }

    public NodeSet<OWLClass> superClasses(OWLClass c, boolean direct) {
        return reasoner.getSuperClasses(c, direct);
    }

    public NodeSet<OWLClass> subClasses(OWLClass c, boolean direct) {
        return reasoner.getSubClasses(c, direct);
    }

    public Node<OWLClass> equivalentClasses(OWLClass c) {
        return reasoner.getEquivalentClasses(c);
    }

    public NodeSet<OWLNamedIndividual> instances(OWLClassExpression c, boolean direct) {
        return reasoner.getInstances(c, direct);
    }

    public NodeSet<OWLClass> types(OWLNamedIndividual i, boolean direct) {
        return reasoner.getTypes(i, direct);
    }

    /** All inferred (not necessarily asserted) atomic subsumptions, used for positive sampling. */
    public List<OWLSubClassOfAxiom> inferredSubsumptions() {
        List<OWLSubClassOfAxiom> out = new ArrayList<>();
        InferredSubClassAxiomGenerator gen = new InferredSubClassAxiomGenerator();
        gen.createAxioms(ontology.getOWLOntologyManager().getOWLDataFactory(), reasoner)
                .forEach(out::add);
        return out;
    }

    @Override
    public void close() {
        reasoner.dispose();
    }

    /** Raised when the symbolic oracle cannot decide a query, so no label may be recorded. */
    public static final class UnsupportedQueryException extends RuntimeException {
        public UnsupportedQueryException(String msg) {
            super(msg);
        }
    }
}
