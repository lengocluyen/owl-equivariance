package org.owleq.query;

import org.owleq.io.OntologyIO;
import org.owleq.proof.Justifier;
import org.owleq.reasoner.ReasonerService;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.reasoner.Node;

import java.util.*;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Generates symbolically verified entailment queries (spec section 10).
 *
 * <p>Positives are drawn from the reasoner's inferred class hierarchy, preferring subsumptions
 * that are <em>not</em> asserted verbatim, since an asserted axiom tests lookup rather than
 * inference.
 *
 * <p>Negatives are the delicate half. Sampling two unrelated classes produces items solvable by
 * noticing that the two names have nothing to do with each other -- a lexical shortcut, and
 * exactly the confound this study exists to remove. Every negative here is therefore
 * <em>matched</em>: it reuses the positive's subject and swaps the object for a class that is
 * structurally or lexically close but provably not entailed (spec section 10.3).
 */
public final class QueryGenerator {

    /** Which matched-negative family a non-entailed item came from. */
    public enum NegativeKind {
        /** Shares an asserted parent with the true superclass. */
        SIBLING,
        /** Elsewhere under a common ancestor: same region of the hierarchy, wrong branch. */
        NEARBY_BRANCH,
        /** Chosen for maximal name similarity to the true superclass. */
        LEXICAL,
        /** Unrelated class: retained as an easy control, not as the main negative. */
        RANDOM
    }

    public static final class Query {
        public String taskType;
        public OWLAxiom axiom;
        public boolean entailed;
        public boolean explicit;
        public NegativeKind negativeKind;
        public Set<OWLAxiom> justification = Collections.emptySet();
        /** Smallest justification size found; a reasoner-derived difficulty proxy. */
        public int proofDepth = -1;
        /**
         * For a negative, the positive it was derived from.
         *
         * <p>Carried so the two can be given matched context sizes. If negatives were built
         * independently their contexts would end up systematically smaller than the
         * positives' -- the module of an unrelated class pair is thinner than the module of
         * an entailed one -- and context size alone would predict the label.
         */
        public Query pairedPositive;
    }

    private final OWLOntology ontology;
    private final ReasonerService reasoner;
    private final OWLDataFactory df = OWLManager.getOWLDataFactory();
    private final ContextBuilder contexts;
    private final Map<OWLEntity, String> lexicon;
    private final int justificationCallBudget;
    private final Consumer<String> progress;
    private final Diagnostics diagnostics = new Diagnostics();

    /** Machine-readable counters copied into the dataset build report. */
    public static final class Diagnostics {
        public long inferredCandidatesEnumerated;
        public int boundedCandidatePoolSize;
        public int positiveCandidatesExamined;
        public int justificationReasonerCalls;
        public int justificationReasonerBuilds;
        public int justificationCacheHits;
        public int justificationBudgetExhaustedCandidates;
    }

    public QueryGenerator(OWLOntology ontology, ReasonerService reasoner) {
        this(ontology, reasoner, 3000, message -> { });
    }

    public QueryGenerator(OWLOntology ontology, ReasonerService reasoner,
                          int justificationCallBudget, Consumer<String> progress) {
        if (justificationCallBudget < 1) {
            throw new IllegalArgumentException("justification call budget must be positive");
        }
        this.ontology = ontology;
        this.reasoner = reasoner;
        this.contexts = new ContextBuilder(ontology);
        this.lexicon = Lexicon.index(ontology);
        this.justificationCallBudget = justificationCallBudget;
        this.progress = progress == null ? message -> { } : progress;
    }

    public Diagnostics diagnostics() {
        return diagnostics;
    }

    // ------------------------------------------------------------------ positives

    /**
     * Atomic subsumptions A subclass-of B that the reasoner infers, binned by justification size
     * so the dataset spans easy and hard items rather than piling up on one-step lookups.
     */
    public List<Query> positives(int count, boolean preferInferredOnly, long seed) {
        if (count <= 0) {
            return Collections.emptyList();
        }
        int examineCap = Math.max(count * 8, 200);
        PriorityQueue<ScoredAxiom> bounded = new PriorityQueue<>(
                Comparator.reverseOrder());
        Set<OWLClass> unsat = reasoner.unsatisfiableClasses();

        List<OWLClass> classes = sortedClasses();
        progress.accept(String.format(
                "candidate_enumeration:start classes=%d pool_cap=%d", classes.size(), examineCap));
        int classIndex = 0;
        for (OWLClass sub : classes) {
            classIndex++;
            if (sub.isOWLNothing() || sub.isOWLThing() || unsat.contains(sub)) {
                continue;
            }
            for (Node<OWLClass> node : reasoner.superClasses(sub, false)) {
                for (OWLClass sup : node.getEntities()) {
                    if (sup.isOWLThing() || sup.equals(sub) || unsat.contains(sup)) {
                        continue;
                    }
                    OWLSubClassOfAxiom ax = df.getOWLSubClassOfAxiom(sub, sup);
                    boolean asserted = ontology.containsAxiom(ax);
                    if (preferInferredOnly && asserted) {
                        continue;
                    }
                    diagnostics.inferredCandidatesEnumerated++;
                    offerBounded(bounded, new ScoredAxiom(ax, seed), examineCap);
                }
            }
            if (classIndex % 1000 == 0 || classIndex == classes.size()) {
                progress.accept(String.format(
                        "candidate_enumeration:progress classes=%d/%d inferred=%d retained=%d",
                        classIndex, classes.size(), diagnostics.inferredCandidatesEnumerated,
                        bounded.size()));
            }
        }
        // A seeded content hash gives every inferred axiom a deterministic pseudorandom rank.
        // Keeping only the lowest ranks is a bounded-memory sample independent of ELK's internal
        // iteration order; the previous implementation materialized and sorted the full inferred
        // closure even though it examined only this many candidates.
        List<ScoredAxiom> scored = new ArrayList<>(bounded);
        Collections.sort(scored);
        List<OWLSubClassOfAxiom> candidates = scored.stream()
                .map(candidate -> candidate.axiom)
                .collect(Collectors.toList());
        diagnostics.boundedCandidatePoolSize = candidates.size();
        progress.accept(String.format(
                "candidate_enumeration:complete inferred=%d retained=%d",
                diagnostics.inferredCandidatesEnumerated, candidates.size()));

        // Bins follow spec section 10.2; keyed on justification size, computed lazily so that
        // an expensive justification is never computed for a candidate that is not needed.
        int[] binEdges = {1, 3, 6, Integer.MAX_VALUE};
        int perBin = Math.max(1, count / binEdges.length);
        Map<Integer, List<Query>> bins = new LinkedHashMap<>();
        for (int i = 0; i < binEdges.length; i++) {
            bins.put(i, new ArrayList<>());
        }

        Justifier justifier = new Justifier();
        int examined = 0;
        for (OWLSubClassOfAxiom ax : candidates) {
            if (totalSize(bins) >= count || examined >= examineCap) {
                break;
            }
            examined++;
            diagnostics.positiveCandidatesExamined++;
            Set<OWLAxiom> module = contexts.starModule(ax.getSignature());
            Optional<Set<OWLAxiom>> j = justifier.one(
                    module, ax, justificationCallBudget);
            recordJustificationDiagnostics(justifier);
            if (examined % 10 == 0) {
                reportJustificationProgress(examined, candidates.size(), totalSize(bins), count);
            }
            if (!j.isPresent()) {
                // The module must entail whatever the full ontology entails over its signature;
                // if it does not, something is wrong with this item and it is dropped rather
                // than shipped with an unverified label.
                continue;
            }
            int size = j.get().size();
            int bin = binOf(size, binEdges);
            boolean binFull = bins.get(bin).size() >= perBin;
            boolean allBinsFull = bins.values().stream().allMatch(b -> b.size() >= perBin);
            if (binFull && !allBinsFull) {
                // Hold this bin's quota until the sparser bins have had their chance; deep-proof
                // items are rare and would otherwise be crowded out by one-step subsumptions.
                continue;
            }
            Query q = new Query();
            q.taskType = "ATOMIC_SUBSUMPTION";
            q.axiom = ax;
            q.entailed = true;
            q.explicit = ontology.containsAxiom(ax);
            q.justification = j.get();
            q.proofDepth = size;
            bins.get(bin).add(q);
            if (totalSize(bins) >= count) {
                reportJustificationProgress(examined, candidates.size(), totalSize(bins), count);
            }
        }
        List<Query> out = new ArrayList<>();
        bins.values().forEach(out::addAll);
        progress.accept(String.format(
                "justification_search:complete examined=%d selected=%d calls=%d "
                        + "budget_exhausted=%d",
                examined, out.size(), diagnostics.justificationReasonerCalls,
                diagnostics.justificationBudgetExhaustedCandidates));
        return out.size() > count ? new ArrayList<>(out.subList(0, count)) : out;
    }

    /** Instance checking A(a) for inferred, non-asserted types. */
    public List<Query> instanceQueries(int count, long seed) {
        if (count <= 0) {
            return Collections.emptyList();
        }
        List<Query> out = new ArrayList<>();
        List<OWLNamedIndividual> individuals = ontology.getIndividualsInSignature().stream()
                .sorted(Comparator.comparing(i -> i.getIRI().toString()))
                .collect(Collectors.toList());
        Collections.shuffle(individuals, new Random(seed));

        Justifier justifier = new Justifier();
        for (OWLNamedIndividual ind : individuals) {
            if (out.size() >= count) {
                break;
            }
            List<OWLClass> inferredTypes = reasoner.types(ind, false).getFlattened().stream()
                    .sorted(Comparator.comparing(c -> c.getIRI().toString()))
                    .collect(Collectors.toList());
            for (OWLClass type : inferredTypes) {
                if (out.size() >= count) {
                    break;
                }
                if (type.isOWLThing()) {
                    continue;
                }
                OWLClassAssertionAxiom ax = df.getOWLClassAssertionAxiom(type, ind);
                if (ontology.containsAxiom(ax)) {
                    continue;
                }
                Set<OWLAxiom> module = contexts.starModule(ax.getSignature());
                Optional<Set<OWLAxiom>> j = justifier.one(
                        module, ax, justificationCallBudget);
                recordJustificationDiagnostics(justifier);
                if (!j.isPresent()) {
                    continue;
                }
                Query q = new Query();
                q.taskType = "INSTANCE_CHECKING";
                q.axiom = ax;
                q.entailed = true;
                q.explicit = false;
                q.justification = j.get();
                q.proofDepth = j.get().size();
                out.add(q);
                break;
            }
        }
        return out;
    }

    // ------------------------------------------------------------------ negatives

    /**
     * One matched non-entailed query per positive, keeping the subject and replacing the object
     * with a confusable but unentailed class. Every candidate is checked with the reasoner
     * before being accepted.
     */
    public List<Query> matchedNegatives(List<Query> positives, long seed) {
        List<Query> out = new ArrayList<>();
        Random rnd = new Random(seed);
        Set<OWLClass> unsat = reasoner.unsatisfiableClasses();
        List<OWLClass> allClasses = sortedClasses().stream()
                .filter(c -> !c.isOWLThing() && !c.isOWLNothing() && !unsat.contains(c))
                .collect(Collectors.toList());

        for (Query pos : positives) {
            if (pos.axiom instanceof OWLClassAssertionAxiom) {
                OWLClassAssertionAxiom ax = (OWLClassAssertionAxiom) pos.axiom;
                if (ax.getClassExpression().isAnonymous()
                        || !ax.getIndividual().isNamed()) {
                    continue;
                }
                OWLClass trueType = ax.getClassExpression().asOWLClass();
                OWLNamedIndividual individual = ax.getIndividual().asOWLNamedIndividual();
                Optional<OWLClass> pick = allClasses.stream()
                        .filter(c -> !c.equals(trueType))
                        .sorted(Comparator.comparingDouble(
                                c -> -Lexicon.similarity(text(c), text(trueType))))
                        .filter(c -> !reasoner.isEntailed(
                                df.getOWLClassAssertionAxiom(c, individual)))
                        .findFirst();
                if (!pick.isPresent()) {
                    continue;
                }
                Query q = new Query();
                q.taskType = pos.taskType;
                q.axiom = df.getOWLClassAssertionAxiom(pick.get(), individual);
                q.entailed = false;
                q.explicit = false;
                q.negativeKind = NegativeKind.LEXICAL;
                q.proofDepth = pos.proofDepth;
                q.pairedPositive = pos;
                out.add(q);
                continue;
            }
            if (!(pos.axiom instanceof OWLSubClassOfAxiom)) {
                continue;
            }
            OWLSubClassOfAxiom ax = (OWLSubClassOfAxiom) pos.axiom;
            if (ax.getSubClass().isAnonymous() || ax.getSuperClass().isAnonymous()) {
                continue;
            }
            OWLClass sub = ax.getSubClass().asOWLClass();
            OWLClass trueSuper = ax.getSuperClass().asOWLClass();
            if (unsat.contains(sub)) {
                continue;  // everything is entailed of an unsatisfiable class
            }

            // Ordered by how hard the resulting negative should be.
            for (NegativeKind kind : new NegativeKind[]{NegativeKind.SIBLING,
                    NegativeKind.NEARBY_BRANCH, NegativeKind.LEXICAL, NegativeKind.RANDOM}) {
                Optional<OWLClass> pick = candidate(kind, sub, trueSuper, allClasses, rnd);
                if (!pick.isPresent()) {
                    continue;
                }
                OWLSubClassOfAxiom neg = df.getOWLSubClassOfAxiom(sub, pick.get());
                if (reasoner.isEntailed(neg)) {
                    continue;
                }
                Query q = new Query();
                q.taskType = pos.taskType;
                q.axiom = neg;
                q.entailed = false;
                q.explicit = false;
                q.negativeKind = kind;
                q.proofDepth = pos.proofDepth;  // matched to its positive for paired analysis
                q.pairedPositive = pos;
                out.add(q);
                break;
            }
        }
        return out;
    }

    private Optional<OWLClass> candidate(NegativeKind kind, OWLClass sub, OWLClass trueSuper,
                                         List<OWLClass> all, Random rnd) {
        List<OWLClass> pool;
        switch (kind) {
            case SIBLING:
                pool = siblingsOf(trueSuper);
                break;
            case NEARBY_BRANCH:
                pool = nearbyBranch(trueSuper);
                break;
            case LEXICAL:
                pool = all.stream()
                        .sorted(Comparator.comparingDouble(
                                c -> -Lexicon.similarity(text(c), text(trueSuper))))
                        .limit(25)
                        .collect(Collectors.toList());
                break;
            default:
                pool = new ArrayList<>(all);
                Collections.shuffle(pool, rnd);
        }
        return pool.stream()
                .filter(c -> !c.equals(trueSuper) && !c.equals(sub))
                // Reject the reverse direction too: a class that entails the subject makes the
                // item ambiguous to a reader and is a different phenomenon (spec section 10.3.6).
                .filter(c -> !reasoner.isEntailed(df.getOWLSubClassOfAxiom(c, sub)))
                .findFirst();
    }

    private List<OWLClass> siblingsOf(OWLClass c) {
        Set<OWLClass> sibs = new LinkedHashSet<>();
        for (Node<OWLClass> parentNode : reasoner.superClasses(c, true)) {
            for (OWLClass parent : parentNode.getEntities()) {
                if (parent.isOWLThing()) {
                    continue;
                }
                for (Node<OWLClass> kid : reasoner.subClasses(parent, true)) {
                    sibs.addAll(kid.getEntities());
                }
            }
        }
        sibs.remove(c);
        return sibs.stream()
                .filter(x -> !x.isOWLNothing())
                .sorted(Comparator.comparing(x -> x.getIRI().toString()))
                .collect(Collectors.toList());
    }

    private List<OWLClass> nearbyBranch(OWLClass c) {
        Set<OWLClass> out = new LinkedHashSet<>();
        for (Node<OWLClass> anc : reasoner.superClasses(c, false)) {
            for (OWLClass a : anc.getEntities()) {
                if (a.isOWLThing()) {
                    continue;
                }
                for (Node<OWLClass> desc : reasoner.subClasses(a, false)) {
                    out.addAll(desc.getEntities());
                }
            }
        }
        out.remove(c);
        return out.stream()
                .filter(x -> !x.isOWLNothing())
                .sorted(Comparator.comparing(x -> x.getIRI().toString()))
                .collect(Collectors.toList());
    }

    private String text(OWLClass c) {
        return lexicon.getOrDefault(c, org.owleq.transform.Naming.localName(c));
    }

    private List<OWLClass> sortedClasses() {
        return ontology.getClassesInSignature().stream()
                .sorted(Comparator.comparing(c -> c.getIRI().toString()))
                .collect(Collectors.toList());
    }

    private static int binOf(int size, int[] edges) {
        for (int i = 0; i < edges.length; i++) {
            if (size <= edges[i]) {
                return i;
            }
        }
        return edges.length - 1;
    }

    private static int totalSize(Map<Integer, List<Query>> bins) {
        return bins.values().stream().mapToInt(List::size).sum();
    }

    private void recordJustificationDiagnostics(Justifier justifier) {
        diagnostics.justificationReasonerCalls += justifier.lastCallCount();
        diagnostics.justificationReasonerBuilds += justifier.lastReasonerBuildCount();
        diagnostics.justificationCacheHits += justifier.lastCacheHitCount();
        if (justifier.lastBudgetExhausted()) {
            diagnostics.justificationBudgetExhaustedCandidates++;
        }
    }

    private void reportJustificationProgress(int examined, int available,
                                             int selected, int requested) {
        progress.accept(String.format(
                "justification_search:progress examined=%d/%d selected=%d/%d "
                        + "calls=%d budget_exhausted=%d",
                examined, available, selected, requested,
                diagnostics.justificationReasonerCalls,
                diagnostics.justificationBudgetExhaustedCandidates));
    }

    private static void offerBounded(PriorityQueue<ScoredAxiom> pool,
                                     ScoredAxiom candidate, int capacity) {
        if (pool.size() < capacity) {
            pool.add(candidate);
        } else if (candidate.compareTo(pool.peek()) < 0) {
            pool.poll();
            pool.add(candidate);
        }
    }

    /** Seeded content rank used for bounded, iteration-order-independent sampling. */
    private static final class ScoredAxiom implements Comparable<ScoredAxiom> {
        final OWLSubClassOfAxiom axiom;
        final String rendered;
        final String score;

        ScoredAxiom(OWLSubClassOfAxiom axiom, long seed) {
            this.axiom = axiom;
            this.rendered = OntologyIO.renderAxiom(axiom);
            this.score = OntologyIO.sha256(seed + "\n" + rendered);
        }

        @Override
        public int compareTo(ScoredAxiom other) {
            int byScore = score.compareTo(other.score);
            return byScore != 0 ? byScore : rendered.compareTo(other.rendered);
        }
    }
}
