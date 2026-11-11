package org.owleq.query;

import org.owleq.io.OntologyIO;
import org.owleq.model.BenchmarkItem;
import org.owleq.proof.Justifier;
import org.owleq.reasoner.ReasonerService;
import org.owleq.transform.Condition;
import org.owleq.transform.SignatureIsomorphism;
import org.semanticweb.owlapi.model.*;

import java.util.*;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Assembles benchmark orbits: one base item per query, one benchmark instance per condition.
 *
 * <p><b>Order equivariance.</b> The context is built exactly once, in the source vocabulary, and
 * each orbit member is produced by mapping that ordered list axiom by axiom. Every variant
 * therefore presents the same axioms in the same positions under the same ids, so the only thing
 * that differs between orbit members is the vocabulary. Rebuilding the context separately per
 * variant would let axiom order drift and confound renaming with presentation (spec section 16.4).
 *
 * <p><b>Verification.</b> Each emitted item's label is re-checked by the reasoner against the
 * exact axiom set the model will see, not against the full ontology. That is the property the
 * benchmark actually asserts, and an item that fails it is dropped rather than shipped.
 */
public final class DatasetBuilder {

    public static final class Config {
        public String ontologyId = "toy";
        public String ontologyVersion = "unversioned";
        public String profile = "OWL2_EL";
        public int positives = 50;
        public int negatives = 50;
        public int instanceQueries = 0;
        public int distractors = 10;
        public int maxContextAxioms = 60;
        public long seed = 42;
        /** Maximum new ELK classifications spent on one candidate justification. */
        public int justificationCallBudget = 256;
        public List<String> conditions = Condition.minimalPilot();
        public String split = "test";
        public String namespaceBase = "urn:owleq:";
        public ContextBuilder.DistractorKind distractorKind =
                ContextBuilder.DistractorKind.NEIGHBOURHOOD;
        /** SHA-256 of the source file's bytes, for provenance. */
        public String sourceFileSha256;
        /** Runtime-only progress hook; it does not enter or influence the dataset. */
        public Consumer<String> progress = message -> { };
    }

    public static final class Report {
        // Provenance: enough to identify exactly which artifact this is and rebuild it.
        public String ontologyId;
        public String ontologyVersion;
        public String ontologyIri;
        public String profile;
        /** SHA-256 of the source file's bytes -- comparable to a published checksum. */
        public String sourceFileSha256;
        /** SHA-256 of the deterministic serialization -- stable across serialization format. */
        public String sourceCanonicalSha256;
        public long seed;
        public List<String> conditions = new ArrayList<>();
        public String distractorKind;
        public int requestedPositives;
        public int requestedNegatives;
        public int requestedDistractors;
        public int maxContextAxioms;
        public String namespaceBase;
        public String certifierVersion = "0.2.0";
        public String reasoner = "ELK";
        public String justificationAlgorithm = "QUICKXPLAIN";
        public String candidateSampling = "SEEDED_SHA256_BOTTOM_K";
        public int justificationCallBudgetPerCandidate;
        public long inferredCandidatesEnumerated;
        public int boundedCandidatePoolSize;
        public int positiveCandidatesExamined;
        public int justificationReasonerCalls;
        public int justificationReasonerBuilds;
        public int justificationCacheHits;
        public int justificationBudgetExhaustedCandidates;
        /** Any preprocessing applied to the source, e.g. EL-fragment extraction. */
        public String preprocessing;

        public int baseItems;
        public int emitted;
        public int droppedUnverified;
        public int droppedUncertified;
        public int droppedEmptyContext;
        public final Map<String, Integer> byCondition = new TreeMap<>();
        public final Map<String, String> mappingFiles = new TreeMap<>();
        public ContextStats positiveContexts = new ContextStats();
        public ContextStats negativeContexts = new ContextStats();
        public final List<String> failures = new ArrayList<>();

        /** Context-size distribution, reported per label so a size/label confound is visible. */
        public static final class ContextStats {
            public int n;
            public int min = Integer.MAX_VALUE;
            public int max;
            public double mean;
            private int total;

            void add(int size) {
                n++;
                total += size;
                min = Math.min(min, size);
                max = Math.max(max, size);
                mean = (double) total / n;
            }

            void finish() {
                if (n == 0) {
                    min = 0;
                }
            }
        }
    }

    private final OWLOntology source;
    private final Config config;
    private final Report report = new Report();

    public DatasetBuilder(OWLOntology source, Config config) {
        this.source = source;
        this.config = config;
    }

    public Report report() {
        return report;
    }

    public List<BenchmarkItem> build() {
        List<QueryGenerator.Query> base = new ArrayList<>();
        progress("source_hash:start");
        String sourceHash = OntologyIO.ontologyHash(source);
        progress("source_hash:complete");

        report.ontologyId = config.ontologyId;
        report.ontologyVersion = config.ontologyVersion;
        report.ontologyIri = source.getOntologyID().getOntologyIRI().isPresent()
                ? source.getOntologyID().getOntologyIRI().get().toString() : "anonymous";
        report.profile = config.profile;
        report.sourceFileSha256 = config.sourceFileSha256;
        report.sourceCanonicalSha256 = sourceHash;
        report.seed = config.seed;
        report.conditions = new ArrayList<>(config.conditions);
        report.distractorKind = config.distractorKind.name();
        report.requestedPositives = config.positives;
        report.requestedNegatives = config.negatives;
        report.requestedDistractors = config.distractors;
        report.maxContextAxioms = config.maxContextAxioms;
        report.namespaceBase = config.namespaceBase;
        report.justificationCallBudgetPerCandidate = config.justificationCallBudget;

        progress("source_classification:start");
        try (ReasonerService rs = new ReasonerService(source)) {
            progress("source_classification:complete");
            if (!rs.isConsistent()) {
                throw new IllegalStateException(
                        "source ontology is inconsistent; every query would be entailed");
            }
            QueryGenerator gen = new QueryGenerator(
                    source, rs, config.justificationCallBudget, this::progress);
            progress("query_generation:start");
            List<QueryGenerator.Query> pos = gen.positives(config.positives, true, config.seed);
            base.addAll(pos);
            if (config.instanceQueries > 0) {
                List<QueryGenerator.Query> instancePos =
                        gen.instanceQueries(config.instanceQueries, config.seed + 1);
                base.addAll(instancePos);
                // Instance checking is balanced independently of the TBox quota. Treating
                // --instance-queries as positive-only would make task type reveal the label.
                base.addAll(gen.matchedNegatives(instancePos, config.seed + 3));
            }
            List<QueryGenerator.Query> negs = gen.matchedNegatives(pos, config.seed + 2);
            if (negs.size() > config.negatives) {
                negs = negs.subList(0, config.negatives);
            }
            base.addAll(negs);
            QueryGenerator.Diagnostics diagnostics = gen.diagnostics();
            report.inferredCandidatesEnumerated = diagnostics.inferredCandidatesEnumerated;
            report.boundedCandidatePoolSize = diagnostics.boundedCandidatePoolSize;
            report.positiveCandidatesExamined = diagnostics.positiveCandidatesExamined;
            report.justificationReasonerCalls = diagnostics.justificationReasonerCalls;
            report.justificationReasonerBuilds = diagnostics.justificationReasonerBuilds;
            report.justificationCacheHits = diagnostics.justificationCacheHits;
            report.justificationBudgetExhaustedCandidates =
                    diagnostics.justificationBudgetExhaustedCandidates;
            progress(String.format(
                    "query_generation:complete base_items=%d justification_calls=%d "
                            + "budget_exhausted=%d",
                    base.size(), report.justificationReasonerCalls,
                    report.justificationBudgetExhaustedCandidates));
        }
        report.baseItems = base.size();

        progress("condition_materialization:start");
        ContextBuilder contexts = new ContextBuilder(source);
        List<Condition> conditions = Condition.of(config.conditions);
        // One isomorphism per condition, built once and reused across every item, so that a
        // given entity has the same alias throughout the dataset.
        Map<String, SignatureIsomorphism> isos = new LinkedHashMap<>();
        Map<String, Map<IRI, Lexicon.Entry>> lexicons = new LinkedHashMap<>();
        for (Condition c : conditions) {
            progress(String.format("condition_materialization:condition=%s:start", c.id));
            SignatureIsomorphism iso = c.isomorphism(source, config.namespaceBase);
            isos.put(c.id, iso);
            // Materialize pi(O) once per condition purely to read back the annotations the
            // policy left behind. Recomputing them from the policy rules instead would
            // duplicate that logic and let the two drift apart.
            try {
                lexicons.put(c.id, Lexicon.annotationIndex(iso.apply(source)));
            } catch (OWLOntologyCreationException e) {
                throw new IllegalStateException("could not materialize condition " + c.id, e);
            }
            progress(String.format("condition_materialization:condition=%s:complete", c.id));
        }
        progress("condition_materialization:complete");

        // Contexts are built in two passes. Positives first, recording each one's size;
        // then negatives, each targeting the size of the positive it was derived from. Built
        // independently, negatives come out systematically smaller -- the module of an
        // unrelated class pair is thinner than that of an entailed one -- and context size
        // alone would predict the label.
        Map<QueryGenerator.Query, ContextBuilder.Result> built = new LinkedHashMap<>();
        progress("context_construction:start");
        int seedOffset = 0;
        for (QueryGenerator.Query q : base) {
            if (q.pairedPositive != null) {
                continue;
            }
            built.put(q, contexts.build(q.axiom, q.justification, config.distractors, 0,
                    config.distractorKind, config.maxContextAxioms, config.seed + (++seedOffset)));
        }
        for (QueryGenerator.Query q : base) {
            if (q.pairedPositive == null) {
                continue;
            }
            ContextBuilder.Result paired = built.get(q.pairedPositive);
            int target = paired != null ? paired.axioms.size() : 0;
            built.put(q, contexts.build(q.axiom, q.justification, config.distractors, target,
                    config.distractorKind, config.maxContextAxioms, config.seed + (++seedOffset)));
        }
        progress(String.format("context_construction:complete contexts=%d", built.size()));

        List<BenchmarkItem> out = new ArrayList<>();
        progress("orbit_emission:start");
        Set<String> seenBaseItemIds = new HashSet<>();
        for (QueryGenerator.Query q : base) {
            // Content-addressed ids remain stable when a different sample size is requested
            // or a new query is inserted earlier in the build. Sequential ids make every
            // downstream prediction impossible to compare across such a harmless rebuild.
            String queryHash = OntologyIO.sha256(OntologyIO.renderAxiom(q.axiom));
            String baseItemId = String.format("%s:%s:%s", config.ontologyId, q.taskType,
                    queryHash.substring(0, 16));
            if (!seenBaseItemIds.add(baseItemId)) {
                throw new IllegalStateException("duplicate source query or base-id collision: "
                        + baseItemId + " for " + OntologyIO.renderAxiom(q.axiom));
            }
            ContextBuilder.Result ctx = built.get(q);
            if (ctx == null || ctx.axioms.isEmpty()) {
                // A zero-axiom context makes the item answerable without reading anything.
                report.droppedEmptyContext++;
                continue;
            }
            if (!ctx.certified) {
                report.droppedUncertified++;
                continue;
            }
            (q.entailed ? report.positiveContexts : report.negativeContexts)
                    .add(ctx.axioms.size());

            for (Condition c : conditions) {
                BenchmarkItem item = emit(q, ctx, c, isos.get(c.id), lexicons.get(c.id),
                        baseItemId, sourceHash);
                if (item != null) {
                    out.add(item);
                    report.byCondition.merge(c.id, 1, Integer::sum);
                }
            }
            if (seenBaseItemIds.size() % 10 == 0) {
                progress(String.format("orbit_emission:progress base_items=%d/%d emitted=%d",
                        seenBaseItemIds.size(), base.size(), out.size()));
            }
        }
        report.emitted = out.size();
        report.positiveContexts.finish();
        report.negativeContexts.finish();
        this.isomorphisms = isos;
        progress(String.format("orbit_emission:complete emitted=%d", out.size()));
        return out;
    }

    private void progress(String message) {
        if (config.progress != null) {
            config.progress.accept(message);
        }
    }

    private Map<String, SignatureIsomorphism> isomorphisms = Collections.emptyMap();

    /** The mappings used, so the caller can write one manifest per condition. */
    public Map<String, SignatureIsomorphism> isomorphisms() {
        return isomorphisms;
    }

    private BenchmarkItem emit(QueryGenerator.Query q, ContextBuilder.Result ctx, Condition c,
                               SignatureIsomorphism iso, Map<IRI, Lexicon.Entry> lexicon,
                               String baseItemId, String sourceHash) {
        // Map the ordered context and the query through pi, preserving positions and ids.
        List<OWLAxiom> mapped = new ArrayList<>(ctx.axioms.size());
        for (OWLAxiom ax : ctx.axioms) {
            mapped.add(iso.transform(ax));
        }
        OWLAxiom mappedQuery = iso.transform(q.axiom);

        Set<OWLAxiom> contextSet = new LinkedHashSet<>(mapped);
        Justifier justifier = new Justifier();
        boolean entailed;
        try {
            entailed = justifier.entails(contextSet, mappedQuery);
        } catch (RuntimeException e) {
            report.failures.add(baseItemId + "/" + c.id + ": " + e.getMessage());
            report.droppedUnverified++;
            return null;
        }
        if (entailed != q.entailed) {
            // Either the transform or the context construction is unsound for this item. Both are
            // supposed to be impossible; record loudly rather than quietly shipping a wrong label.
            report.failures.add(String.format(
                    "%s/%s: label changed under transform (expected %s, reasoner says %s)",
                    baseItemId, c.id, q.entailed, entailed));
            report.droppedUnverified++;
            return null;
        }

        BenchmarkItem item = new BenchmarkItem();
        item.baseItemId = baseItemId;
        item.orbitItemId = baseItemId + ":" + c.id;
        item.split = config.split;

        item.ontology.ontologyId = config.ontologyId;
        item.ontology.version = config.ontologyVersion;
        item.ontology.profile = config.profile;
        item.ontology.sourceHash = sourceHash;

        item.task.type = q.taskType;
        item.task.queryFunctional = OntologyIO.renderAxiom(mappedQuery);
        item.task.queryText = Verbalizer.axiom(mappedQuery);
        item.task.label = q.entailed ? "ENTAILED" : "NOT_ENTAILED";
        item.task.positive = q.entailed;
        item.task.proofDepth = q.proofDepth >= 0 ? q.proofDepth : null;
        item.task.explicit = q.explicit;
        item.task.negativeKind = q.negativeKind == null ? null : q.negativeKind.name();

        item.transform.operator = c.operator;
        item.transform.seed = c.seed;
        item.transform.mappingId = "map:" + config.ontologyId + ":" + c.id;
        item.transform.lexicalCondition = c.id;
        item.transform.annotationPolicy = c.annotationPolicy.name();

        item.context.strategy = ctx.strategy;
        item.context.distractorCount = ctx.distractorCount;
        item.context.labelPreservationCertified = ctx.certified;
        Map<OWLAxiom, String> ids = new LinkedHashMap<>();
        for (int i = 0; i < mapped.size(); i++) {
            String id = "A" + (i + 1);
            ids.put(mapped.get(i), id);
            item.context.axioms.add(new BenchmarkItem.Axiom(id,
                    OntologyIO.renderAxiom(mapped.get(i))));
        }
        item.context.lexicon = lexiconFor(mapped, mappedQuery, lexicon);

        // Reference support, expressed in the same ids the model must cite.
        if (q.entailed && !q.justification.isEmpty()) {
            List<String> support = new ArrayList<>();
            for (OWLAxiom ax : q.justification) {
                String id = ids.get(iso.transform(ax));
                if (id != null) {
                    support.add(id);
                }
            }
            support.sort(Comparator.naturalOrder());
            if (!support.isEmpty()) {
                item.reference.supportAxiomSets.add(support);
            }
        }
        item.reference.reasoner = "ELK";
        item.reference.verified = true;
        return item;
    }

    /**
     * Lexical entries for exactly the entities the model will see, in a stable order.
     *
     * <p>Restricted to the context and query signature: shipping the whole ontology's
     * annotations would hand the model vocabulary for entities that never appear, which is
     * both a leak and a token cost. Entities the policy stripped bare are omitted entirely,
     * so a fully de-lexicalized condition carries an empty list rather than empty entries.
     */
    private List<BenchmarkItem.Lexicon> lexiconFor(List<OWLAxiom> axioms, OWLAxiom query,
                                                   Map<IRI, Lexicon.Entry> index) {
        if (index == null || index.isEmpty()) {
            return Collections.emptyList();
        }
        Set<OWLEntity> signature = new LinkedHashSet<>(query.getSignature());
        for (OWLAxiom ax : axioms) {
            signature.addAll(ax.getSignature());
        }

        List<BenchmarkItem.Lexicon> out = new ArrayList<>();
        List<OWLEntity> sorted = signature.stream()
                .filter(e -> !e.isBuiltIn())
                .sorted(Comparator.comparing(e -> e.getIRI().toString()))
                .collect(Collectors.toList());
        Set<IRI> seen = new HashSet<>();
        for (OWLEntity e : sorted) {
            if (!seen.add(e.getIRI())) {
                continue;  // a pun contributes one lexical entry, not one per type
            }
            Lexicon.Entry entry = index.get(e.getIRI());
            if (entry == null || entry.isEmpty()) {
                continue;
            }
            BenchmarkItem.Lexicon lex = new BenchmarkItem.Lexicon();
            lex.entity = org.owleq.transform.Naming.localName(e);
            lex.iri = e.getIRI().toString();
            lex.label = entry.label;
            lex.definition = entry.definition;
            lex.synonyms = entry.synonyms.isEmpty() ? null : new ArrayList<>(entry.synonyms);
            out.add(lex);
        }
        return out;
    }

    /** Base-item ids grouped, for the leakage check: all orbit members share a split. */
    public static Map<String, List<BenchmarkItem>> orbits(List<BenchmarkItem> items) {
        return items.stream().collect(Collectors.groupingBy(i -> i.baseItemId,
                LinkedHashMap::new, Collectors.toList()));
    }
}
