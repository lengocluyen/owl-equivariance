package org.owleq.proof;

import org.owleq.io.ContextParser;
import org.owleq.model.BenchmarkItem;
import org.semanticweb.owlapi.model.OWLAxiom;

import java.util.*;

/**
 * Deletion-based validation of a model's claimed proof support (spec section 11.4).
 *
 * <p>The model returns a set of context axiom ids it says entails the query. Those axioms are
 * assembled into an ontology on their own and handed to the reasoner. If that ontology entails
 * the query, the support is <em>valid</em>: whatever prose the model wrote around it, the axioms
 * it pointed at really do carry the conclusion.
 *
 * <p>This sidesteps the hardest problem in evaluating LLM reasoning. Free-form chains of thought
 * cannot be mechanically checked, and grading them with another model imports the very
 * unreliability under study. A cited axiom set, by contrast, is a formal object with a decidable
 * property, and it is decided here by the same reasoner that produced the labels.
 *
 * <p>The measurement this enables is the one the spec calls central: a model can produce the right
 * answer while citing axioms that do not entail it (correct answer, invalid proof). That gap is
 * invisible to answer accuracy alone.
 */
public final class SupportValidator {

    public static final class Result {
        public String orbitItemId;
        /** Ids the model cited that do not exist in the context. */
        public List<String> unknownIds = new ArrayList<>();
        public List<String> resolvedIds = new ArrayList<>();
        /** Does the cited set entail the query? */
        public boolean supportValid;
        /** Is every cited axiom necessary, i.e. is the set a justification? */
        public boolean supportMinimal;
        /** Cited axioms whose removal leaves the entailment intact. */
        public List<String> redundantIds = new ArrayList<>();
        public int reasonerCalls;
        public String note;
    }

    /**
     * @param item      the benchmark item the prediction is for
     * @param citedIds  context axiom ids named by the model
     */
    public Result validate(BenchmarkItem item, List<String> citedIds) {
        Result r = new Result();
        r.orbitItemId = item.orbitItemId;

        Map<String, OWLAxiom> ctx = ContextParser.parseContext(item);
        OWLAxiom query = ContextParser.parseAxiom(item.task.queryFunctional);

        Map<String, OWLAxiom> cited = new LinkedHashMap<>();
        for (String id : citedIds) {
            OWLAxiom ax = ctx.get(id);
            if (ax == null) {
                r.unknownIds.add(id);
            } else {
                cited.put(id, ax);
                r.resolvedIds.add(id);
            }
        }

        if (cited.isEmpty()) {
            // An empty support set is the correct answer for a non-entailed query, and a failure
            // for an entailed one. Distinguishing the two is the caller's job; record the fact.
            r.supportValid = false;
            r.supportMinimal = false;
            r.note = citedIds.isEmpty() ? "no support cited" : "no cited id resolved";
            return r;
        }

        Justifier justifier = new Justifier();
        Set<OWLAxiom> support = new LinkedHashSet<>(cited.values());
        r.supportValid = justifier.entails(support, query);

        if (r.supportValid) {
            // Minimality: drop each cited axiom in turn. Anything the entailment survives
            // without was decoration, and a padded support set is weaker evidence of reasoning
            // than a tight one.
            for (Map.Entry<String, OWLAxiom> e : cited.entrySet()) {
                Set<OWLAxiom> without = new LinkedHashSet<>(support);
                without.remove(e.getValue());
                if (!without.isEmpty() && justifier.entails(without, query)) {
                    r.redundantIds.add(e.getKey());
                }
            }
            r.supportMinimal = r.redundantIds.isEmpty();
        }
        r.reasonerCalls = justifier.lastCallCount();
        return r;
    }
}
