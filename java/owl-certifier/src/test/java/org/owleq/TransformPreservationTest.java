package org.owleq;

import org.junit.Test;
import org.owleq.io.OntologyIO;
import org.owleq.reasoner.ReasonerService;
import org.owleq.transform.*;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;

import java.util.*;

import static org.junit.Assert.*;

/**
 * Constructor-level round-trip tests (spec section 14.1) and randomised preservation tests
 * (spec section 35.5).
 *
 * <p>Round-tripping every OWL constructor separately is what catches the realistic failure mode:
 * a rewriter that handles {@code SubClassOf} correctly and quietly drops the filler of a nested
 * existential restriction.
 */
public class TransformPreservationTest {

    private final OWLDataFactory df = OWLManager.getOWLDataFactory();
    private static final String NS = "http://example.org/fixture#";

    private OWLClass c(String n) {
        return df.getOWLClass(IRI.create(NS + n));
    }

    private OWLObjectProperty p(String n) {
        return df.getOWLObjectProperty(IRI.create(NS + n));
    }

    private OWLNamedIndividual i(String n) {
        return df.getOWLNamedIndividual(IRI.create(NS + n));
    }

    private OWLDataProperty dp(String n) {
        return df.getOWLDataProperty(IRI.create(NS + n));
    }

    private OWLOntology ontologyOf(OWLAxiom... axioms) throws OWLOntologyCreationException {
        return OWLManager.createOWLOntologyManager()
                .createOntology(new HashSet<>(Arrays.asList(axioms)), IRI.create(NS + "o"));
    }

    /** One fixture per constructor named in spec section 14.1. */
    private Map<String, OWLOntology> constructorFixtures() throws OWLOntologyCreationException {
        Map<String, OWLOntology> f = new LinkedHashMap<>();
        f.put("subclass", ontologyOf(df.getOWLSubClassOfAxiom(c("A"), c("B"))));
        f.put("equivalence", ontologyOf(df.getOWLEquivalentClassesAxiom(c("A"), c("B"))));
        f.put("disjointness", ontologyOf(df.getOWLDisjointClassesAxiom(c("A"), c("B"))));
        f.put("existential", ontologyOf(df.getOWLSubClassOfAxiom(
                c("A"), df.getOWLObjectSomeValuesFrom(p("r"), c("B")))));
        f.put("nested-existential", ontologyOf(df.getOWLSubClassOfAxiom(
                c("A"), df.getOWLObjectSomeValuesFrom(p("r"),
                        df.getOWLObjectSomeValuesFrom(p("s"), c("B"))))));
        f.put("conjunction", ontologyOf(df.getOWLSubClassOfAxiom(
                c("A"), df.getOWLObjectIntersectionOf(c("B"), c("C")))));
        f.put("conjunction-of-existentials", ontologyOf(df.getOWLSubClassOfAxiom(
                c("A"), df.getOWLObjectIntersectionOf(
                        df.getOWLObjectSomeValuesFrom(p("r"), c("B")), c("C")))));
        f.put("property-hierarchy", ontologyOf(df.getOWLSubObjectPropertyOfAxiom(p("r"), p("s"))));
        f.put("transitivity", ontologyOf(df.getOWLTransitiveObjectPropertyAxiom(p("r"))));
        f.put("property-chain", ontologyOf(df.getOWLSubPropertyChainOfAxiom(
                Arrays.asList(p("r"), p("s")), p("t"))));
        f.put("domain-range", ontologyOf(
                df.getOWLObjectPropertyDomainAxiom(p("r"), c("A")),
                df.getOWLObjectPropertyRangeAxiom(p("r"), c("B"))));
        f.put("class-assertion", ontologyOf(df.getOWLClassAssertionAxiom(c("A"), i("a"))));
        f.put("property-assertion", ontologyOf(
                df.getOWLObjectPropertyAssertionAxiom(p("r"), i("a"), i("b"))));
        f.put("data-property-assertion", ontologyOf(
                df.getOWLDataPropertyAssertionAxiom(dp("d"), i("a"), df.getOWLLiteral(7))));
        f.put("data-property-domain", ontologyOf(
                df.getOWLDataPropertyDomainAxiom(dp("d"), c("A"))));
        f.put("has-value", ontologyOf(df.getOWLSubClassOfAxiom(
                c("A"), df.getOWLObjectHasValue(p("r"), i("b")))));
        return f;
    }

    @Test
    public void everyConstructorRoundTripsExactly() throws Exception {
        for (Map.Entry<String, OWLOntology> e : constructorFixtures().entrySet()) {
            OWLOntology source = e.getValue();
            for (String cond : Arrays.asList("C4", "C5", "C6", "C7")) {
                SignatureIsomorphism iso =
                        Condition.of(cond).isomorphism(source, "urn:owleq:t:");
                OWLOntology target = iso.apply(source);

                Set<OWLAxiom> back = new HashSet<>();
                for (OWLAxiom ax : target.getLogicalAxioms()) {
                    back.add(iso.inverse(ax));
                }
                OWLOntology restored = OWLManager.createOWLOntologyManager().createOntology(back);

                assertEquals(e.getKey() + " under " + cond + " did not round-trip",
                        OntologyIO.canonicalLogicalText(source),
                        OntologyIO.canonicalLogicalText(restored));
            }
        }
    }

    @Test
    public void annotationPoliciesNeverTouchLogicalAxioms() throws Exception {
        OWLOntology source = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        String logicalBefore = OntologyIO.canonicalLogicalText(source);

        for (AnnotationPolicy policy : AnnotationPolicy.values()) {
            SignatureIsomorphism iso = SignatureIsomorphism.identity(source, policy);
            OWLOntology target = iso.apply(source);
            assertEquals("policy " + policy + " modified the logical axiom set",
                    logicalBefore, OntologyIO.canonicalLogicalText(target));
        }
    }

    /**
     * A pun -- one IRI used as both a class and an individual -- must survive as two independent
     * entities. Keying the mapping on the IRI alone would collapse them.
     */
    @Test
    public void punnedIriIsMappedIndependentlyPerType() throws Exception {
        IRI shared = IRI.create(NS + "Shared");
        OWLOntology source = ontologyOf(
                df.getOWLDeclarationAxiom(df.getOWLClass(shared)),
                df.getOWLDeclarationAxiom(df.getOWLNamedIndividual(shared)),
                df.getOWLSubClassOfAxiom(df.getOWLClass(shared), c("B")),
                df.getOWLClassAssertionAxiom(c("B"), df.getOWLNamedIndividual(shared)));

        SignatureIsomorphism iso = Condition.of("C4").isomorphism(source, "urn:owleq:t:");
        IRI classImage = iso.forwardMap().get(df.getOWLClass(shared));
        IRI individualImage = iso.forwardMap().get(df.getOWLNamedIndividual(shared));

        assertNotNull("class side of the pun was not mapped", classImage);
        assertNotNull("individual side of the pun was not mapped", individualImage);
        assertNotEquals("pun collapsed: both sides got the same IRI", classImage, individualImage);

        // And the split must be reversible.
        Set<OWLAxiom> back = new HashSet<>();
        for (OWLAxiom ax : iso.apply(source).getLogicalAxioms()) {
            back.add(iso.inverse(ax));
        }
        OWLOntology restored = OWLManager.createOWLOntologyManager().createOntology(back);
        assertEquals(OntologyIO.canonicalLogicalText(source),
                OntologyIO.canonicalLogicalText(restored));
    }

    @Test
    public void identityMappingWorksOnPunnedOntologies() throws Exception {
        IRI shared = IRI.create(NS + "Shared");
        OWLOntology source = ontologyOf(
                df.getOWLSubClassOfAxiom(df.getOWLClass(shared), c("B")),
                df.getOWLClassAssertionAxiom(c("B"), df.getOWLNamedIndividual(shared)));

        // Would throw if injectivity were checked globally rather than per entity type.
        SignatureIsomorphism iso =
                SignatureIsomorphism.identity(source, AnnotationPolicy.REMOVE_ALL_LEXICAL);
        assertEquals(OntologyIO.canonicalLogicalText(source),
                OntologyIO.canonicalLogicalText(iso.apply(source)));
    }

    /**
     * Randomised check (spec section 35.5): random small EL ontologies, random typed bijections,
     * sampled queries. Preservation is a theorem, so any counterexample is an implementation bug.
     */
    @Test
    public void randomElOntologiesPreserveSampledLabels() throws Exception {
        for (int trial = 0; trial < 12; trial++) {
            long seed = 1000L + trial;
            OWLOntology source = randomElOntology(seed, 12, 3);
            SignatureIsomorphism iso = Condition.of(trial % 2 == 0 ? "C4" : "C7")
                    .isomorphism(source, "urn:owleq:rand:");
            OWLOntology target = iso.apply(source);

            List<OWLAxiom> queries = sampleQueries(source, seed);
            try (ReasonerService src = new ReasonerService(source);
                 ReasonerService tgt = new ReasonerService(target)) {
                for (OWLAxiom q : queries) {
                    assertEquals("trial " + trial + ": label moved for "
                                    + OntologyIO.renderAxiom(q),
                            src.isEntailed(q), tgt.isEntailed(iso.transform(q)));
                }
            }
        }
    }

    private OWLOntology randomElOntology(long seed, int classCount, int propCount)
            throws OWLOntologyCreationException {
        Random rnd = new Random(seed);
        Set<OWLAxiom> axioms = new HashSet<>();
        for (int k = 0; k < classCount; k++) {
            axioms.add(df.getOWLDeclarationAxiom(c("K" + k)));
        }
        for (int k = 0; k < propCount; k++) {
            axioms.add(df.getOWLDeclarationAxiom(p("q" + k)));
        }
        for (int k = 0; k < classCount * 2; k++) {
            OWLClass a = c("K" + rnd.nextInt(classCount));
            OWLClass b = c("K" + rnd.nextInt(classCount));
            if (a.equals(b)) {
                continue;
            }
            switch (rnd.nextInt(4)) {
                case 0:
                    axioms.add(df.getOWLSubClassOfAxiom(a, b));
                    break;
                case 1:
                    axioms.add(df.getOWLSubClassOfAxiom(a, df.getOWLObjectSomeValuesFrom(
                            p("q" + rnd.nextInt(propCount)), b)));
                    break;
                case 2:
                    axioms.add(df.getOWLSubClassOfAxiom(
                            df.getOWLObjectSomeValuesFrom(p("q" + rnd.nextInt(propCount)), a), b));
                    break;
                default:
                    axioms.add(df.getOWLSubClassOfAxiom(
                            a, df.getOWLObjectIntersectionOf(b, c("K" + rnd.nextInt(classCount)))));
            }
        }
        axioms.add(df.getOWLClassAssertionAxiom(c("K0"), i("x")));
        return OWLManager.createOWLOntologyManager()
                .createOntology(axioms, IRI.create(NS + "rand" + seed));
    }

    /** A mix of likely-entailed and likely-non-entailed queries, so both directions are exercised. */
    private List<OWLAxiom> sampleQueries(OWLOntology o, long seed) {
        Random rnd = new Random(seed * 7);
        List<OWLClass> classes = new ArrayList<>(o.getClassesInSignature());
        classes.sort(Comparator.comparing(x -> x.getIRI().toString()));
        List<OWLAxiom> qs = new ArrayList<>();
        for (int k = 0; k < 25 && classes.size() >= 2; k++) {
            OWLClass a = classes.get(rnd.nextInt(classes.size()));
            OWLClass b = classes.get(rnd.nextInt(classes.size()));
            qs.add(df.getOWLSubClassOfAxiom(a, b));
        }
        for (OWLClass a : classes.subList(0, Math.min(4, classes.size()))) {
            qs.add(df.getOWLClassAssertionAxiom(a, i("x")));
        }
        return qs;
    }
}
