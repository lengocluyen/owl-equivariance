# Dataset Card — owl-equivariance benchmark

## What this is

Automatically generated, symbolically verified OWL 2 entailment questions, each shipped as
an **orbit**: the same logical problem presented under several typed signature isomorphisms
and annotation policies. No human annotation is involved at any stage; every label is
decided by an OWL reasoner.

## Source ontologies

Each entry is frozen by version IRI and SHA-256 content hash in the build manifest
(`data/certified/<id>/build_report.json`) and reproduced by
`scripts/reproduce_pilot.sh`.

| id | ontology | domain | license | profile | logical axioms | classes | preprocessing |
|---|---|---|---|---|---|---|---|
| `toy` | hand-built fixture | generic (people / organisations) | repository license | OWL 2 EL | 31 | 14 | none |
| `cl` | Cell Ontology, `cl-basic` | biomedical — cell types | CC BY 4.0 | OWL 2 EL | 5,065 | 3,616 | none |
| `po` | Plant Ontology | botany — plant anatomy and development | CC BY 4.0 | OWL 2 EL | ~3,000 | ~2,000 | EL fragment |

Both public ontologies are OBO Foundry releases redistributed under CC BY 4.0; benchmark
files derived from them inherit that license and its attribution requirement.

### EL-fragment preprocessing

ELK is complete for OWL 2 EL and nothing else, so an ontology outside EL would produce
unsound labels *without any error*. Most published ontologies miss EL by a handful of axioms
while being EL everywhere else — Plant Ontology by one `InverseObjectProperties` plus a few
nominals and inverse-property expressions.

`--el-fragment` removes exactly those axioms and reports how many, by type. The result is a
**different ontology**, not a view: dropping axioms removes entailments. Every claim is about
the fragment, which is what is shipped, hashed and reasoned over; `build_report.json` records
the removal count so the distance from the published artifact stays visible. Ontologies that
cannot be reduced to EL are rejected rather than silently reasoned over.

## Task families

| type | query shape | notes |
|---|---|---|
| `ATOMIC_SUBSUMPTION` | `SubClassOf(A B)` | positives prefer entailments that are **not** asserted verbatim, so the item tests inference rather than lookup |
| `INSTANCE_CHECKING` | `ClassAssertion(A a)` | requires an ABox; absent from ontologies that have none |
| `EXPRESSION_SUBSUMPTION` | `SubClassOf(A ObjectSomeValuesFrom(r B))` | planned; the generator is not implemented yet |

Property-assertion entailment (`T3` in the spec) is deliberately excluded: ELK does not
decide it, and shipping items whose labels the oracle cannot verify would defeat the point.

## Negatives

Every non-entailed item is **matched**, not sampled at random. It keeps the positive's
subject and swaps the object for a class that is close but provably not entailed:

| family | construction |
|---|---|
| `SIBLING` | shares an inferred parent with the true superclass |
| `NEARBY_BRANCH` | same region of the hierarchy under a common ancestor, wrong branch |
| `LEXICAL` | highest name similarity to the true superclass |
| `RANDOM` | unrelated class — retained only as an easy control |

Random negatives are trivially separable by noticing the two names have nothing to do with
each other, which is the lexical shortcut this study exists to remove. They are kept as a
control, never as the main negative family.

Candidates are rejected when the subject is unsatisfiable (everything is entailed of it) or
when the reverse subsumption holds (ambiguous to a reader, and a different phenomenon).

## Context

Each item carries the exact axiom list the model sees, plus a vocabulary block with the
lexical annotations the condition left in place.

- **Strategy** `LOCALITY_MODULE_BOTTOM`: the ⊥-locality module for the query signature, plus
  distractors drawn from `O \ M`.
- **Distractors are never synthesised.** A fabricated axiom would sit outside `O` and void
  the monotonicity argument that fixes the negative labels.
- **`label_preservation_certified`** is `true` on every shipped item, and every item's label
  is re-verified by the reasoner against its own context before emission.
- **Positive and negative contexts are size-matched.** Each negative targets the size of the
  positive it was derived from.

### Why ⊥ and not ⊥⊤*

Both module types are query-complete and both give correct labels, but the ⊥⊤*-module of two
*unrelated* classes is **empty** — correct (nothing over that signature is entailed) and
experimentally useless, since the model can answer NOT_ENTAILED without reading anything.
An earlier build using star modules shipped **59 of 60 negatives with zero axioms** while
passing every logical check. The ⊥-module retains each query entity's ancestor chain, which
is the material needed to decide the subsumption either way. See
[`transformation_certificates.md`](transformation_certificates.md).

The vocabulary block matters more than it looks. OBO ontologies name entities with opaque
accession numbers (`CL_0000540`), so their human-readable meaning lives entirely in
`rdfs:label` and the definition annotations. A prompt built only from functional-syntax
axioms would show no labels, and conditions C0, C1 and C2 would be the same prompt.

## Conditions

See [`transformation_certificates.md`](transformation_certificates.md) for what each
operator preserves and why. Summary: C0 reference, C1 opaque IRIs with labels kept, C2
original IRIs with labels removed, C4/C4S2/C4S3 fully de-lexicalized under three seeds, C5
pseudowords, C6 random real words, C7 adversarial decoys, C8 misleading labels on neutral
identifiers, C9 adversarial decoys with all annotations intact.

## Splits

Split assignment is at the **orbit** level: every variant of a base item lands in the same
split. `owleq validate` fails the dataset if this is violated. An orbit split across train
and test would put the training item, renamed, into the test set.

For generalization claims the split must be **by ontology**, not within one. A within-
ontology split may be reported as a secondary result but not as the headline.

## Tokenization controls

Two condition pairs only mean something if they are length-matched, and each is matched to a
**different** target:

| pair | isolates | matched to |
|---|---|---|
| C4 vs C5 | identifier morphology (opaque id vs pseudoword) | the opaque format's fixed width |
| C6 vs C7 | semantics (irrelevant word vs misleading word) | the entity's label length |

`owleq tokens` verifies both and refuses to certify either unless the counter can see inside
a whitespace token — fragmentation is sub-word, so a word count reports every de-lexicalized
condition as identical whatever the truth.

C5 vs C6 is deliberately **not** checked: it is not a primary contrast, and the two are
matched to different targets by design.

Separately, the reference contrast is confounded with prompt length by construction —
removing the vocabulary block makes C4 user prompts roughly 0.22× the length of C0's. That
is inherent to the manipulation, is reported as a warning, and is what the `token_delta`
covariate exists to control for.

## Known limitations

1. **Two real ontologies, both OBO.** `cl` and `po` differ in domain but share OBO modelling
   conventions and opaque accession IRIs. A third ontology with different conventions is
   needed before "generalizes across modelling styles" can be claimed. The spec's full-paper
   target is 5–10.
2. **Only atomic subsumption is populated.** Instance checking needs an ABox, which neither
   `cl-basic` nor `po` has; the expression-subsumption generator is not implemented yet.
   Task-type comparisons are therefore not yet available.
3. **Proof depth is a proxy.** `proof_depth` is the size of the smallest justification found
   by black-box contraction — reasoner-derived, but not the depth of a rule-level proof
   graph.
4. **Minimality is relative.** The justification search is capped, so "minimal" means
   "relative to the smallest justification found", not globally minimal.
5. **Bounded coverage.** OWL 2 EL only; no datatype reasoning, no OWL 2 DL constructs.
6. **Contamination is not excluded.** Both ontologies are public and predate any model used,
   so C0 performance may reflect memorization. That is precisely what the transformed
   conditions are for, but C0 should not be read as a clean measure of reasoning.
7. **The IRI channel is near-inert on OBO ontologies.** Their IRIs are already accession
   codes, so C0 and C1 are close to identical for a reader; the lexical signal lives in the
   labels. This is a property of OBO, not a defect, but it means C1 is a weak manipulation
   here and an ontology with meaningful IRIs is needed to exercise that channel.

## Changes that invalidate earlier builds

Datasets generated before these fixes should be regenerated, not reused:

- Contexts were built from ⊥⊤*-modules, which are empty for unrelated class pairs; **59 of
  60 negatives had zero axioms**.
- Opaque renaming ignored its seed, so C4, C4S2 and C4S3 were the same mapping.
- Target namespaces encoded the condition id and seed, leaking the experimental cell into
  every prompt.
- Adversarial decoys permuted IRI local names, which on OBO are accession codes — so C7 was
  a second opaque condition rather than a semantic one.
- Negative contexts were not size-matched to positives.

## Intended and unintended uses

**Intended.** Measuring answer-, orbit- and proof-level equivariance of LLM ontology
reasoning under logic-preserving renaming; isolating which lexical channel carries model
performance; as a training signal for isomorphism augmentation.

**Not intended.** Benchmarking symbolic reasoners (ELK is the oracle here, not the subject);
evaluating ontology construction or ontology learning; any claim about a model's private
reasoning process — only the cited support is verified, never the model's own account of how
it got there.

## Ethical considerations

No human subjects, no personally identifiable data, no annotator labor. Source ontologies
are public and redistributed under their own licenses. The main risk is misreading a result:
a drop under renaming shows a dependence on names, not an absence of reasoning, and the
paper-claim checklist in the spec (§45) exists to keep those distinct.
