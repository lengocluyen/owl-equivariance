package org.owleq.transform;

import org.semanticweb.owlapi.model.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Assigns a new local name to every entity of one OWL type.
 *
 * <p>Implementations must be deterministic given the seed and the (sorted) entity list, and must
 * be injective within the type. Injectivity across types is guaranteed separately by
 * {@link SignatureIsomorphism}, which namespaces each type.
 */
public interface NameStrategy {

    /** @return entity -> new local name; must be injective. */
    Map<OWLEntity, String> assign(List<OWLEntity> entities, EntityType<?> type,
                                  OWLOntology source, long seed);

    String operatorId();

    // ------------------------------------------------------------------ O1

    /**
     * O1, opaque identifiers: {@code C_000001}. Carries no lexical signal whatsoever, but is
     * also tokenized very differently from a real word, which is exactly why O2 exists as a
     * token-matched control.
     */
    final class Opaque implements NameStrategy {
        @Override
        public Map<OWLEntity, String> assign(List<OWLEntity> entities, EntityType<?> type,
                                             OWLOntology source, long seed) {
            String prefix = Naming.typePrefix(type);
            // The index-to-entity assignment is permuted by the seed. Assigning indices in
            // signature order instead would make every seed produce the *same* mapping, so
            // C4 and C4S2 would be one condition wearing two names and the self-consistency
            // contrast -- two logically identical renamings the model should answer
            // identically -- would compare a run against itself.
            List<Integer> indices = new ArrayList<>(entities.size());
            for (int i = 1; i <= entities.size(); i++) {
                indices.add(i);
            }
            Collections.shuffle(indices, new Random(seed * 1_000_003L + type.hashCode()));

            Map<OWLEntity, String> out = new LinkedHashMap<>();
            for (int i = 0; i < entities.size(); i++) {
                out.put(entities.get(i), String.format("%s_%06d", prefix, indices.get(i)));
            }
            return out;
        }

        @Override
        public String operatorId() {
            return "opaque";
        }
    }

    // ------------------------------------------------------------------ O2

    /**
     * O2, pseudowords: pronounceable, word-shaped, meaningless. The control for O1's tokenization
     * confound (spec section 24).
     *
     * <p>{@code family} selects a disjoint syllable inventory so that a model fine-tuned on one
     * family can be tested on a generator it has never seen (spec section 28.4).
     */
    final class Pseudoword implements NameStrategy {
        private static final String[][] ONSET_FAMILIES = {
                {"b", "d", "f", "k", "l", "m", "n", "p", "r", "s", "t", "v"},
                {"br", "tr", "dr", "kr", "pl", "gr", "st", "sl", "fl", "kl"},
                {"th", "sh", "ch", "z", "j", "g", "h", "w", "y", "q"},
        };
        private static final String[][] NUCLEUS_FAMILIES = {
                {"a", "e", "i", "o", "u"},
                {"ai", "ou", "ia", "ei", "au"},
                {"o", "u", "y", "ae", "eo"},
        };
        private static final String[] CODAS = {"", "n", "r", "s", "l", "m", "t"};

        private final int family;

        public Pseudoword(int family) {
            this.family = Math.floorMod(family, ONSET_FAMILIES.length);
        }

        @Override
        public Map<OWLEntity, String> assign(List<OWLEntity> entities, EntityType<?> type,
                                             OWLOntology source, long seed) {
            Set<String> blocked = Naming.lexicalBlocklist(source);
            Random rnd = new Random(seed * 31 + type.hashCode() + family);
            Map<OWLEntity, String> out = new LinkedHashMap<>();
            Set<String> used = new HashSet<>();
            // Length is matched to the *opaque* name format, not to the entity's label.
            // O2 exists as the token-matched control for O1: holding length fixed makes the
            // C4-vs-C5 contrast about word-likeness alone. Matching labels instead would make
            // pseudowords far longer than the opaque ids they are supposed to control for,
            // and the comparison would measure length as much as morphology.
            // (O3 is the control for O4 and matches label length instead -- different pair,
            // different target.)
            int opaqueLength = Naming.typePrefix(type).length() + 7;  // e.g. "C_000012"
            for (OWLEntity e : entities) {
                int targetLen = Math.max(4, opaqueLength);
                String w = null;
                for (int attempt = 0; attempt < 400 && w == null; attempt++) {
                    String cand = coin(rnd, targetLen);
                    if (!used.contains(cand.toLowerCase(Locale.ROOT))
                            && !blocked.contains(cand.toLowerCase(Locale.ROOT))) {
                        w = cand;
                    }
                }
                if (w == null) {
                    // Deterministic escape hatch; keeps injectivity when the space is exhausted.
                    w = coin(rnd, targetLen) + used.size();
                }
                used.add(w.toLowerCase(Locale.ROOT));
                out.put(e, Naming.caseFor(type, w));
            }
            return out;
        }

        private String coin(Random rnd, int targetLen) {
            String[] onsets = ONSET_FAMILIES[family];
            String[] nuclei = NUCLEUS_FAMILIES[family];
            StringBuilder sb = new StringBuilder();
            while (sb.length() < targetLen) {
                sb.append(onsets[rnd.nextInt(onsets.length)]);
                sb.append(nuclei[rnd.nextInt(nuclei.length)]);
                if (sb.length() >= targetLen - 1 && rnd.nextBoolean()) {
                    sb.append(CODAS[rnd.nextInt(CODAS.length)]);
                }
            }
            return sb.toString();
        }

        @Override
        public String operatorId() {
            return "pseudoword_f" + family;
        }
    }

    // ------------------------------------------------------------------ O3

    /**
     * O3, random natural-language decoys: real words with no relation to the entity. Tests whether
     * any word-shaped, meaning-bearing token helps, even an irrelevant one.
     */
    final class RandomDecoy implements NameStrategy {
        @Override
        public Map<OWLEntity, String> assign(List<OWLEntity> entities, EntityType<?> type,
                                             OWLOntology source, long seed) {
            boolean verbLike = type.equals(EntityType.OBJECT_PROPERTY)
                    || type.equals(EntityType.DATA_PROPERTY);
            List<String> pool = new ArrayList<>(verbLike ? WordLists.VERBS : WordLists.NOUNS);
            Set<String> blocked = Naming.lexicalBlocklist(source);
            pool.removeIf(w -> blocked.contains(w.toLowerCase(Locale.ROOT)));
            Collections.shuffle(pool, new Random(seed * 17 + type.hashCode()));

            // Length is matched to the entity's *display name*, because O3 is the control
            // for O4: the pair is meant to isolate "irrelevant word" from "misleading word".
            // Single short nouns against multi-word ontology labels
            // ("TransitionalMyocyteOfAtrioventricularBundle") would make the two conditions
            // differ in prompt length as much as in meaning, and the comparison would be
            // confounded rather than controlled.
            Map<OWLEntity, String> display = Naming.displayNames(source);
            Random rnd = new Random(seed * 17 + type.hashCode() + 1);

            Map<OWLEntity, String> out = new LinkedHashMap<>();
            Set<String> used = new HashSet<>();
            int i = 0;
            for (OWLEntity e : entities) {
                int target = Naming.toLocalName(
                        display.getOrDefault(e, Naming.localName(e))).length();
                // Stop at whichever word boundary lands *closest* to the target, rather than
                // at the first that exceeds it: always overshooting biases decoys long by
                // up to a whole word and leaves the C6-vs-C7 pair measurably unmatched.
                StringBuilder sb = new StringBuilder();
                for (int guard = 1; guard <= 12; guard++) {
                    String word = pool.get((i + guard) % pool.size());
                    String candidate = Character.toUpperCase(word.charAt(0)) + word.substring(1);
                    if (sb.length() > 0
                            && Math.abs(sb.length() + candidate.length() - target)
                            >= Math.abs(sb.length() - target)) {
                        break;
                    }
                    sb.append(candidate);
                }
                String name = sb.length() == 0 ? pool.get(i % pool.size()) : sb.toString();
                while (!used.add(name.toLowerCase(Locale.ROOT))) {
                    name = name + pool.get(rnd.nextInt(pool.size()));
                }
                out.put(e, Naming.caseFor(type, name));
                i++;
            }
            return out;
        }

        @Override
        public String operatorId() {
            return "random_decoy";
        }
    }

    // ------------------------------------------------------------------ O4

    /**
     * O4, adversarial semantic decoys: every entity is given the name of a <em>different</em>
     * entity that it is easy to confuse with, so the lexical channel actively contradicts the
     * logical structure.
     *
     * <p>Constructed as a fixed-point-free permutation of the existing names, which keeps it a
     * genuine typed bijection (spec section 12.6). Confusability comes from permuting inside
     * sibling groups: entities sharing an asserted parent are cyclically shifted, so
     * {@code Neuron} may be renamed {@code Astrocyte} and vice versa. Groups too small to permute
     * are merged into a single fallback cycle.
     */
    final class AdversarialDecoy implements NameStrategy {
        @Override
        public Map<OWLEntity, String> assign(List<OWLEntity> entities, EntityType<?> type,
                                             OWLOntology source, long seed) {
            // Names are taken from the partner's *display name* (its rdfs:label where it
            // has one), not its IRI local name. On an OBO ontology the local names are
            // accession codes, so permuting them would swap meaningless numbers and the
            // condition would not be semantically adversarial at all -- it would collapse
            // into a second opaque-renaming condition.
            Map<OWLEntity, String> display = Naming.displayNames(source);
            Map<OWLEntity, OWLEntity> shift = Derangement.siblingShift(entities, source);

            Map<OWLEntity, String> out = new LinkedHashMap<>();
            for (OWLEntity e : entities) {
                OWLEntity partner = shift.get(e);
                String name = display.getOrDefault(partner, Naming.localName(partner));
                out.put(e, Naming.caseFor(type, Naming.toLocalName(name)));
            }
            return out;
        }

        @Override
        public String operatorId() {
            return "adversarial_decoy";
        }
    }
}
