# Transformation Certificates

What each operator claims to preserve, why, and what the code checks. This is the document
a reviewer should be able to read instead of the source.

Certificate types:

- **`BY_CONSTRUCTION`** — preservation follows from the semantics for every ontology and
  every query. The reasoner checks are software tests, not evidence.
- **`BY_MONOTONICITY`** — preservation follows from a monotonicity argument over a specific
  construction.
- **`PER_ITEM_VERIFIED`** — no general argument; each instance is checked individually.

---

## The core claim

Let `Σ(O) = Σ_C ∪ Σ_OP ∪ Σ_DP ∪ Σ_I` be the logical signature of an ontology `O`, and let

```
π = (π_C, π_OP, π_DP, π_I)
```

be a tuple of bijections, each mapping one typed vocabulary onto a fresh one of the same
type. Extend `π` recursively over class expressions, property expressions, axioms, and
queries.

**Claim.** For every axiom `q` over `Σ(O)`:

```
O ⊨ q   ⟺   π(O) ⊨ π(q)
```

**Argument.** An OWL 2 interpretation is a pair `I = (Δ, ·^I)` where `·^I` maps class names
to subsets of `Δ`, property names to relations over `Δ`, and individual names to elements
of `Δ`. Nothing in the definition of satisfaction inspects the *symbol* — only its image
under `·^I`. So for any interpretation `I` of `π(O)`, the interpretation `I∘π` defined by
`A^(I∘π) = (π(A))^I` interprets `O`, and this construction is a bijection between the
models of `O` and the models of `π(O)` that preserves satisfaction of every axiom. Hence
`O` and `π(O)` have isomorphic model classes, and entailment is preserved in both
directions. ∎

The claim is unconditional: it holds for every OWL 2 profile, every constructor, and every
query type. No implementation can make it false — only an implementation bug can make the
*code* fail to realise it, which is what the tests look for.

### Punning

An IRI may be used as more than one kind of entity (a class and an individual, say). Direct
Semantics interprets these through separate interpretation functions, so they are two
entities that happen to share a name.

The mapping is therefore keyed on `(IRI, EntityType)`, never on the IRI alone, and each
entity type gets its own target namespace. Consequences:

- A punned IRI receives **two independent images**, splitting the pun. This is sound: the
  two uses were already semantically independent, so splitting them is itself an
  isomorphism.
- The transform can never *create* a pun that was not present, because the target
  namespaces are disjoint by type.
- Injectivity is required **per type**, not globally — enforced in
  `SignatureIsomorphism`'s constructor, which builds the inverse keyed on the target
  *entity* rather than the target IRI.

Keying on the IRI alone — the behaviour of `OWLEntityRenamer` — would merge the two uses
into one entity and can change entailments.

---

## Operators

### O1 — Opaque identifiers (`opaque`)

`Professor → C_000012`, `worksFor → OP_000007`, `Alice → I_000421`

**Certificate: `BY_CONSTRUCTION`.**

Entities are sorted by IRI, then the *index sequence* is permuted with the seed before being
assigned. Both properties matter and they pull in opposite directions:

- **Same seed ⇒ same mapping.** The sort makes the build reproducible across runs and JVMs.
- **Different seed ⇒ different mapping.** The permutation is what makes C4, C4S2 and C4S3
  three genuinely different renamings. Assigning indices in signature order — the obvious
  implementation — makes every seed produce *identical* output, at which point the
  self-consistency contrast compares a run against itself and reports 0% disagreement no
  matter how the model behaves. `differentSeedsOfTheSameOperatorProduceDifferentMappings`
  and `theSameSeedReproducesTheSameMapping` pin both directions.

Built-in vocabulary (`owl:Thing`, `rdfs:*`, `xsd:*`) is excluded via `isBuiltIn()` and never
renamed. Datatypes and anonymous individuals are untouched.

**Known limitation, stated rather than hidden:** opaque identifiers tokenize very
differently from real words, so O1 alone confounds "no meaning" with "unusual token
sequence". This is precisely why O2 exists.

### O2 — Pseudowords (`pseudoword`)

`Professor → Tavrine`, `University → Mondera`

**Certificate: `BY_CONSTRUCTION`.**

Pronounceable, word-shaped, meaningless. Generated from consonant-vowel templates with a
per-family syllable inventory. Every candidate is checked against a blocklist built from the
ontology's own local names and annotation text, so a "meaningless" name can never coincide
with a real name from the same ontology.

**Length is matched to the opaque format, not to the ontology's labels.** O2 is the
token-matched control for O1: holding length fixed makes C4-vs-C5 a contrast about
identifier *morphology* alone. Matching label length instead would make pseudowords several
times longer than the `C_000012` identifiers they control for, and the comparison would
measure length as much as word-likeness. (O3 is the control for O4 and matches label length
instead — different pair, different target. `owleq tokens` verifies both.)

The `family` parameter selects a disjoint syllable inventory. A model fine-tuned on family
0 can therefore be tested on family 1 or 2 — a generator it has never seen (spec §28.4).

### O3 — Random natural-language decoys (`random_decoy`)

`Professor → River`, `worksFor → surrounds`

**Certificate: `BY_CONSTRUCTION`.**

Real words, drawn from domains no research ontology is about (furniture, weather,
transport, kitchenware). Classes get nouns, properties get verbs, matching the
part-of-speech conventions of ontology naming. Isolates "is a word" from "is the right
word": if C6 beats C5, word-shaped tokens help even when the words are irrelevant.

**Length is matched to the entity's label**, by composing several words where one is too
short. O3 is the control for O4, and O4's names are real ontology labels — often long
compounds like `TransitionalMyocyteOfAtrioventricularBundle`. Single short nouns against
those would make C6-vs-C7 differ in length as much as in meaning; measured on the Cell
Ontology, unmatched decoys left the pair 21.8% apart in prompt length.

### O4 — Adversarial semantic decoys (`adversarial_decoy`)

`Neuron → Astrocyte`, and `Astrocyte → Neuron`

**Certificate: `BY_CONSTRUCTION`.**

The strongest condition, and the one most easily misunderstood: it is *still a bijection*.
Every occurrence of an entity is renamed consistently, so the logical structure is
untouched — only the names now point at the wrong concepts.

Constructed as a fixed-point-free permutation of the existing names. Confusability comes
from permuting *within sibling groups*: entities sharing an asserted parent are cyclically
shifted, which is fixed-point-free for any group of size ≥ 2. Entities with no structural
neighbour fall back to a coarse lexical bucket, and leftovers are folded into a single
final cycle. A lone orphan in an ontology with no cycle at all maps to itself; this is
recorded rather than faked.

**Names come from labels, not IRI local names.** This is essential on OBO-style ontologies
and easy to get wrong. Their local names are accession codes (`CL_1000480`), so permuting
local names swaps meaningless numbers: the condition silently degenerates into a second
opaque renaming and cannot support the "adversarial semantic decoy vs neutral pseudoword"
comparison it exists for. The operator therefore reads each entity's `rdfs:label`, falling
back to the local name only when no label exists, and converts it to a legal local name
(`"dendritic cell"` → `DendriticCell`). The sibling-bucket fallback uses labels for the same
reason — bucketing on local names would put every OBO class in one bucket beginning `CL_`.
`adversarialDecoyNamesComeFromLabelsNotAccessionCodes` guards this.

Where two source IRIs share a local name, the permutation can produce a collision; a
deterministic `_2`, `_3` suffix restores injectivity.

### Identity (`none`)

**Certificate: `BY_CONSTRUCTION`** (trivially — the mapping is the identity).

Exists so the annotation-only conditions (C2, C3) can vary labels while leaving IRIs
untouched, which is what makes "C0 vs C2 isolates the label channel" true.

---

## Annotation policies

**Certificate: `BY_CONSTRUCTION`, and stronger than the operators'.**

Annotation axioms carry no weight under OWL 2 Direct Semantics. Every annotation policy is
therefore entailment-preserving *trivially* — not because of a careful argument, but
because the axioms it touches are semantically inert.

That inertness is the whole point of varying them: any behavioural change a policy causes
is, by definition, not a change in reasoning.

| Policy | Effect |
|---|---|
| `KEEP_ALL` | annotations retargeted to the new IRIs |
| `REMOVE_LABELS` | `rdfs:label`, `skos:prefLabel` dropped |
| `REMOVE_DEFINITIONS` | `IAO:0000115`, `rdfs:comment` dropped |
| `REMOVE_SYNONYMS` | `skos:altLabel`, `oboInOwl:has*Synonym` dropped |
| `REMOVE_ALL_LEXICAL` | every lexical channel dropped |
| `OPAQUE_LABELS` | label := the new (meaningless) local name |
| `MISLEADING_LABELS` | label := a confusable neighbour's label, via the same derangement as O4 |

Two details worth recording:

- **Ontology-level annotations are always dropped** in transformed variants. They name the
  source ontology and would reintroduce exactly the identifying signal the transform
  removes.
- **Axiom annotations are stripped** from logical axioms. OBO ontologies annotate axioms
  with provenance strings that leak source vocabulary.
- A punned subject IRI yields one annotation per image, preserving all lexical material
  rather than inventing an arbitrary tie-break.

`TransformPreservationTest.annotationPoliciesNeverTouchLogicalAxioms` asserts byte equality
of the canonical logical axiom set under every policy.

---

## Context construction

**Certificate: `BY_MONOTONICITY`.**

Each context is a set `Context` with `M ⊆ Context ⊆ O`, where `M` is a locality module for
the query signature.

- **Non-entailed queries.** `Context ⊆ O` and `O ⊭ q` imply `Context ⊭ q`. Adding axioms can
  only add entailments, so a subset of a non-entailing ontology cannot entail `q`.
- **Entailed queries.** `Context ⊇ J` for a justification `J` with `J ⊨ q`, so `Context ⊨ q`.

**Why a module and not just a justification.** For a negative item, a small hand-picked
context would make "not entailed" true but uninteresting — the model could be right for the
wrong reason, having simply not been shown the relevant part of the ontology. A locality
module is *query-complete* for its signature: for any axiom `α` over `sig(M)`, `O ⊨ α` iff
`M ⊨ α` (Cuenca Grau, Horrocks, Kazakov, Sattler). A model answering NOT_ENTAILED from `M`
is answering the question the full ontology poses.

### ⊥-modules, not ⊥⊤*-modules — and why the distinction is not cosmetic

Both module types are query-complete, so **both give correct labels**. They differ sharply
in what they leave for a *non-entailed* query, and that difference decided the choice.

The ⊥⊤*-(star) module of two **unrelated** classes is **empty**. This is correct: once the
symbols outside the signature are replaced by ⊤, every axiom becomes a tautology and is
discarded, and indeed nothing over that signature is entailed. It is also experimentally
fatal — the model is asked to reject a subsumption having been shown *no axioms at all*, and
can answer correctly by noticing the context is empty.

This is not hypothetical. An earlier build of this benchmark used star modules and shipped
**59 of 60 negative items with zero axioms**, while passing every logical check, because
logical certification and experimental adequacy are different questions.

The ⊥-module keeps the full ancestor chain of each query entity — exactly the material
needed to decide the subsumption either way — and yields comparable contexts for entailed
and non-entailed items. `bottomModuleKeepsEvidenceWhereTheStarModuleDiscardsIt` pins the
contrast; `localityModulesAgreeWithTheFullOntologyOnTheirSignature` confirms both types
remain query-complete.

### Size matching between labels

Contexts are built in two passes: positives first, each sized from its own module plus the
distractor budget; then negatives, each **targeting the size of the positive it was derived
from**. Without this, negatives come out systematically smaller — the module of an unrelated
class pair is thinner than that of an entailed one — and *context length alone predicts the
label*, which a model can exploit without reading anything.

The target is a target, not a licence to discard evidence: a target below the module size
yields the module. Padding is bounded by the axioms the ontology actually contains.

**Distractors are drawn from `O \ M`, never synthesised.** A fabricated axiom would sit
outside `O` and void the subset argument, forcing a per-item recheck and — worse — changing
what the negative label means. The distractor pool is seeded from the query signature as
well as the module's, so an item with a small module still has a neighbourhood to draw from;
without that, a small module yields an empty pool and therefore an empty context.

When a module exceeds the size budget it is trimmed around the justification, and the item
is marked accordingly. Trimming preserves the subset property, so negatives stay certified
either way; positives stay certified exactly when the justification survives. An item whose
context would still be empty is dropped and counted, never shipped.

---

## Namespace neutrality

Every condition and seed writes into the **same** target namespace.

An earlier build encoded them (`urn:owleq:c7:42:c#X`), which put the experimental cell into
every IRI printed in the prompt. That tells the model which condition it is in — that the
names are adversarial, or that two variants are the same problem under different seeds — and
turns a blind manipulation into a labelled one. `namespacesDoNotLeakTheConditionOrSeed`
asserts that no condition id or seed appears in the transformed vocabulary, and
`check_condition_leakage` re-checks it on the shipped dataset.

---

## Order equivariance

The context is built **once**, in the source vocabulary, and each orbit member is produced
by mapping that ordered list axiom by axiom. Every variant therefore presents the same
axioms in the same positions under the same identifiers.

This matters for two reasons. Rebuilding the context per variant would let axiom order
drift, confounding renaming with presentation. And because identifier `A7` denotes
corresponding axioms in every variant, support-set comparison across conditions is a
straightforward set operation rather than an inverse-mapping exercise.

---

## What is *not* claimed

Stated explicitly, because the gap between these and the claims above is where a reviewer
will look first.

1. **No canonical form.** Nothing here computes a canonical normal form for arbitrary OWL 2
   DL ontologies. The deterministic serialization exists for reproducible hashing, not
   semantic canonicalization: two logically equivalent ontologies may serialize differently.
2. **No conservative-extension checking.** Transformations preserve semantics by
   construction; the system does not decide arbitrary conservative-extension problems.
3. **The reasoner is assumed correct.** ELK is a reference oracle, not an experimental
   subject. A cross-reasoner check is available for a subset; disagreements are treated as
   pipeline defects requiring analysis, never resolved by majority vote.
4. **Proof depth is a proxy.** The recorded `proof_depth` is the size of the smallest
   justification found by black-box contraction — a reasoner-derived difficulty measure, but
   not the depth of a rule-level proof graph (spec §11.2 Level 2).
5. **Justification enumeration is bounded.** The hitting-set search is capped, so
   "minimality" means "relative to the smallest justification found", not globally minimal.

---

## Validation performed

| Check | Where | What it catches |
|---|---|---|
| Constructor round-trip `inverse(π(O)) = O` | `TransformPreservationTest` | dropped fillers, mishandled nesting; 16 constructor fixtures × 4 operators |
| Pun independence and reversibility | `TransformPreservationTest` | IRI-keyed mapping collapsing two entities |
| Identity mapping on punned ontologies | `TransformPreservationTest` | injectivity checked globally instead of per type |
| Annotation isolation | `TransformPreservationTest` | annotation policy leaking into logical axioms |
| Randomised preservation | `TransformPreservationTest` | random EL ontologies × random bijections × sampled queries |
| Golden entailments under all 14 conditions | `GoldenOntologyTest` | any answer change a reader can check by eye |
| Original names fully removed | `GoldenOntologyTest` | vocabulary leaking through an unhandled axiom type |
| Module ⇔ full ontology agreement | `ContextAndSupportTest` | module extraction that is not query-complete |
| Distractors never change a label | `ContextAndSupportTest` | 0/3/10/50 distractors, all class pairs |
| Stored label holds against its own context | `ContextAndSupportTest` | the property the dataset actually asserts |
| Orbit members structurally identical | `ContextAndSupportTest` | axiom id or ordering drift between variants |
| Reference support valid and minimal | `ContextAndSupportTest` | a broken justification finder |
| Sampled entailments beyond the benchmark | `validate-orbit --sample` | constructor bugs hiding outside the query set |
