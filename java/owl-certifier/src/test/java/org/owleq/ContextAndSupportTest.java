package org.owleq;

import org.junit.Test;
import org.owleq.io.ContextParser;
import org.owleq.io.OntologyIO;
import org.owleq.model.BenchmarkItem;
import org.owleq.proof.Justifier;
import org.owleq.proof.SupportValidator;
import org.owleq.query.ContextBuilder;
import org.owleq.query.DatasetBuilder;
import org.owleq.reasoner.ReasonerService;
import org.semanticweb.owlapi.model.*;

import java.util.*;
import java.util.stream.Collectors;

import static org.junit.Assert.*;

/** Context certification, justification minimality and deletion-based support validation. */
public class ContextAndSupportTest {

    private List<BenchmarkItem> buildToyDataset() throws Exception {
        OWLOntology o = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        DatasetBuilder.Config cfg = new DatasetBuilder.Config();
        cfg.ontologyId = "golden";
        cfg.positives = 6;
        cfg.negatives = 6;
        cfg.distractors = 3;
        cfg.maxContextAxioms = 30;
        cfg.conditions = Arrays.asList("C0", "C4", "C7");
        return new DatasetBuilder(o, cfg).build();
    }

    @Test
    public void everyEmittedItemsLabelHoldsAgainstItsOwnContext() throws Exception {
        List<BenchmarkItem> items = buildToyDataset();
        assertFalse("dataset builder produced nothing", items.isEmpty());

        Justifier justifier = new Justifier();
        for (BenchmarkItem item : items) {
            Map<String, OWLAxiom> ctx = ContextParser.parseContext(item);
            assertEquals("context did not round-trip through the parser",
                    item.context.axioms.size(), ctx.size());

            OWLAxiom q = ContextParser.parseAxiom(item.task.queryFunctional);
            boolean entailed = justifier.entails(new LinkedHashSet<>(ctx.values()), q);
            assertEquals(item.orbitItemId + ": stored label disagrees with its context",
                    item.task.positive, entailed);
        }
    }

    @Test
    public void orbitMembersAreStructurallyIdenticalUpToRenaming() throws Exception {
        Map<String, List<BenchmarkItem>> orbits = DatasetBuilder.orbits(buildToyDataset());
        for (Map.Entry<String, List<BenchmarkItem>> e : orbits.entrySet()) {
            List<BenchmarkItem> members = e.getValue();
            int size = members.get(0).context.axioms.size();
            for (BenchmarkItem m : members) {
                assertEquals(e.getKey() + ": orbit members differ in context size",
                        size, m.context.axioms.size());
                assertEquals(e.getKey() + ": orbit members disagree on the label",
                        members.get(0).task.label, m.task.label);
            }
            // Ids must line up positionally: A3 in one variant is the image of A3 in another.
            for (int k = 0; k < size; k++) {
                String id = members.get(0).context.axioms.get(k).id;
                for (BenchmarkItem m : members) {
                    assertEquals("axiom ids drifted between orbit members",
                            id, m.context.axioms.get(k).id);
                }
            }
        }
    }

    @Test
    public void baseItemIdsAreContentAddressedByTheSourceQuery() throws Exception {
        for (BenchmarkItem item : buildToyDataset()) {
            if (!"C0".equals(item.transform.lexicalCondition)) {
                continue;
            }
            String hash = OntologyIO.sha256(item.task.queryFunctional).substring(0, 16);
            assertEquals("base id must survive sample reordering and count changes",
                    "golden:" + item.task.type + ":" + hash, item.baseItemId);
        }
    }

    @Test
    public void repeatedBuildsEmitTheSameOrderedItems() throws Exception {
        List<BenchmarkItem> first = buildToyDataset();
        List<BenchmarkItem> second = buildToyDataset();
        assertEquals(first.size(), second.size());
        for (int i = 0; i < first.size(); i++) {
            assertEquals(first.get(i).orbitItemId, second.get(i).orbitItemId);
            assertEquals(first.get(i).task.queryFunctional, second.get(i).task.queryFunctional);
        }
    }

    @Test
    public void instanceCheckingArmHasMatchedPositiveAndNegativeLabels() throws Exception {
        OWLOntology o = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        DatasetBuilder.Config cfg = new DatasetBuilder.Config();
        cfg.ontologyId = "abox-golden";
        cfg.positives = 0;
        cfg.negatives = 0;
        cfg.instanceQueries = 2;
        cfg.distractors = 2;
        cfg.maxContextAxioms = 30;
        cfg.conditions = Collections.singletonList("C0");

        List<BenchmarkItem> items = new DatasetBuilder(o, cfg).build();
        long positive = items.stream()
                .filter(i -> "INSTANCE_CHECKING".equals(i.task.type) && i.task.positive)
                .count();
        long negative = items.stream()
                .filter(i -> "INSTANCE_CHECKING".equals(i.task.type) && !i.task.positive)
                .count();

        assertTrue("fixture produced no inferred instance query", positive > 0);
        assertEquals("instance task type reveals the label because negatives are missing",
                positive, negative);
    }

    @Test
    public void referenceSupportIsValidAndMinimal() throws Exception {
        List<BenchmarkItem> items = buildToyDataset();
        SupportValidator validator = new SupportValidator();
        int checked = 0;

        for (BenchmarkItem item : items) {
            if (!item.task.positive || item.reference.supportAxiomSets.isEmpty()) {
                continue;
            }
            SupportValidator.Result r =
                    validator.validate(item, item.reference.supportAxiomSets.get(0));
            assertTrue(item.orbitItemId + ": reference support does not entail the query",
                    r.supportValid);
            assertTrue(item.orbitItemId + ": reference support is not minimal, redundant="
                    + r.redundantIds, r.supportMinimal);
            checked++;
        }
        assertTrue("no positive item carried a reference support set", checked > 0);
    }

    @Test
    public void supportValidatorRejectsAnIrrelevantAxiomSet() throws Exception {
        List<BenchmarkItem> items = buildToyDataset();
        BenchmarkItem positive = items.stream()
                .filter(i -> i.task.positive && !i.reference.supportAxiomSets.isEmpty())
                .findFirst()
                .orElseThrow(() -> new AssertionError("no positive item"));

        // Cite axioms that are in the context but are not the ones that carry the entailment.
        Set<String> real = new HashSet<>(positive.reference.supportAxiomSets.get(0));
        List<String> wrong = positive.context.axioms.stream()
                .map(a -> a.id)
                .filter(id -> !real.contains(id))
                .limit(2)
                .collect(Collectors.toList());
        assumeUsable(wrong);

        SupportValidator.Result r = new SupportValidator().validate(positive, wrong);
        assertFalse("an unrelated axiom set was accepted as valid support", r.supportValid);
    }

    @Test
    public void unknownCitedIdsAreReportedNotSilentlyDropped() throws Exception {
        BenchmarkItem item = buildToyDataset().stream()
                .filter(i -> i.task.positive)
                .findFirst()
                .orElseThrow(AssertionError::new);

        SupportValidator.Result r = new SupportValidator()
                .validate(item, Arrays.asList("A1", "A9999", "NOT_AN_ID"));
        assertTrue(r.unknownIds.contains("A9999"));
        assertTrue(r.unknownIds.contains("NOT_AN_ID"));
        assertTrue(r.resolvedIds.contains("A1"));
    }

    /**
     * The locality module must carry every entailment the full ontology has over its own
     * signature. This is the property that makes a non-entailed item mean what it says.
     * Checked for both module types, since either may be used to build contexts.
     */
    @Test
    public void localityModulesAgreeWithTheFullOntologyOnTheirSignature() throws Exception {
        OWLOntology full = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        ContextBuilder cb = new ContextBuilder(full);
        Justifier justifier = new Justifier();

        List<OWLClass> classes = new ArrayList<>(full.getClassesInSignature());
        classes.sort(Comparator.comparing(c -> c.getIRI().toString()));
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        try (ReasonerService rs = new ReasonerService(full)) {
            for (OWLClass a : classes) {
                for (OWLClass b : classes) {
                    if (a.equals(b)) {
                        continue;
                    }
                    OWLSubClassOfAxiom q = df.getOWLSubClassOfAxiom(a, b);
                    boolean expected = rs.isEntailed(q);
                    String label = a.getIRI().getShortForm() + " sub " + b.getIRI().getShortForm();
                    assertEquals("bottom module disagrees with the full ontology on " + label,
                            expected, justifier.entails(cb.queryModule(q.getSignature()), q));
                    assertEquals("star module disagrees with the full ontology on " + label,
                            expected, justifier.entails(cb.starModule(q.getSignature()), q));
                }
            }
        }
    }

    /**
     * The bottom module keeps a usable context for a non-entailed query; the star module
     * does not.
     *
     * <p>This is the reason contexts are built from bottom modules. Both are query-complete,
     * so both give correct labels -- but the star module of two unrelated classes is empty,
     * and an item with no axioms can be answered NOT_ENTAILED without reading anything.
     */
    @Test
    public void bottomModuleKeepsEvidenceWhereTheStarModuleDiscardsIt() throws Exception {
        // Two taxonomies that share nothing. The toy ontology will not do here: its classes
        // are all connected through the property restrictions, so its star modules are not
        // empty. The collapse needs a genuinely unrelated pair, which is the common case on
        // a large ontology and is what produced 59/60 empty negative contexts.
        String disjoint =
                "Prefix(:=<http://example.org/d#>)\n"
                        + "Ontology(<http://example.org/d>\n"
                        + " Declaration(Class(:A)) Declaration(Class(:P))\n"
                        + " Declaration(Class(:C)) Declaration(Class(:Q))\n"
                        + " SubClassOf(:A :P)\n"
                        + " SubClassOf(:C :Q)\n"
                        + ")\n";
        OWLOntology full = GoldenOntologyTest.parse(disjoint);
        ContextBuilder cb = new ContextBuilder(full);
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        OWLSubClassOfAxiom q = df.getOWLSubClassOfAxiom(
                df.getOWLClass(IRI.create("http://example.org/d#A")),
                df.getOWLClass(IRI.create("http://example.org/d#C")));

        assertTrue("bottom module should retain both ancestor chains",
                cb.queryModule(q.getSignature()).size() >= 2);
        assertTrue("star module of an unrelated pair collapses -- the motivating case",
                cb.starModule(q.getSignature()).isEmpty());

        // And the context builder must still produce something to reason over.
        ContextBuilder.Result r = cb.build(q, null, 4, 0,
                ContextBuilder.DistractorKind.NEIGHBOURHOOD, 45, 1L);
        assertFalse("context collapsed to nothing for an unrelated pair", r.axioms.isEmpty());
        assertEquals("provenance must name the module actually used",
                "LOCALITY_MODULE_BOTTOM", r.strategy);
    }

    @Test
    public void contextIsNeverEmptyForAnyQuery() throws Exception {
        OWLOntology full = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        ContextBuilder cb = new ContextBuilder(full);
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        List<OWLClass> classes = new ArrayList<>(full.getClassesInSignature());
        classes.sort(Comparator.comparing(c -> c.getIRI().toString()));

        for (OWLClass a : classes) {
            for (OWLClass b : classes) {
                if (a.equals(b)) {
                    continue;
                }
                OWLSubClassOfAxiom q = df.getOWLSubClassOfAxiom(a, b);
                ContextBuilder.Result r = cb.build(q, null, 8, 0,
                        ContextBuilder.DistractorKind.NEIGHBOURHOOD, 45, 7L);
                assertFalse("empty context for " + OntologyIO.renderAxiom(q)
                        + " -- answerable without evidence", r.axioms.isEmpty());
            }
        }
    }

    /** A taxonomy with enough axioms that a context can actually be padded to a target. */
    private OWLOntology wideTaxonomy(int branches) throws OWLOntologyCreationException {
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();
        Set<OWLAxiom> axioms = new HashSet<>();
        OWLClass root = df.getOWLClass(IRI.create("http://example.org/w#Root"));
        for (int i = 0; i < branches; i++) {
            OWLClass mid = df.getOWLClass(IRI.create("http://example.org/w#Mid" + i));
            OWLClass leaf = df.getOWLClass(IRI.create("http://example.org/w#Leaf" + i));
            axioms.add(df.getOWLSubClassOfAxiom(mid, root));
            axioms.add(df.getOWLSubClassOfAxiom(leaf, mid));
        }
        return org.semanticweb.owlapi.apibinding.OWLManager.createOWLOntologyManager()
                .createOntology(axioms, IRI.create("http://example.org/w"));
    }

    @Test
    public void targetSizeMatchesANegativeContextToItsPositive() throws Exception {
        OWLOntology full = wideTaxonomy(20);   // 40 logical axioms
        ContextBuilder cb = new ContextBuilder(full);
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        // Leaf0 sub Leaf1 is not entailed: two leaves under different parents.
        OWLSubClassOfAxiom negative = df.getOWLSubClassOfAxiom(
                df.getOWLClass(IRI.create("http://example.org/w#Leaf0")),
                df.getOWLClass(IRI.create("http://example.org/w#Leaf1")));

        int moduleSize = cb.queryModule(negative.getSignature()).size();
        for (int target : new int[]{moduleSize, moduleSize + 5, moduleSize + 12}) {
            ContextBuilder.Result r = cb.build(negative, null, 2, target,
                    ContextBuilder.DistractorKind.NEIGHBOURHOOD, 45, 3L);
            assertEquals("negative context did not reach its paired positive's size",
                    target, r.axioms.size());
        }

        // The target is a target, not a licence to discard evidence: a request below the
        // module size yields the module, because dropping relevant axioms to hit a size
        // could change what the item is asking.
        ContextBuilder.Result floored = cb.build(negative, null, 2, 1,
                ContextBuilder.DistractorKind.NEIGHBOURHOOD, 45, 3L);
        assertEquals("target below module size must not drop evidence",
                moduleSize, floored.axioms.size());
    }

    /** Padding is bounded by what the ontology actually contains -- never invented. */
    @Test
    public void contextCannotExceedTheAvailableAxioms() throws Exception {
        OWLOntology full = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        ContextBuilder cb = new ContextBuilder(full);
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        OWLSubClassOfAxiom q = df.getOWLSubClassOfAxiom(
                df.getOWLClass(IRI.create("http://example.org/test#University")),
                df.getOWLClass(IRI.create("http://example.org/test#Employee")));

        ContextBuilder.Result r = cb.build(q, null, 2, 500,
                ContextBuilder.DistractorKind.NEIGHBOURHOOD, 500, 3L);
        assertTrue("context must not exceed the ontology's logical axioms",
                r.axioms.size() <= full.getLogicalAxiomCount());
        assertFalse(r.axioms.isEmpty());
    }

    @Test
    public void distractorsNeverChangeALabel() throws Exception {
        OWLOntology full = GoldenOntologyTest.parse(GoldenOntologyTest.TOY);
        ContextBuilder cb = new ContextBuilder(full);
        Justifier justifier = new Justifier();
        OWLDataFactory df = org.semanticweb.owlapi.apibinding.OWLManager.getOWLDataFactory();

        List<OWLClass> classes = new ArrayList<>(full.getClassesInSignature());
        classes.sort(Comparator.comparing(c -> c.getIRI().toString()));

        try (ReasonerService rs = new ReasonerService(full)) {
            for (OWLClass a : classes) {
                for (OWLClass b : classes) {
                    if (a.equals(b)) {
                        continue;
                    }
                    OWLSubClassOfAxiom q = df.getOWLSubClassOfAxiom(a, b);
                    boolean expected = rs.isEntailed(q);
                    Set<OWLAxiom> j = expected
                            ? justifier.one(cb.queryModule(q.getSignature()), q).orElse(null)
                            : null;
                    for (int d : new int[]{0, 3, 10, 50}) {
                        ContextBuilder.Result r = cb.build(q, j, d, 0,
                                ContextBuilder.DistractorKind.NEIGHBOURHOOD, 60, 7L);
                        assertEquals("distractor count " + d + " changed the label",
                                expected,
                                justifier.entails(new LinkedHashSet<>(r.axioms), q));
                    }
                }
            }
        }
    }

    private static void assumeUsable(List<String> ids) {
        if (ids.size() < 2) {
            throw new AssertionError("fixture too small to build a wrong support set");
        }
    }
}
