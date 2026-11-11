package org.owleq;

import org.junit.Test;
import org.owleq.proof.Justifier;
import org.owleq.reasoner.ReasonerService;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;

import java.util.*;

import static org.junit.Assert.*;

/** Deterministic complexity regressions for the large-ontology justification path. */
public class LargeOntologyPerformanceTest {

    private static final class Fixture {
        final Set<OWLAxiom> axioms;
        final OWLSubClassOfAxiom query;
        final Set<OWLAxiom> expectedProof;

        Fixture(Set<OWLAxiom> axioms, OWLSubClassOfAxiom query,
                Set<OWLAxiom> expectedProof) {
            this.axioms = axioms;
            this.query = query;
            this.expectedProof = expectedProof;
        }
    }

    /**
     * A small proof embedded in a much wider ontology. The former deletion algorithm required
     * at least one classification per candidate axiom; QuickXplain must stay well below half of
     * that structural bound. This checks calls rather than wall time, so loaded CI hosts do not
     * make the regression flaky.
     */
    @Test(timeout = 120000)
    public void quickXplainIsSublinearForASparseProofInAWideOntology() throws Exception {
        Fixture fixture = wideFixture(96, 7); // 199 logical axioms; proof size 7
        Justifier justifier = new Justifier();

        Optional<Set<OWLAxiom>> result = justifier.one(
                fixture.axioms, fixture.query, 128);

        assertTrue("bounded QuickXplain failed to find the sparse proof", result.isPresent());
        assertEquals("the unique chain proof changed", fixture.expectedProof, result.get());
        assertTrue("reasoner calls regressed toward linear deletion: "
                        + justifier.lastCallCount(),
                justifier.lastCallCount() < fixture.axioms.size() / 2);
        assertEquals("one justification search should reuse one manager/working ontology",
                1, justifier.lastOracleInitializationCount());
        assertEquals("each uncached entailment check builds exactly one fresh reasoner",
                justifier.lastCallCount(), justifier.lastReasonerBuildCount());
        assertFalse(justifier.lastBudgetExhausted());

        // Verify minimality independently of the extraction algorithm.
        for (OWLAxiom axiom : result.get()) {
            Set<OWLAxiom> without = new LinkedHashSet<>(result.get());
            without.remove(axiom);
            assertFalse("returned support is not minimal",
                    new Justifier().entails(without, fixture.query));
        }
        assertTrue(new Justifier().entails(result.get(), fixture.query));
    }

    @Test(timeout = 30000)
    public void perCandidateBudgetStopsDeterministicallyWithoutPartialSupport() {
        Fixture fixture = wideFixture(12, 5);
        Justifier first = new Justifier();
        Justifier second = new Justifier();

        Optional<Set<OWLAxiom>> a = first.one(fixture.axioms, fixture.query, 3);
        Optional<Set<OWLAxiom>> b = second.one(fixture.axioms, fixture.query, 3);

        assertFalse("budget exhaustion must not return a partial non-minimal support",
                a.isPresent());
        assertFalse(b.isPresent());
        assertTrue(first.lastBudgetExhausted());
        assertTrue(second.lastBudgetExhausted());
        assertEquals(3, first.lastCallCount());
        assertEquals(first.lastCallCount(), second.lastCallCount());
        assertEquals(first.lastReasonerBuildCount(), second.lastReasonerBuildCount());
    }

    private Fixture wideFixture(int branches, int proofLength) {
        OWLDataFactory dataFactory = OWLManager.getOWLDataFactory();
        Set<OWLAxiom> axioms = new LinkedHashSet<>();
        Set<OWLAxiom> proof = new LinkedHashSet<>();

        OWLClass first = cls(dataFactory, "Proof0");
        OWLClass previous = first;
        for (int i = 1; i <= proofLength; i++) {
            OWLClass next = cls(dataFactory, "Proof" + i);
            OWLAxiom link = dataFactory.getOWLSubClassOfAxiom(previous, next);
            proof.add(link);
            axioms.add(link);
            previous = next;
        }

        for (int i = 0; i < branches; i++) {
            OWLClass leaf = cls(dataFactory, "NoiseLeaf" + i);
            OWLClass middle = cls(dataFactory, "NoiseMiddle" + i);
            OWLClass root = cls(dataFactory, "NoiseRoot" + i);
            axioms.add(dataFactory.getOWLSubClassOfAxiom(leaf, middle));
            axioms.add(dataFactory.getOWLSubClassOfAxiom(middle, root));
        }
        OWLSubClassOfAxiom query = dataFactory.getOWLSubClassOfAxiom(first, previous);

        // Guard the fixture itself against an accidental unsupported reasoner case.
        try {
            OWLOntology ontology = OWLManager.createOWLOntologyManager().createOntology(axioms);
            try (ReasonerService reasoner = new ReasonerService(ontology)) {
                assertTrue(reasoner.isEntailed(query));
            }
        } catch (OWLOntologyCreationException e) {
            throw new AssertionError(e);
        }
        return new Fixture(axioms, query, proof);
    }

    private OWLClass cls(OWLDataFactory dataFactory, String localName) {
        return dataFactory.getOWLClass(IRI.create("http://example.org/perf#" + localName));
    }
}
