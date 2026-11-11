package org.owleq.query;

import org.owleq.io.OntologyIO;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import uk.ac.manchester.cs.owlapi.modularity.ModuleType;
import uk.ac.manchester.cs.owlapi.modularity.SyntacticLocalityModuleExtractor;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Builds the axiom context shown to the model, with a label-preservation guarantee (spec
 * section 16).
 *
 * <p><b>The guarantee.</b> Every context is a subset of the source ontology O that contains the
 * bottom-locality module M for the query signature. Two monotonicity facts then fix both
 * labels without any per-item reasoner check:
 *
 * <ul>
 *   <li>Non-entailed queries: {@code Context subset-of O} and {@code O !|= q} imply
 *       {@code Context !|= q}. Adding axioms can only add entailments, so a subset of a
 *       non-entailing ontology cannot entail q.</li>
 *   <li>Entailed queries: the context contains a justification J with {@code J |= q}, so
 *       {@code Context |= q}.</li>
 * </ul>
 *
 * <p><b>Why modules and not just a justification.</b> For a negative item, a small hand-picked
 * context would make "not entailed" true but uninteresting: the model could be right for the
 * wrong reason, having simply not been shown the relevant part of the ontology. The bottom module
 * is <em>query-complete</em> for its signature -- for any axiom alpha over sig(M),
 * {@code O |= alpha iff M |= alpha} (Cuenca Grau, Horrocks, Kazakov and Sattler) -- so a model
 * that answers NOT_ENTAILED from M is answering the same question the full ontology poses.
 *
 * <p>Distractors are drawn from {@code O \ M}, never synthesised. A fabricated axiom would sit
 * outside O and void the subset argument above, forcing a per-item recheck and, worse, changing
 * what the negative label means.
 */
public final class ContextBuilder {

    /** Distractor families of spec section 16.3. */
    public enum DistractorKind {
        /** Axioms sharing entities with the module: hardest, forces real structural reading. */
        NEIGHBOURHOOD,
        /** Axioms with no signature overlap: the easy control. */
        DISCONNECTED
    }

    private final OWLOntology full;
    private final List<OWLAxiom> logicalAxioms;

    public ContextBuilder(OWLOntology full) {
        this.full = full;
        this.logicalAxioms = full.getLogicalAxioms().stream()
                .sorted(Comparator.comparing(OntologyIO::renderAxiom))
                .collect(Collectors.toList());
    }

    public static final class Result {
        /** Ordered; this exact order is reused for every orbit member. */
        public final List<OWLAxiom> axioms;
        public final int moduleSize;
        public final int distractorCount;
        public final boolean certified;
        public final String strategy;

        Result(List<OWLAxiom> axioms, int moduleSize, int distractorCount, boolean certified,
               String strategy) {
            this.axioms = axioms;
            this.moduleSize = moduleSize;
            this.distractorCount = distractorCount;
            this.certified = certified;
            this.strategy = strategy;
        }
    }

    /**
     * @param query         the query axiom, in the source vocabulary
     * @param justification a known justification for positives; null or empty for negatives
     * @param distractors   how many axioms beyond the module to add
     * @param targetSize    desired total context size, or 0 for "module + distractors".
     *                      Used to match a negative item's context to its paired positive.
     * @param maxAxioms     hard cap on context size
     */
    public Result build(OWLAxiom query, Set<OWLAxiom> justification, int distractors,
                        int targetSize, DistractorKind kind, int maxAxioms, long seed) {
        Set<OWLAxiom> module = queryModule(query.getSignature());
        Set<OWLAxiom> core = new LinkedHashSet<>(module);

        boolean trimmed = false;
        if (core.size() > maxAxioms) {
            core = trimToBudget(core, justification, maxAxioms, seed);
            trimmed = true;
        }

        // The pool is seeded from the query signature as well as the module's, so an item
        // whose module is small still has a neighbourhood to draw from. Without this, a
        // query whose module is empty gets an empty pool and therefore an empty context --
        // and a model can answer NOT_ENTAILED correctly having been shown nothing at all.
        List<OWLAxiom> pool = distractorPool(core, query, kind);
        Collections.shuffle(pool, new Random(seed));

        // A positive sets its own size from its module plus the distractor budget; a
        // negative is given its paired positive's size and matches it exactly, floored at
        // its own module size (evidence is never dropped to hit a target).
        int desired = targetSize > 0
                ? Math.max(core.size(), Math.min(targetSize, maxAxioms))
                : Math.min(maxAxioms, core.size() + distractors);
        int room = Math.max(0, desired - core.size());
        List<OWLAxiom> chosen = pool.subList(0, Math.min(room, pool.size()));

        List<OWLAxiom> all = new ArrayList<>(core);
        all.addAll(chosen);

        if (all.isEmpty()) {
            // Every fallback exhausted. Emitting a zero-axiom item would be worse than
            // emitting nothing, so the caller is told and drops the item.
            return new Result(Collections.emptyList(), module.size(), 0, false, "EMPTY");
        }
        // Deterministic presentation order, independent of set iteration order. Shuffled with a
        // fixed seed so justification axioms are not always first (spec section 16.4).
        all.sort(Comparator.comparing(OntologyIO::renderAxiom));
        Collections.shuffle(all, new Random(seed * 31 + 7));

        // Trimming preserves the subset property, so negatives stay certified either way; for
        // positives it preserves entailment exactly when the justification survived.
        boolean certified = !trimmed
                || justification == null
                || justification.isEmpty()
                || all.containsAll(justification);

        return new Result(all, module.size(), chosen.size(), certified,
                trimmed ? "LOCALITY_MODULE_BOTTOM_TRIMMED" : "LOCALITY_MODULE_BOTTOM");
    }

    /**
     * The locality module used to build contexts.
     *
     * <p><b>Bottom, not star.</b> Both module types are query-complete for their signature,
     * so either yields correct labels. They differ sharply in what they contain for a
     * <em>non-entailed</em> query: the star module of two unrelated classes is
     * <em>empty</em>, because once the unrelated symbols are replaced by top every axiom
     * becomes a tautology and is discarded. That is formally right and experimentally
     * useless -- the model would be asked to reject a subsumption having been shown no
     * axioms whatsoever, and could answer correctly by noticing the context is empty.
     *
     * <p>The bottom module keeps the full ancestor chain of each query entity, which is
     * exactly the material needed to decide the subsumption either way, and yields
     * comparable contexts for entailed and non-entailed items.
     */
    public Set<OWLAxiom> queryModule(Set<OWLEntity> signature) {
        return extractModule(signature, ModuleType.BOT);
    }

    /** The bottom-top-star module: smaller, still query-complete. Kept for comparison. */
    public Set<OWLAxiom> starModule(Set<OWLEntity> signature) {
        return extractModule(signature, ModuleType.STAR);
    }

    private Set<OWLAxiom> extractModule(Set<OWLEntity> signature, ModuleType type) {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        SyntacticLocalityModuleExtractor ex =
                new SyntacticLocalityModuleExtractor(m, full, type);
        Set<OWLEntity> sig = signature.stream()
                .filter(e -> !e.isBuiltIn())
                .collect(Collectors.toSet());
        return ex.extract(sig).stream()
                .filter(OWLAxiom::isLogicalAxiom)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    /**
     * Shrink an oversized module to the budget while keeping the justification intact, so the
     * positive label survives. Remaining slots go to module axioms nearest the query signature.
     */
    private Set<OWLAxiom> trimToBudget(Set<OWLAxiom> module, Set<OWLAxiom> justification,
                                       int maxAxioms, long seed) {
        Set<OWLAxiom> keep = new LinkedHashSet<>();
        if (justification != null) {
            keep.addAll(justification);
        }
        List<OWLAxiom> rest = module.stream()
                .filter(a -> !keep.contains(a))
                .sorted(Comparator.comparing(OntologyIO::renderAxiom))
                .collect(Collectors.toList());
        Collections.shuffle(rest, new Random(seed * 13 + 3));
        for (OWLAxiom a : rest) {
            if (keep.size() >= maxAxioms) {
                break;
            }
            keep.add(a);
        }
        return keep;
    }

    private List<OWLAxiom> distractorPool(Set<OWLAxiom> core, OWLAxiom query,
                                          DistractorKind kind) {
        Set<OWLEntity> coreSig = core.stream()
                .flatMap(a -> a.getSignature().stream())
                .collect(Collectors.toCollection(HashSet::new));
        // Seeding from the query as well as the module is what keeps the pool non-empty
        // when the module is small.
        coreSig.addAll(query.getSignature());

        List<OWLAxiom> primary = logicalAxioms.stream()
                .filter(a -> !core.contains(a))
                .filter(a -> {
                    boolean overlaps = a.getSignature().stream().anyMatch(coreSig::contains);
                    return kind == DistractorKind.NEIGHBOURHOOD ? overlaps : !overlaps;
                })
                .collect(Collectors.toList());
        if (!primary.isEmpty()) {
            return primary;
        }
        // Last resort: any axiom outside the core. An unrelated distractor is a weaker
        // control than a neighbourhood one, but far better than an empty context.
        return logicalAxioms.stream()
                .filter(a -> !core.contains(a))
                .collect(Collectors.toList());
    }
}
