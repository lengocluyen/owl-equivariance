package org.owleq.query;

import org.owleq.transform.Naming;
import org.semanticweb.owlapi.model.*;

import java.util.stream.Collectors;

/**
 * Renders axioms in a compact Manchester-like syntax.
 *
 * <p>Functional syntax is the authoritative form stored in the dataset; this is the alternative
 * surface form for the syntax ablation (spec section 31). Keeping both lets the study check that
 * a measured effect is a property of the renaming and not of one particular notation.
 *
 * <p>Entities are printed by local name only. That is deliberate: the local name is one of the
 * lexical channels under study, so the prompt must show exactly what the condition specifies and
 * nothing more -- printing full IRIs would smuggle the source namespace back in.
 */
public final class Verbalizer {

    private Verbalizer() {
    }

    public static String axiom(OWLAxiom ax) {
        if (ax instanceof OWLSubClassOfAxiom) {
            OWLSubClassOfAxiom a = (OWLSubClassOfAxiom) ax;
            return expr(a.getSubClass()) + " SubClassOf " + expr(a.getSuperClass());
        }
        if (ax instanceof OWLEquivalentClassesAxiom) {
            return ((OWLEquivalentClassesAxiom) ax).getClassExpressions().stream()
                    .map(Verbalizer::expr)
                    .collect(Collectors.joining(" EquivalentTo "));
        }
        if (ax instanceof OWLDisjointClassesAxiom) {
            return "DisjointClasses: " + ((OWLDisjointClassesAxiom) ax).getClassExpressions()
                    .stream().map(Verbalizer::expr).collect(Collectors.joining(", "));
        }
        if (ax instanceof OWLClassAssertionAxiom) {
            OWLClassAssertionAxiom a = (OWLClassAssertionAxiom) ax;
            return ind(a.getIndividual()) + " Type " + expr(a.getClassExpression());
        }
        if (ax instanceof OWLObjectPropertyAssertionAxiom) {
            OWLObjectPropertyAssertionAxiom a = (OWLObjectPropertyAssertionAxiom) ax;
            return ind(a.getSubject()) + " " + prop(a.getProperty()) + " " + ind(a.getObject());
        }
        if (ax instanceof OWLSubObjectPropertyOfAxiom) {
            OWLSubObjectPropertyOfAxiom a = (OWLSubObjectPropertyOfAxiom) ax;
            return prop(a.getSubProperty()) + " SubPropertyOf " + prop(a.getSuperProperty());
        }
        if (ax instanceof OWLObjectPropertyDomainAxiom) {
            OWLObjectPropertyDomainAxiom a = (OWLObjectPropertyDomainAxiom) ax;
            return prop(a.getProperty()) + " Domain " + expr(a.getDomain());
        }
        if (ax instanceof OWLObjectPropertyRangeAxiom) {
            OWLObjectPropertyRangeAxiom a = (OWLObjectPropertyRangeAxiom) ax;
            return prop(a.getProperty()) + " Range " + expr(a.getRange());
        }
        if (ax instanceof OWLTransitiveObjectPropertyAxiom) {
            return prop(((OWLTransitiveObjectPropertyAxiom) ax).getProperty()) + " Characteristic Transitive";
        }
        if (ax instanceof OWLSubPropertyChainOfAxiom) {
            OWLSubPropertyChainOfAxiom a = (OWLSubPropertyChainOfAxiom) ax;
            return a.getPropertyChain().stream().map(Verbalizer::prop)
                    .collect(Collectors.joining(" o ")) + " SubPropertyOf " + prop(a.getSuperProperty());
        }
        if (ax instanceof OWLDeclarationAxiom) {
            OWLEntity e = ((OWLDeclarationAxiom) ax).getEntity();
            return "Declaration " + e.getEntityType().getName() + " " + Naming.localName(e);
        }
        // Anything unrecognised falls back to functional syntax rather than being silently
        // dropped or mangled: an unreadable axiom is better than a wrong one.
        return ax.toString().replaceAll("\\s+", " ").trim();
    }

    public static String expr(OWLClassExpression c) {
        if (!c.isAnonymous()) {
            return Naming.localName(c.asOWLClass());
        }
        if (c instanceof OWLObjectSomeValuesFrom) {
            OWLObjectSomeValuesFrom s = (OWLObjectSomeValuesFrom) c;
            return "(" + prop(s.getProperty()) + " some " + expr(s.getFiller()) + ")";
        }
        if (c instanceof OWLObjectAllValuesFrom) {
            OWLObjectAllValuesFrom s = (OWLObjectAllValuesFrom) c;
            return "(" + prop(s.getProperty()) + " only " + expr(s.getFiller()) + ")";
        }
        if (c instanceof OWLObjectIntersectionOf) {
            return "(" + ((OWLObjectIntersectionOf) c).getOperands().stream()
                    .map(Verbalizer::expr).collect(Collectors.joining(" and ")) + ")";
        }
        if (c instanceof OWLObjectUnionOf) {
            return "(" + ((OWLObjectUnionOf) c).getOperands().stream()
                    .map(Verbalizer::expr).collect(Collectors.joining(" or ")) + ")";
        }
        if (c instanceof OWLObjectComplementOf) {
            return "(not " + expr(((OWLObjectComplementOf) c).getOperand()) + ")";
        }
        if (c instanceof OWLObjectHasValue) {
            OWLObjectHasValue h = (OWLObjectHasValue) c;
            return "(" + prop(h.getProperty()) + " value " + ind(h.getFiller()) + ")";
        }
        return c.toString().replaceAll("\\s+", " ").trim();
    }

    private static String prop(OWLPropertyExpression p) {
        if (p instanceof OWLObjectProperty) {
            return Naming.localName((OWLObjectProperty) p);
        }
        if (p instanceof OWLDataProperty) {
            return Naming.localName((OWLDataProperty) p);
        }
        if (p instanceof OWLObjectInverseOf) {
            return "inverse " + prop(((OWLObjectInverseOf) p).getInverse());
        }
        return p.toString();
    }

    private static String ind(OWLIndividual i) {
        return i.isAnonymous() ? i.toString() : Naming.localName(i.asOWLNamedIndividual());
    }
}
