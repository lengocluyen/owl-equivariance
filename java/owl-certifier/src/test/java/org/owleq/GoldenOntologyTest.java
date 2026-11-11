package org.owleq;

import org.junit.Test;
import org.owleq.io.OntologyIO;
import org.owleq.reasoner.ReasonerService;
import org.owleq.transform.Condition;
import org.owleq.transform.SignatureIsomorphism;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.io.StringDocumentSource;
import org.semanticweb.owlapi.model.*;

import java.util.*;

import static org.junit.Assert.*;

/**
 * The golden fixture of spec section 35.4: a hand-checked ontology whose expected entailments are
 * obvious to a reader, run through every transform.
 *
 * <p>If any condition changes any of these answers, the transform is broken -- no statistics
 * required to see it.
 */
public class GoldenOntologyTest {

    static final String TOY =
            "Prefix(:=<http://example.org/test#>)\n"
                    + "Prefix(rdfs:=<http://www.w3.org/2000/01/rdf-schema#>)\n"
                    + "Ontology(<http://example.org/test>\n"
                    + " Declaration(Class(:Professor))\n"
                    + " Declaration(Class(:Employee))\n"
                    + " Declaration(Class(:Person))\n"
                    + " Declaration(Class(:University))\n"
                    + " Declaration(ObjectProperty(:worksFor))\n"
                    + " Declaration(NamedIndividual(:Alice))\n"
                    + " Declaration(NamedIndividual(:UTC))\n"
                    + " SubClassOf(:Professor :Employee)\n"
                    + " SubClassOf(:Employee :Person)\n"
                    + " ObjectPropertyDomain(:worksFor :Employee)\n"
                    + " ObjectPropertyRange(:worksFor :University)\n"
                    + " ClassAssertion(:Professor :Alice)\n"
                    + " ClassAssertion(:University :UTC)\n"
                    + " ObjectPropertyAssertion(:worksFor :Alice :UTC)\n"
                    + " AnnotationAssertion(rdfs:label :Professor \"professor\")\n"
                    + " AnnotationAssertion(rdfs:label :Employee \"employee\")\n"
                    + " AnnotationAssertion(rdfs:label :Person \"person\")\n"
                    + ")\n";

    static OWLOntology parse(String doc) throws OWLOntologyCreationException {
        return OWLManager.createOWLOntologyManager()
                .loadOntologyFromOntologyDocument(new StringDocumentSource(doc));
    }

    private static final String NS = "http://example.org/test#";

    /** The four expectations from spec section 49, as (query, expected entailment). */
    private static Map<OWLAxiom, Boolean> expectations(OWLDataFactory df) {
        OWLClass professor = df.getOWLClass(IRI.create(NS + "Professor"));
        OWLClass person = df.getOWLClass(IRI.create(NS + "Person"));
        OWLClass university = df.getOWLClass(IRI.create(NS + "University"));
        OWLClass employee = df.getOWLClass(IRI.create(NS + "Employee"));
        OWLNamedIndividual alice = df.getOWLNamedIndividual(IRI.create(NS + "Alice"));

        Map<OWLAxiom, Boolean> m = new LinkedHashMap<>();
        m.put(df.getOWLSubClassOfAxiom(professor, person), true);
        m.put(df.getOWLClassAssertionAxiom(person, alice), true);
        m.put(df.getOWLClassAssertionAxiom(university, alice), false);
        m.put(df.getOWLSubClassOfAxiom(university, employee), false);
        return m;
    }

    @Test
    public void sourceOntologyHasTheExpectedEntailments() throws Exception {
        OWLOntology o = parse(TOY);
        OWLDataFactory df = OWLManager.getOWLDataFactory();
        try (ReasonerService rs = new ReasonerService(o)) {
            expectations(df).forEach((q, expected) ->
                    assertEquals(OntologyIO.renderAxiom(q), expected, rs.isEntailed(q)));
        }
    }

    @Test
    public void everyConditionPreservesEveryGoldenAnswer() throws Exception {
        OWLOntology source = parse(TOY);
        OWLDataFactory df = OWLManager.getOWLDataFactory();
        Map<OWLAxiom, Boolean> expected = expectations(df);

        for (String id : Arrays.asList("C0", "C1", "C2", "C3", "C4", "C4S2", "C4S3",
                "C5", "C5F1", "C5F2", "C6", "C7", "C8", "C9")) {
            Condition c = Condition.of(id);
            SignatureIsomorphism iso = c.isomorphism(source, "urn:owleq:test:");
            OWLOntology target = iso.apply(source);
            try (ReasonerService rs = new ReasonerService(target)) {
                for (Map.Entry<OWLAxiom, Boolean> e : expected.entrySet()) {
                    OWLAxiom mapped = iso.transform(e.getKey());
                    assertEquals(id + " changed the answer to " + OntologyIO.renderAxiom(e.getKey()),
                            e.getValue(), rs.isEntailed(mapped));
                }
            }
        }
    }

    @Test
    public void renamingActuallyRemovesTheOriginalNames() throws Exception {
        OWLOntology source = parse(TOY);
        SignatureIsomorphism iso = Condition.of("C4").isomorphism(source, "urn:owleq:test:");
        String text = OntologyIO.canonicalText(iso.apply(source));

        for (String name : Arrays.asList("Professor", "Employee", "Person", "University",
                "worksFor", "Alice", "professor", "employee")) {
            assertFalse("C4 leaked the original name " + name, text.contains(name));
        }
    }

    @Test
    public void adversarialDecoyReusesRealNamesButNeverAnEntitysOwn() throws Exception {
        OWLOntology source = parse(TOY);
        SignatureIsomorphism iso = Condition.of("C7").isomorphism(source, "urn:owleq:test:");

        int moved = 0;
        for (Map.Entry<OWLEntity, IRI> e : iso.forwardMap().entrySet()) {
            String before = org.owleq.transform.Naming.localName(e.getKey());
            String after = org.owleq.transform.Naming.localName(e.getValue());
            if (!before.equals(after)) {
                moved++;
            }
        }
        // The point of O4 is that names are swapped, not erased; a mapping that left most
        // entities alone would not be adversarial at all.
        assertTrue("adversarial decoy left too many names in place: " + moved + "/"
                + iso.size(), moved >= iso.size() - 2);
    }

    /**
     * Two seeds of the same operator must produce genuinely different aliases.
     *
     * <p>C4 and C4S2 exist to ask whether a model answers two logically indistinguishable
     * renamings the same way. If both seeds yield the same mapping they are one condition
     * under two names, and the measured "self-consistency" is a run compared against itself.
     */
    @Test
    public void differentSeedsOfTheSameOperatorProduceDifferentMappings() throws Exception {
        OWLOntology source = parse(TOY);
        SignatureIsomorphism a = Condition.of("C4").isomorphism(source, "urn:owleq:");
        SignatureIsomorphism b = Condition.of("C4S2").isomorphism(source, "urn:owleq:");

        int differing = 0;
        for (Map.Entry<OWLEntity, IRI> e : a.forwardMap().entrySet()) {
            IRI other = b.forwardMap().get(e.getKey());
            assertNotNull("both conditions must map the same entity set", other);
            if (!e.getValue().equals(other)) {
                differing++;
            }
        }
        assertTrue("C4 and C4S2 assign identical names to every entity: they are the same "
                + "condition twice", differing > 0);
    }

    /** The same seed must still reproduce exactly, or nothing is reproducible. */
    @Test
    public void theSameSeedReproducesTheSameMapping() throws Exception {
        OWLOntology source = parse(TOY);
        SignatureIsomorphism a = Condition.of("C4").isomorphism(source, "urn:owleq:");
        SignatureIsomorphism b = Condition.of("C4").isomorphism(source, "urn:owleq:");
        assertEquals(a.forwardMap(), b.forwardMap());
    }

    /**
     * No condition id or seed may appear in the IRIs, because those IRIs are printed in the
     * prompt and would tell the model which experimental cell it is in.
     */
    @Test
    public void namespacesDoNotLeakTheConditionOrSeed() throws Exception {
        OWLOntology source = parse(TOY);
        for (String id : Arrays.asList("C1", "C4", "C4S2", "C5", "C6", "C7", "C8")) {
            Condition c = Condition.of(id);
            SignatureIsomorphism iso = c.isomorphism(source, "urn:owleq:");
            String text = OntologyIO.canonicalText(iso.apply(source)).toLowerCase(Locale.ROOT);
            assertFalse(id + " leaks its condition id into the vocabulary",
                    text.contains(":" + id.toLowerCase(Locale.ROOT) + ":"));
            assertFalse(id + " leaks its seed into the vocabulary",
                    text.contains(":" + c.seed + ":"));
        }
    }

    /**
     * The adversarial operator must produce readable concept names, not accession codes.
     *
     * <p>On an OBO-style ontology the IRI local names are numbers, so permuting them would
     * swap meaningless tokens and C7 would silently become a second opaque condition.
     */
    @Test
    public void adversarialDecoyNamesComeFromLabelsNotAccessionCodes() throws Exception {
        String obo =
                "Prefix(:=<http://purl.obolibrary.org/obo/>)\n"
                        + "Prefix(rdfs:=<http://www.w3.org/2000/01/rdf-schema#>)\n"
                        + "Ontology(<http://example.org/obo>\n"
                        + " Declaration(Class(:CL_0000540))\n"
                        + " Declaration(Class(:CL_0000235))\n"
                        + " Declaration(Class(:CL_0000000))\n"
                        + " SubClassOf(:CL_0000540 :CL_0000000)\n"
                        + " SubClassOf(:CL_0000235 :CL_0000000)\n"
                        + " AnnotationAssertion(rdfs:label :CL_0000540 \"neuron\")\n"
                        + " AnnotationAssertion(rdfs:label :CL_0000235 \"macrophage\")\n"
                        + " AnnotationAssertion(rdfs:label :CL_0000000 \"cell\")\n"
                        + ")\n";
        OWLOntology source = parse(obo);
        SignatureIsomorphism iso = Condition.of("C7").isomorphism(source, "urn:owleq:");

        Set<String> names = new HashSet<>();
        for (IRI target : iso.forwardMap().values()) {
            names.add(org.owleq.transform.Naming.localName(target));
        }
        assertTrue("adversarial names should be label-derived, e.g. Neuron / Macrophage / Cell; "
                        + "got " + names,
                names.contains("Neuron") || names.contains("Macrophage") || names.contains("Cell"));
        for (String n : names) {
            assertFalse("adversarial decoy reused an accession code: " + n, n.startsWith("CL_"));
        }
    }

    @Test
    public void opaqueLabelsPolicyRemovesMeaningButKeepsALabel() throws Exception {
        OWLOntology source = parse(TOY);
        SignatureIsomorphism iso = Condition.of("C8").isomorphism(source, "urn:owleq:test:");
        OWLOntology target = iso.apply(source);

        long labels = target.getAxioms(AxiomType.ANNOTATION_ASSERTION).size();
        assertTrue("C8 should attach a misleading label to every entity", labels >= iso.size());

        String text = OntologyIO.canonicalText(target);
        assertFalse("C8 kept an original IRI local name", text.contains("#Professor>"));
    }
}
