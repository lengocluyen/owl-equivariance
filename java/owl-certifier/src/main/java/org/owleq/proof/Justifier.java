package org.owleq.proof;

import org.owleq.io.OntologyIO;
import org.owleq.reasoner.ReasonerService;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;

import java.util.*;

/**
 * Minimal entailing-subset computation against the symbolic reasoner.
 *
 * <p>The original implementation removed axioms one at a time and constructed a fresh OWL
 * manager, ontology and ELK reasoner after every removal. That is linear in the module size even
 * when the actual justification is tiny, and it made large ontologies such as Uberon spend days
 * rebuilding nearly identical reasoners. This implementation uses deterministic QuickXplain:
 * it divides the candidate set and normally needs O(k log(n/k)) entailment checks for a
 * justification of size k inside n candidate axioms.
 *
 * <p>Every entailment check remains an independent ELK classification, so correctness does not
 * depend on incremental-reasoner behaviour. Within one justification search, however, the OWL
 * manager, mutable ontology, query declarations and exact-subset cache are reused. A caller-set
 * reasoner-call budget bounds every candidate deterministically; exhausting it returns no
 * justification and is exposed through {@link #lastBudgetExhausted()} rather than silently
 * accepting a non-minimal support.
 */
public final class Justifier {

    private static final int DEFAULT_MAX_JUSTIFICATIONS = 5;
    private static final int DEFAULT_CALL_BUDGET = 3000;

    private int calls;
    private int reasonerBuilds;
    private int cacheHits;
    private int oracleInitializations;
    private int activeCallBudget = Integer.MAX_VALUE;
    private boolean budgetExhausted;

    /** One minimal justification with the historical generous default budget. */
    public Optional<Set<OWLAxiom>> one(Set<OWLAxiom> from, OWLAxiom q) {
        return one(from, q, DEFAULT_CALL_BUDGET);
    }

    /**
     * One minimal justification, bounded by {@code callBudget} new reasoner invocations.
     *
     * <p>An empty result means either that {@code from} does not entail {@code q}, or that the
     * deterministic budget was exhausted. Callers that use a restrictive budget must inspect
     * {@link #lastBudgetExhausted()} and report the latter separately.
     */
    public Optional<Set<OWLAxiom>> one(Set<OWLAxiom> from, OWLAxiom q, int callBudget) {
        if (callBudget < 1) {
            throw new IllegalArgumentException("reasoner call budget must be at least 1");
        }
        reset(callBudget);
        try {
            return minimalSubset(from, q);
        } catch (BudgetExceededException e) {
            budgetExhausted = true;
            return Optional.empty();
        }
    }

    /**
     * Up to {@code max} distinct justifications, via a bounded Reiter hitting-set traversal.
     * Each minimal subset is found with QuickXplain and all branches share the same call budget.
     */
    public List<Set<OWLAxiom>> all(Set<OWLAxiom> from, OWLAxiom q) {
        return all(from, q, DEFAULT_MAX_JUSTIFICATIONS, DEFAULT_CALL_BUDGET);
    }

    public List<Set<OWLAxiom>> all(Set<OWLAxiom> from, OWLAxiom q, int max, int callBudget) {
        if (max < 1 || callBudget < 1) {
            throw new IllegalArgumentException("max and reasoner call budget must be positive");
        }
        reset(callBudget);
        List<Set<OWLAxiom>> found = new ArrayList<>();
        Deque<Set<OWLAxiom>> removedPaths = new ArrayDeque<>();
        removedPaths.push(new LinkedHashSet<>());
        Set<Set<OWLAxiom>> seen = new HashSet<>();

        try {
            while (!removedPaths.isEmpty() && found.size() < max) {
                Set<OWLAxiom> removed = removedPaths.pop();
                if (!seen.add(removed)) {
                    continue;
                }
                Set<OWLAxiom> remaining = new LinkedHashSet<>(from);
                remaining.removeAll(removed);
                Optional<Set<OWLAxiom>> candidate = minimalSubset(remaining, q);
                if (!candidate.isPresent()) {
                    continue;
                }
                Set<OWLAxiom> justification = candidate.get();
                if (found.stream().noneMatch(justification::equals)) {
                    found.add(justification);
                }
                for (OWLAxiom axiom : justification) {
                    Set<OWLAxiom> next = new LinkedHashSet<>(removed);
                    next.add(axiom);
                    removedPaths.push(next);
                }
            }
        } catch (BudgetExceededException e) {
            budgetExhausted = true;
        }
        return found;
    }

    public int lastCallCount() {
        return calls;
    }

    public int lastReasonerBuildCount() {
        return reasonerBuilds;
    }

    public int lastCacheHitCount() {
        return cacheHits;
    }

    /** Number of OWL managers/working ontologies created by the last search. */
    public int lastOracleInitializationCount() {
        return oracleInitializations;
    }

    public boolean lastBudgetExhausted() {
        return budgetExhausted;
    }

    /**
     * Direct entailment check used for small supplied contexts and support validation.
     * Diagnostics accumulate across consecutive calls, matching the historical API.
     */
    public boolean entails(Set<OWLAxiom> axioms, OWLAxiom q) {
        calls++;
        reasonerBuilds++;
        try {
            OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
            Set<OWLAxiom> withDeclarations = withQueryDeclarations(manager, axioms, q);
            OWLOntology ontology = manager.createOntology(withDeclarations);
            try (ReasonerService reasoner = new ReasonerService(ontology)) {
                return reasoner.isEntailed(q);
            }
        } catch (OWLOntologyCreationException e) {
            throw new IllegalStateException(e);
        }
    }

    private void reset(int callBudget) {
        calls = 0;
        reasonerBuilds = 0;
        cacheHits = 0;
        oracleInitializations = 0;
        budgetExhausted = false;
        activeCallBudget = callBudget;
    }

    private Optional<Set<OWLAxiom>> minimalSubset(Set<OWLAxiom> from, OWLAxiom q) {
        List<OWLAxiom> ordered = new ArrayList<>(from);
        ordered.sort(Comparator.comparing(OntologyIO::renderAxiom));
        if (ordered.isEmpty()) {
            return Optional.empty();
        }

        try (SubsetOracle oracle = new SubsetOracle(ordered, q)) {
            BitSet all = new BitSet(ordered.size());
            all.set(0, ordered.size());
            if (!oracle.entails(all)) {
                return Optional.empty();
            }
            BitSet minimal = quickXplain(new BitSet(), all, oracle);
            Set<OWLAxiom> result = new LinkedHashSet<>();
            for (int i = minimal.nextSetBit(0); i >= 0; i = minimal.nextSetBit(i + 1)) {
                result.add(ordered.get(i));
            }
            return Optional.of(result);
        } catch (OWLOntologyCreationException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Deterministic QuickXplain over an entailment-monotone candidate set. */
    private BitSet quickXplain(BitSet background, BitSet candidates, SubsetOracle oracle) {
        if (candidates.isEmpty() || oracle.entails(background)) {
            return new BitSet();
        }
        if (candidates.cardinality() == 1) {
            return (BitSet) candidates.clone();
        }

        BitSet left = new BitSet();
        BitSet right = new BitSet();
        int split = candidates.cardinality() / 2;
        int seen = 0;
        for (int i = candidates.nextSetBit(0); i >= 0; i = candidates.nextSetBit(i + 1)) {
            (seen++ < split ? left : right).set(i);
        }

        BitSet neededLeft = quickXplain(union(background, right), left, oracle);
        BitSet neededRight = quickXplain(union(background, neededLeft), right, oracle);
        neededLeft.or(neededRight);
        return neededLeft;
    }

    private static BitSet union(BitSet first, BitSet second) {
        BitSet out = (BitSet) first.clone();
        out.or(second);
        return out;
    }

    private static Set<OWLAxiom> withQueryDeclarations(OWLOntologyManager manager,
                                                       Collection<OWLAxiom> axioms,
                                                       OWLAxiom query) {
        Set<OWLAxiom> out = new LinkedHashSet<>(axioms);
        OWLDataFactory dataFactory = manager.getOWLDataFactory();
        for (OWLEntity entity : query.getSignature()) {
            if (!entity.isBuiltIn()) {
                out.add(dataFactory.getOWLDeclarationAxiom(entity));
            }
        }
        return out;
    }

    /**
     * Exact-subset entailment oracle. It reuses one manager and ontology and caches repeated
     * subsets, while constructing a fresh reasoner for each genuinely new subset so that the
     * result never depends on incremental-classification support in the pinned ELK version.
     */
    private final class SubsetOracle implements AutoCloseable {
        private final List<OWLAxiom> candidates;
        private final OWLAxiom query;
        private final OWLOntologyManager manager;
        private final OWLOntology ontology;
        private final Set<OWLAxiom> declarations;
        private final Map<BitSet, Boolean> cache = new HashMap<>();
        private Set<OWLAxiom> currentAxioms;

        SubsetOracle(List<OWLAxiom> candidates, OWLAxiom query)
                throws OWLOntologyCreationException {
            this.candidates = candidates;
            this.query = query;
            oracleInitializations++;
            this.manager = OWLManager.createOWLOntologyManager();
            this.declarations = withQueryDeclarations(manager, Collections.emptySet(), query);
            this.currentAxioms = new LinkedHashSet<>(declarations);
            this.ontology = manager.createOntology(currentAxioms);
        }

        boolean entails(BitSet selected) {
            BitSet key = (BitSet) selected.clone();
            Boolean cached = cache.get(key);
            if (cached != null) {
                cacheHits++;
                return cached;
            }
            if (calls >= activeCallBudget) {
                throw new BudgetExceededException();
            }

            Set<OWLAxiom> target = new LinkedHashSet<>(declarations);
            for (int i = selected.nextSetBit(0); i >= 0; i = selected.nextSetBit(i + 1)) {
                target.add(candidates.get(i));
            }
            Set<OWLAxiom> remove = new HashSet<>(currentAxioms);
            remove.removeAll(target);
            Set<OWLAxiom> add = new HashSet<>(target);
            add.removeAll(currentAxioms);
            if (!remove.isEmpty()) {
                manager.removeAxioms(ontology, remove);
            }
            if (!add.isEmpty()) {
                manager.addAxioms(ontology, add);
            }
            currentAxioms = target;

            calls++;
            reasonerBuilds++;
            boolean result;
            try (ReasonerService reasoner = new ReasonerService(ontology)) {
                result = reasoner.isEntailed(query);
            }
            cache.put(key, result);
            return result;
        }

        @Override
        public void close() {
            manager.removeOntology(ontology);
        }
    }

    private static final class BudgetExceededException extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }
}
