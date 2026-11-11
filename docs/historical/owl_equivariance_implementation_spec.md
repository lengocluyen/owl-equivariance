# Implementation Specification  
## Do LLMs Preserve OWL Reasoning Beyond Entity Names?

**Working project name:** `owl-equivariance`  
**Working paper title:** *Do LLMs Preserve OWL Proofs Beyond Entity Names? A Certified Isomorphism and Lexical-Channel Audit*  
**Document status:** Implementation specification, version 1.0  
**Intended scope:** A focused pilot leading to an ISWC/ESWC-style paper, with a possible later journal extension  
**Human participants:** None  
**Primary evaluation:** Automatically generated and symbolically verified OWL entailment tasks  
**Recommended first fragment:** OWL 2 EL  
**Primary symbolic reasoner:** ELK  
**Optional second reasoner:** HermiT for selected OWL 2 DL cases  

---

# 1. Executive Summary

This project evaluates whether large language models genuinely reason over the formal structure of OWL ontologies or rely primarily on the lexical meaning of class names, property names, individual names, and annotations.

The central experimental intervention is a **typed signature isomorphism**. Every class, object property, data property, and named individual is consistently renamed through a sort-preserving bijection. The transformed ontology is logically isomorphic to the original ontology. The query and expected entity-valued answers are transformed using the same mapping. Therefore, the entailment result must remain unchanged.

The project does not merely compare accuracy before and after renaming. It evaluates:

1. final-answer correctness;
2. consistency across multiple logically equivalent variants of the same problem;
3. proof validity;
4. proof support and inference-pattern consistency;
5. dependence on separate lexical channels:
   - IRI local names;
   - `rdfs:label`;
   - synonyms;
   - definitions;
   - comments;
6. robustness across OWL reasoning types and proof depths;
7. whether augmentation with isomorphic variants improves robustness.

The first implementation should remain deliberately narrow:

- use only reasoning tasks whose labels can be generated and verified automatically;
- begin with OWL 2 EL;
- use a small set of transformations that preserve semantics by construction;
- use symbolic reasoners only as generators and validators;
- avoid claims about arbitrary OWL normalization or conservative extension;
- avoid symbolic-reasoner runtime as a main research contribution;
- avoid generic “LLMs are brittle” claims.

The pilot should answer a go/no-go question:

> Does proof-level and lexical-channel analysis reveal a substantial, reproducible phenomenon beyond the already-known accuracy drop under logical obfuscation?

If the pilot only shows that opaque identifiers reduce accuracy, the project should stop or be reduced to a workshop contribution. If it reveals systematic proof instability, channel-specific effects, constructor-specific failure patterns, or a useful structural defense, it can support a strong full paper.

---

# 2. Research Objective

## 2.1 Main research question

Given an OWL ontology \(O\), a query \(q\), and a typed signature isomorphism \(\pi\), does an LLM preserve:

1. the final entailment decision;
2. the validity of the generated proof;
3. the logical support used in the proof;
4. the reasoning strategy;

when processing \((O,q)\) and \((\pi(O),\pi(q))\)?

## 2.2 Recommended research questions

### RQ1 — Answer equivariance

How much does final-answer performance change under certified OWL signature isomorphisms?

### RQ2 — Lexical-channel dependence

How much of the model’s performance comes from:

- formal OWL structure;
- IRI local names;
- human-readable labels;
- definitions and synonyms?

### RQ3 — Proof equivariance

When final answers remain correct, does the model preserve a valid and structurally corresponding proof?

### RQ4 — Failure conditions

How are robustness failures associated with:

- proof depth;
- axiom type;
- ontology size;
- vocabulary frequency;
- lexical similarity;
- positive versus non-entailed queries;
- model size and prompting method?

### RQ5 — Defense

Can typed-isomorphism augmentation improve robust orbit accuracy on unseen ontologies and unseen renaming families without significantly reducing original-name accuracy?

## 2.3 Central hypothesis

A language model may appear competent on ontology reasoning because meaningful ontology names activate pretrained lexical and factual associations. Under a typed isomorphism that preserves all logical relationships but removes or reverses those lexical cues, the model may:

- change a previously correct answer;
- produce an invalid proof;
- cite irrelevant premises;
- fail to apply the same inference pattern.

## 2.4 Narrow novelty claim

Do not claim that this project is the first study of logical obfuscation or symbolic renaming.

A defensible claim is:

> We define and implement certified typed-signature transformation orbits for OWL reasoning, isolate the contributions of formal and annotation channels, and evaluate both answer-level and proof-level equivariance over real public ontologies.

A stronger later claim is possible only if the project implements a structural model with architectural equivariance.

---

# 3. Non-Goals

The first paper should explicitly exclude the following.

1. **Arbitrary OWL canonicalization**  
   There is no attempt to compute a canonical normal form for arbitrary OWL 2 DL ontologies.

2. **General conservative-extension checking**  
   Transformations must preserve semantics by construction. The system does not decide arbitrary conservative-extension problems.

3. **Symbolic-reasoner bug discovery**  
   ELK, HermiT, or another reasoner is used as a symbolic reference, not as the primary experimental subject.

4. **Reasoner runtime optimization**  
   Runtime can be reported for pipeline practicality, but it is not the primary scientific result.

5. **Ontology learning from labels**  
   Tasks requiring a model to infer a definition from a class name are excluded from the core reasoning benchmark.

6. **External factual knowledge**  
   Each query must be answerable from the provided ontology fragment.

7. **Natural-language commonsense reasoning**  
   The benchmark targets formal OWL entailment, not informal commonsense inference.

8. **Full SROIQ coverage in the first version**  
   Begin with OWL 2 EL. Add selected constructs only after the pipeline is stable.

9. **Unverified chain-of-thought evaluation**  
   Free-form reasoning text is not accepted as a proof unless it can be parsed into a formal proof representation and verified.

---

# 4. Formal Problem Definition

## 4.1 OWL signature

Let the logical signature of ontology \(O\) be:

\[
\Sigma(O) =
\Sigma_C \cup
\Sigma_{OP} \cup
\Sigma_{DP} \cup
\Sigma_I
\]

where:

- \(\Sigma_C\): named classes;
- \(\Sigma_{OP}\): named object properties;
- \(\Sigma_{DP}\): named data properties;
- \(\Sigma_I\): named individuals.

Annotation properties should be handled separately because annotation axioms do not contribute to OWL 2 Direct Semantics in the same way as logical axioms.

## 4.2 Typed signature isomorphism

A transformation \(\pi\) is a tuple of bijections:

\[
\pi =
(\pi_C,\pi_{OP},\pi_{DP},\pi_I)
\]

with:

\[
\pi_C:\Sigma_C\rightarrow\Sigma_C',
\quad
\pi_{OP}:\Sigma_{OP}\rightarrow\Sigma_{OP}',
\]

\[
\pi_{DP}:\Sigma_{DP}\rightarrow\Sigma_{DP}',
\quad
\pi_I:\Sigma_I\rightarrow\Sigma_I'.
\]

No entity can change its OWL type. A class cannot be renamed to an object property, and an individual cannot be renamed to a class.

## 4.3 Recursive extension

The mapping is extended recursively to:

- class expressions;
- property expressions;
- individuals;
- logical axioms;
- ontology imports when included;
- test queries;
- entity-valued expected answers;
- formal proofs.

For example:

\[
\pi(A\sqsubseteq \exists r.B)
=
\pi_C(A)
\sqsubseteq
\exists \pi_{OP}(r).\pi_C(B).
\]

## 4.4 Preservation requirement

For all supported test axioms or queries \(q\):

\[
O\models q
\iff
\pi(O)\models \pi(q).
\]

For an answer set:

\[
Ans(\pi(O),\pi(q))
=
\pi(Ans(O,q)).
\]

For a Boolean query, the answer must be identical.

## 4.5 Proof equivariance

Let a formal proof be represented as a directed acyclic graph:

\[
P=(V,E,\ell)
\]

where:

- \(V\) contains premises and derived axioms;
- \(E\) records inference dependencies;
- \(\ell\) assigns an inference-rule label to each derived node.

A strict proof-equivariance condition is:

\[
P_{\pi}
\cong
\pi(P)
\]

where graph isomorphism preserves:

- transformed axiom labels;
- inference-rule labels;
- dependency edges.

A weaker condition is justification equivalence:

\[
Support(P_{\pi})
=
\pi(Support(P)).
\]

Because multiple valid proofs may exist, exact graph identity should not be required by default. The evaluation should distinguish:

1. **proof validity**;
2. **support equivalence**;
3. **rule-sequence equivalence**;
4. **exact proof-graph isomorphism**, where applicable.

## 4.6 Three-valued model output

The preferred output labels are:

- `ENTAILED`;
- `NOT_ENTAILED`;
- `UNKNOWN` or `INVALID_INPUT`, optionally.

For the core benchmark, include only cases where the symbolic reasoner returns a verified binary label. The LLM should not equate `NOT_ENTAILED` with classical negation.

---

# 5. System Architecture

## 5.1 High-level components

The recommended architecture contains two main services and one shared artifact store.

```text
┌─────────────────────────────────────────────────────────────┐
│                     Python Experiment Layer                 │
│                                                             │
│  Dataset Manager → Prompt Builder → Model Runner             │
│          ↓              ↓              ↓                    │
│  Transform Config → Response Parser → Metrics Engine         │
│          ↓                             ↓                    │
│  Training Pipeline             Reports / Figures            │
└──────────────────────────┬──────────────────────────────────┘
                           │ JSONL / REST / CLI
┌──────────────────────────▼──────────────────────────────────┐
│                       Java OWL Service                      │
│                                                            │
│ OWLAPI Loader → Profile Checker → Query Generator           │
│      ↓                ↓                ↓                    │
│ Transformation Engine → ELK/HermiT → Proof/Support Exporter │
│      ↓                                  ↓                   │
│ Certification Manifest          Validation Reports          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  Versioned Artifact Store                   │
│ ontologies / mappings / questions / proofs / predictions   │
└─────────────────────────────────────────────────────────────┘
```

## 5.2 Why Java plus Python

### Java layer

Use Java for:

- OWLAPI ontology parsing and rewriting;
- reliable entity-type handling;
- OWL profile validation;
- integration with ELK;
- optional integration with HermiT;
- entailment checking;
- proof or explanation extraction where supported;
- deterministic serialization.

### Python layer

Use Python for:

- experiment configuration;
- local and API model inference;
- prompt generation;
- response parsing;
- statistics;
- fine-tuning;
- plots and tables;
- reproducibility scripts.

Do not implement formal OWL rewriting through string replacement. All logical transformations must operate on OWLAPI entity and axiom objects.

---

# 6. Recommended Repository Structure

```text
owl-equivariance/
├── README.md
├── LICENSE
├── CITATION.cff
├── pyproject.toml
├── Makefile
├── docker-compose.yml
├── .env.example
├── configs/
│   ├── datasets/
│   │   ├── pilot_obo.yaml
│   │   ├── ontourl_reasoning.yaml
│   │   └── full_benchmark.yaml
│   ├── transforms/
│   │   ├── opaque.yaml
│   │   ├── pseudoword.yaml
│   │   ├── random_decoy.yaml
│   │   ├── adversarial_decoy.yaml
│   │   └── lexical_channels.yaml
│   ├── models/
│   │   ├── local_small.yaml
│   │   ├── local_medium.yaml
│   │   └── api_models.yaml
│   ├── prompts/
│   │   ├── direct.yaml
│   │   ├── structured_proof.yaml
│   │   └── few_shot.yaml
│   └── experiments/
│       ├── pilot.yaml
│       ├── proof_audit.yaml
│       └── augmentation.yaml
├── java/
│   └── owl-certifier/
│       ├── pom.xml
│       ├── src/main/java/org/owleq/
│       │   ├── cli/
│       │   ├── io/
│       │   ├── model/
│       │   ├── profile/
│       │   ├── query/
│       │   ├── reasoner/
│       │   ├── transform/
│       │   ├── proof/
│       │   └── validation/
│       └── src/test/
├── src/owl_equivariance/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── data/
│   │   ├── schemas.py
│   │   ├── loader.py
│   │   ├── split.py
│   │   └── validation.py
│   ├── prompting/
│   │   ├── templates.py
│   │   ├── verbalizer.py
│   │   └── few_shot.py
│   ├── models/
│   │   ├── base.py
│   │   ├── hf_runner.py
│   │   ├── vllm_runner.py
│   │   └── api_runner.py
│   ├── parsing/
│   │   ├── answer_parser.py
│   │   ├── proof_parser.py
│   │   └── repair.py
│   ├── evaluation/
│   │   ├── answer_metrics.py
│   │   ├── orbit_metrics.py
│   │   ├── proof_metrics.py
│   │   ├── calibration.py
│   │   └── statistics.py
│   ├── training/
│   │   ├── dataset.py
│   │   ├── augment.py
│   │   ├── supervised.py
│   │   └── consistency.py
│   └── reporting/
│       ├── tables.py
│       ├── plots.py
│       └── paper_export.py
├── scripts/
│   ├── download_ontologies.py
│   ├── build_java.sh
│   ├── generate_queries.sh
│   ├── generate_orbits.sh
│   ├── validate_dataset.sh
│   ├── run_inference.sh
│   ├── evaluate.sh
│   └── reproduce_pilot.sh
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── certified/
│   ├── splits/
│   └── predictions/
├── tests/
│   ├── test_schemas.py
│   ├── test_mapping_roundtrip.py
│   ├── test_answer_parser.py
│   ├── test_orbit_metrics.py
│   └── fixtures/
├── reports/
│   ├── pilot/
│   ├── full/
│   └── figures/
└── docs/
    ├── dataset_card.md
    ├── transformation_certificates.md
    ├── model_card.md
    └── reproducibility.md
```

---

# 7. Technology Stack

## 7.1 Java symbolic stack

Recommended:

- Java LTS version supported by the selected OWLAPI dependencies;
- OWLAPI;
- ELK reasoner for OWL 2 EL;
- HermiT for selected OWL 2 DL validation;
- Jackson for JSON;
- Picocli for command-line interfaces;
- JUnit for tests;
- Maven for builds.

Optional:

- ROBOT as an independent command-line validation layer;
- an OWL explanation library if compatible with the selected OWLAPI version.

## 7.2 Python stack

Recommended:

- Python 3.11 or later;
- `pydantic` for schemas;
- `PyYAML` for configuration;
- `pandas` and `numpy`;
- `scikit-learn`;
- `scipy`;
- `statsmodels`;
- `transformers`;
- `datasets`;
- `accelerate`;
- `peft`;
- `trl`, where needed;
- `vllm` for high-throughput inference;
- `networkx` for proof-graph analysis;
- `matplotlib` for figures;
- `pytest`;
- `ruff`;
- `mypy`.

Pin exact versions in a lock file only when implementation begins. Do not hard-code model-specific APIs into the dataset or evaluation layers.

## 7.3 Storage format

Use:

- OWL Functional Syntax or RDF/XML for reasoner input;
- Turtle for human inspection;
- JSONL for benchmark instances;
- JSON for mapping manifests;
- Parquet for aggregated predictions and metrics.

The authoritative transformed ontology should be generated from OWLAPI objects, not from a text-rewritten Turtle file.

---

# 8. Public Ontology Selection

## 8.1 Pilot selection criteria

Choose ontologies that satisfy:

1. public availability;
2. a clear license;
3. valid OWL parsing;
4. compatibility with OWL 2 EL for the first pilot;
5. meaningful labels and identifiers;
6. enough inferred relations to generate nontrivial tasks;
7. manageable context size after module extraction;
8. no personally identifiable data.

## 8.2 Suggested pilot ontology profile

Use three ontologies with different characteristics:

### Ontology A — Small and clean

- fewer than approximately 5,000 logical axioms;
- shallow-to-medium hierarchy;
- many labels;
- useful for debugging.

### Ontology B — Medium biomedical ontology

- approximately 5,000–50,000 logical axioms;
- richer hierarchy;
- existential restrictions;
- useful for proof-depth analysis.

### Ontology C — Different domain or modeling style

- not only biomedical;
- different label conventions;
- useful for domain generalization.

The exact ontology list should be frozen in a dataset manifest with:

- ontology name;
- ontology version IRI;
- retrieval date;
- source identifier;
- license;
- SHA-256 checksum;
- OWL profile;
- axiom statistics;
- import-handling policy.

## 8.3 OntoURL usage

OntoURL can be used as:

- a comparison benchmark;
- a source of ontology reasoning task formats;
- an external generalization dataset.

Do not automatically include all OntoURL tasks. Restrict core experiments to tasks whose answers are formally determined by provided ontology axioms.

Exclude or separately analyze tasks involving:

- ontology construction;
- definitions inferred from names;
- semantic alignment based mainly on lexical meaning;
- external domain knowledge.

---

# 9. Ontology Preprocessing

## 9.1 Import policy

Choose one policy and record it per ontology:

1. **imports closure included**;
2. **root ontology only**;
3. **selected import closure**.

For reproducibility, the preferred policy is to materialize and checksum the complete selected import closure.

## 9.2 Annotation extraction

Extract separately:

- IRI full string;
- IRI local name;
- `rdfs:label`;
- `skos:prefLabel`;
- `skos:altLabel`;
- definitions;
- comments;
- synonyms;
- language tags.

Store these in a lexical-channel table instead of mixing them invisibly into the logical representation.

## 9.3 Profile validation

For each ontology:

1. load through OWLAPI;
2. compute OWL 2 profile membership;
3. reject or isolate profile violations;
4. record unsupported axiom types;
5. run consistency checking;
6. record unsatisfiable named classes.

For the pilot:

- select only consistent OWL 2 EL ontologies;
- exclude unsatisfiable classes from ordinary query generation unless inconsistency is a deliberate task.

## 9.4 Normalized serialization

Create an internal deterministic serialization:

- sort declarations;
- sort logical axioms by canonical textual key;
- sort annotations;
- use stable prefixes;
- use Unix line endings;
- record the SHA-256 hash.

This is for reproducibility, not a claim of semantic canonicalization.

---

# 10. Query Generation

## 10.1 Core task families

Begin with four task families.

### T1 — Atomic subsumption

Query:

\[
A\sqsubseteq B
\]

where \(A\) and \(B\) are named classes.

Positive examples are inferred subclass relationships not explicitly asserted when possible.

### T2 — Instance checking

Query:

\[
A(a)
\]

where \(A\) is a named class and \(a\) is a named individual.

Use only ontologies with a suitable ABox.

### T3 — Object-property assertion entailment

Query:

\[
r(a,b)
\]

Use only when the selected reasoner supports the required entailment checks and the ontology contains enough ABox structure.

### T4 — Class-expression subsumption

Examples:

\[
A\sqsubseteq \exists r.B
\]

\[
A\sqsubseteq B\sqcap C
\]

Include only carefully supported OWL EL expressions in the initial phase.

## 10.2 Positive-query generation

For atomic subsumption:

1. classify the ontology;
2. obtain inferred direct and indirect superclasses;
3. remove explicitly asserted subclass axioms for the “inferred-only” subset;
4. sample pairs across proof-depth bins.

Recommended depth bins:

- depth 1: direct asserted or immediate;
- depth 2–3;
- depth 4–6;
- depth 7+.

The exact proof depth must be derived from a proof or explanation graph when possible. Hierarchy path length alone is only a proxy.

## 10.3 Negative-query generation

Negative generation is critical.

Do not sample random unrelated classes only. Such negatives may be trivially easy.

Generate matched non-entailed queries:

1. choose a positive source class \(A\);
2. select a candidate target \(C\) that is not entailed;
3. match \(C\) to the positive target \(B\) by:
   - hierarchy depth;
   - frequency;
   - label length;
   - lexical similarity;
   - ontology region;
   - structural degree;
4. verify `NOT_ENTAILED` using the symbolic reasoner;
5. reject cases involving unsatisfiable source classes;
6. optionally reject candidates for which the reverse relation is entailed.

Negative categories:

- **sibling negative**;
- **nearby branch negative**;
- **lexically similar negative**;
- **adversarial lexical negative**;
- **random negative**, retained as an easy control.

## 10.4 Query balance

The pilot should contain approximately equal numbers of:

- entailed and non-entailed cases;
- shallow and deeper cases;
- original and transformed conditions;
- task families, where possible.

Use grouped sampling to avoid one ontology dominating the dataset.

## 10.5 Avoiding leakage

All variants of the same base item must belong to the same split.

Group identifier:

```text
base_item_id = ontology_id + task_type + source_axiom_hash
```

Never allow an original item in training and a renamed orbit member in testing.

Split by ontology for the main generalization experiment:

- training ontologies;
- validation ontologies;
- test ontologies.

A secondary within-ontology split can be reported, but it must not be the main result.

---

# 11. Formal Proof and Explanation Generation

## 11.1 Proof representation

Use a model-independent JSON proof schema.

```json
{
  "proof_id": "proof:abc123",
  "ontology_id": "go-2026-xx",
  "query_id": "q:000104",
  "conclusion": {
    "type": "SubClassOf",
    "sub": "http://example.org/A",
    "super": "http://example.org/B"
  },
  "nodes": [
    {
      "node_id": "n1",
      "axiom": "...",
      "kind": "asserted",
      "rule": null,
      "premises": []
    },
    {
      "node_id": "n2",
      "axiom": "...",
      "kind": "derived",
      "rule": "SUBCLASS_TRANSITIVITY",
      "premises": ["n1", "n3"]
    }
  ],
  "root_node": "n2",
  "reasoner": "ELK",
  "valid": true
}
```

## 11.2 Proof extraction levels

Implement three levels.

### Level 0 — Entailment only

Record only whether the reasoner entails the query.

This is mandatory for all instances.

### Level 1 — Justification support

Record one or more sets of asserted axioms sufficient for the entailment.

This is recommended for the pilot.

### Level 2 — Rule-labeled proof graph

Record inference steps and dependencies.

This is ideal but may depend on reasoner support and library compatibility.

The project must remain viable if Level 2 is only available for a subset.

## 11.3 Multiple proofs

Because an entailment may have multiple valid justifications:

- do not require an LLM to reproduce one exact proof;
- validate the proposed proof independently;
- compare its support to the set of known justifications where available;
- report whether it is:
  - valid;
  - minimal;
  - identical to a reference justification;
  - an alternative valid proof.

## 11.4 Proof validation

The safest validation strategy is deletion-based.

Given model-selected support \(S\) and conclusion \(q\):

1. create ontology \(O_S\) containing only axioms in \(S\);
2. run the symbolic reasoner;
3. test \(O_S\models q\);
4. optionally test minimality by removing each support axiom;
5. mark unsupported or malformed references.

This validates proof support even when the free-form inference text is not machine-verifiable.

## 11.5 Structured proof output

Require the model to return:

```json
{
  "label": "ENTAILED",
  "support_axiom_ids": ["a12", "a18", "a31"],
  "steps": [
    {
      "conclusion": "C_12 SubClassOf C_44",
      "premises": ["a12", "a18"],
      "rule": "subclass_transitivity"
    }
  ]
}
```

For the initial pilot, `support_axiom_ids` is more important than fully formal rule text.

---

# 12. Certified Transformation Engine

## 12.1 Operator registry

Every operator must implement:

```java
public interface CertifiedTransform {
    TransformResult apply(
        OWLOntology ontology,
        TransformConfig config,
        long seed
    );

    String operatorId();

    PreservationCertificate certificate();
}
```

## 12.2 Transform result

```json
{
  "operator_id": "typed-iri-renaming-v1",
  "seed": 104729,
  "source_ontology_hash": "...",
  "target_ontology_hash": "...",
  "mapping_file": "mappings/orbit_0001.json",
  "inverse_mapping_available": true,
  "certificate_type": "BY_CONSTRUCTION",
  "validation": {
    "source_consistent": true,
    "target_consistent": true,
    "sampled_entailments_preserved": true
  }
}
```

Reasoner validation is an implementation check. The primary certificate comes from the proven construction.

## 12.3 O1 — Opaque identifier renaming

Example:

```text
Professor → C_000012
worksFor  → OP_000007
Alice     → I_000421
```

Requirements:

- bijective within each entity type;
- no collisions;
- deterministic under seed;
- no original lexical material in generated local names;
- preserve built-in OWL/RDF/RDFS/XSD vocabulary;
- preserve datatypes;
- preserve anonymous individuals;
- transform the query and proof references.

Recommended patterns:

- classes: `C_000001`;
- object properties: `OP_000001`;
- data properties: `DP_000001`;
- individuals: `I_000001`.

## 12.4 O2 — Pseudoword renaming

Generate pronounceable but semantically empty tokens.

Example:

```text
Professor → Tavrine
University → Mondera
worksFor → nelicates
```

Requirements:

- separate generators by entity type;
- avoid real dictionary words;
- avoid ontology labels and synonyms;
- control token length;
- test tokenizer fragmentation;
- record token counts for each model tokenizer.

Generation approaches:

- constrained character-level Markov model;
- consonant-vowel templates;
- syllable inventory;
- fixed random seed.

Create multiple pseudoword families so the test set can use a generator not seen during training.

## 12.5 O3 — Random natural-language decoys

Map entities to unrelated natural-language words.

Example:

```text
Professor → River
Employee → Bicycle
worksFor → surrounds
```

Controls:

- match part of speech where practical;
- keep property names verb-like;
- keep class names noun-like;
- avoid words with a known relation to the original entity;
- match token length and frequency bands.

This operator tests whether any meaningful word helps, even when semantically irrelevant.

## 12.6 O4 — Adversarial semantic decoys

Map an entity to a misleading name likely to activate an incorrect prior.

Examples:

- swap sibling class names;
- map a class to a nearby but non-entailed class name;
- reverse directional property names:
  - `hasPart` ↔ `partOf`;
  - `parentOf` ↔ `childOf`;
- exchange source and target concepts in a common relation.

Important constraint:

The mapping must still be a global typed bijection. Every occurrence of the entity is consistently renamed in the ontology and query.

Adversarial selection objective:

\[
\pi^* =
\arg\max_{\pi}
LexicalConflict(\pi)
\]

subject to:

- type preservation;
- bijection;
- no logical-axiom modification.

Possible conflict score:

\[
LexicalConflict(A,\pi(A))
=
Sim(label(A),label(B_{wrong}))
+
StructuralMismatch(A,B_{wrong}).
\]

For the pilot, use rule-based adversarial mappings before learning an attack policy.

## 12.7 O5 — Annotation-channel interventions

These transformations modify annotation axioms while preserving logical axioms.

Conditions:

1. all annotations retained;
2. labels removed;
3. definitions removed;
4. synonyms removed;
5. all lexical annotations removed;
6. labels replaced by opaque strings;
7. labels replaced by misleading labels;
8. original labels retained after IRI renaming.

Each condition must be identified separately.

## 12.8 O6 — Conjunction split/merge

Optional structural operator:

\[
A\sqsubseteq B\sqcap C
\leftrightarrow
\{A\sqsubseteq B,\ A\sqsubseteq C\}.
\]

Implement only for axiom patterns with a simple proof of equivalence.

Record:

- number of transformed axioms;
- source and target axiom counts;
- whether the transformation is reversible;
- exact operator proof in `docs/transformation_certificates.md`.

Do not include this operator in the first pilot unless the renaming pipeline is already stable.

---

# 13. Mapping Manifest

Every transformed ontology must have a complete manifest.

```json
{
  "mapping_id": "map:go:opaque:seed42",
  "operator": "opaque",
  "seed": 42,
  "source_namespace": "http://purl.obolibrary.org/obo/",
  "target_namespace": "urn:owleq:opaque:42:",
  "classes": {
    "http://example.org/Professor": "urn:owleq:opaque:42:C_000001"
  },
  "object_properties": {
    "http://example.org/worksFor": "urn:owleq:opaque:42:OP_000001"
  },
  "data_properties": {},
  "individuals": {},
  "annotation_policy": "remove_all_lexical",
  "hashes": {
    "source_ontology": "...",
    "target_ontology": "...",
    "mapping": "..."
  }
}
```

Validation rules:

- all logical entities occur exactly once in the mapping;
- the inverse mapping is unique;
- built-in vocabulary is absent;
- source and target entity types match;
- query entities all exist in the mapping;
- mapping round-trip returns the original ontology structure modulo serialization.

---

# 14. Certification and Validation Tests

## 14.1 Unit-level transformation tests

For each supported OWL constructor, create fixture ontologies and test:

\[
inverse(transform(O)) = O
\]

up to axiom-set equality.

Required fixtures:

- subclass;
- equivalence;
- disjointness;
- existential restriction;
- conjunction;
- object-property hierarchy;
- transitivity;
- domain and range;
- class assertion;
- object-property assertion;
- data-property assertion if supported.

## 14.2 Query preservation test

For every generated instance:

1. reason over \(O\);
2. reason over \(\pi(O)\);
3. transform \(q\) to \(\pi(q)\);
4. assert that the Boolean entailment labels match;
5. inverse-map entity-valued answers;
6. assert answer-set equality.

Any failure invalidates the instance and should stop dataset release.

## 14.3 Sampled global check

For each transformed ontology, sample a larger set of axioms beyond the benchmark questions and verify preservation.

This is a software-quality check, not the formal proof of preservation.

## 14.4 Annotation isolation test

Verify that annotation-only conditions do not modify the logical axiom set.

Compute:

```text
logical_axioms(source) == logical_axioms(target)
```

after applying the inverse entity mapping where required.

## 14.5 Cross-reasoner check

For a subset:

- validate EL ontologies with ELK;
- optionally validate with a second compatible reasoner;
- investigate disagreements before using the data.

Do not majority-vote over reasoners. A disagreement indicates a pipeline or support issue requiring analysis.

---

# 15. Benchmark Instance Schema

Use a versioned Pydantic schema.

```json
{
  "schema_version": "1.0",
  "base_item_id": "go:T1:abc123",
  "orbit_item_id": "go:T1:abc123:opaque:seed42",
  "ontology": {
    "ontology_id": "go",
    "version": "frozen-version",
    "profile": "OWL2_EL",
    "source_hash": "...",
    "transformed_hash": "..."
  },
  "task": {
    "type": "ATOMIC_SUBSUMPTION",
    "query_functional": "SubClassOf(:C_01 :C_02)",
    "label": "ENTAILED",
    "positive": true,
    "proof_depth": 4,
    "explicit": false
  },
  "transform": {
    "operator": "opaque",
    "seed": 42,
    "mapping_id": "map:...",
    "lexical_condition": "opaque_iri_no_labels"
  },
  "context": {
    "axiom_ids": ["a1", "a2", "a3"],
    "serialization": "FUNCTIONAL",
    "token_count_by_model": {
      "model_a": 1600
    }
  },
  "reference": {
    "support_axiom_sets": [
      ["a1", "a3"]
    ],
    "reasoner": "ELK",
    "verified": true
  },
  "split": "test"
}
```

---

# 16. Context Construction

## 16.1 Why not provide the full ontology

Large public ontologies can exceed LLM context limits. Full-ontology prompting also introduces uncontrolled differences in input length.

Use a **certified query-preserving context** for the primary experiments.

Possible context strategies:

1. asserted proof support plus controlled distractors;
2. reasoner-generated justification plus neighborhood;
3. locality module;
4. fixed-radius signature module;
5. complete small ontology.

## 16.2 Recommended pilot context

For positive items:

- one verified justification;
- a fixed number of distractor axioms;
- all declarations needed for parsing;
- lexical annotations according to condition.

For negative items:

Use a query-complete module or a complete small ontology. A small support set cannot certify non-entailment.

Recommended approach:

- select small ontology modules around the query signature;
- verify that each module preserves the target query label relative to the full ontology;
- store a certificate that the full and module labels agree for the sampled query.

Be precise: this is per-query verified equivalence, not a universal completeness claim.

## 16.3 Distractor policy

Create controlled distractor bins:

- 0 distractors;
- 5;
- 20;
- 50;
- optional 100.

Distractor types:

- disconnected;
- same-signature neighborhood;
- lexically similar;
- structurally similar;
- misleading.

Use the same logical context structure across each orbit member after mapping.

## 16.4 Ordering

To avoid confounding from axiom order:

- define a deterministic base order;
- optionally include an independent ordering-ablation experiment;
- apply the same relative order across isomorphic variants.

Do not mix entity renaming with random axiom shuffling in the main analysis.

---

# 17. Prompt Design

## 17.1 Direct classification prompt

```text
You are given OWL axioms and one query.

Use only the supplied axioms.
Do not use outside knowledge.
Under the open-world assumption, decide whether the query is entailed.

Return exactly one JSON object:
{
  "label": "ENTAILED" or "NOT_ENTAILED",
  "support_axiom_ids": []
}

Ontology axioms:
[A1] ...
[A2] ...

Query:
...
```

## 17.2 Structured proof prompt

```text
Determine whether the query is entailed by the supplied OWL axioms.

Use only the listed axioms.
Entity names may be arbitrary and must not be interpreted using outside knowledge.

Return JSON:
{
  "label": "ENTAILED" or "NOT_ENTAILED",
  "support_axiom_ids": ["A1", "A2"],
  "proof_steps": [
    {
      "premises": ["A1", "A2"],
      "rule": "RULE_NAME",
      "conclusion": "..."
    }
  ]
}

If the query is not entailed, return an empty support list.
```

## 17.3 Prompt variants

Evaluate:

- direct answer;
- direct answer with “ignore entity names” instruction;
- structured proof;
- few-shot examples;
- few-shot examples with opaque names;
- tool-assisted symbolic checking, as an optional upper baseline.

## 17.4 Avoid uncontrolled chain-of-thought

Do not require hidden or unrestricted chain-of-thought. Ask for a concise, structured proof object.

Use only machine-verifiable fields in quantitative evaluation.

---

# 18. Model Selection

## 18.1 Pilot models

Use at least three model classes:

1. a small open-weight instruction model;
2. a medium open-weight instruction model;
3. a strong general model, local or API-based.

The exact choices should be determined at experiment time, based on:

- reproducibility;
- context capacity;
- license;
- inference cost;
- support for constrained JSON output;
- availability of token probabilities if calibration is evaluated.

## 18.2 Model metadata

Record:

- exact model identifier;
- revision or checksum;
- tokenizer revision;
- quantization;
- inference engine;
- GPU type;
- precision;
- temperature;
- top-p;
- maximum output tokens;
- system prompt;
- chat template;
- random seed.

## 18.3 Deterministic inference

Primary runs:

- temperature 0 or deterministic greedy decoding;
- fixed maximum token count;
- one response per item.

Robustness runs:

- multiple sampled responses;
- fixed seed set;
- report majority vote and self-consistency separately.

Do not mix deterministic and sampled results in the primary table.

---

# 19. Response Parsing

## 19.1 Strict parser

The parser should:

1. locate the first valid JSON object;
2. validate against a Pydantic schema;
3. normalize labels;
4. reject unknown axiom IDs;
5. reject duplicate steps where appropriate;
6. record raw output;
7. record parser error category.

## 19.2 Error categories

- no JSON;
- malformed JSON;
- missing label;
- invalid label;
- unknown support ID;
- unsupported proof syntax;
- output truncation;
- refusal;
- irrelevant natural-language response.

Parsing failure should count as incorrect in the main evaluation but also be reported separately.

## 19.3 Repair policy

For the primary scientific result, do not call another LLM to repair malformed output.

A deterministic repair can be used only for trivial syntax issues, with:

- original raw output preserved;
- repair action recorded;
- results reported with and without repair.

---

# 20. Answer-Level Metrics

## 20.1 Standard metrics

Report:

- accuracy;
- macro F1;
- precision and recall for `ENTAILED`;
- precision and recall for `NOT_ENTAILED`;
- invalid-output rate.

## 20.2 Invariance gap

For transformation \(T\):

\[
IG_T =
Acc_{original} - Acc_T.
\]

Also report confidence intervals.

## 20.3 Correct-to-wrong flip rate

\[
CWF_T =
\frac{
\#\{i: \hat y_i=y_i \land \hat y_{T(i)}\neq y_i\}
}{
\#\{i: \hat y_i=y_i\}
}.
\]

## 20.4 Wrong-to-correct flip rate

\[
WCF_T =
\frac{
\#\{i: \hat y_i\neq y_i \land \hat y_{T(i)}=y_i\}
}{
\#\{i: \hat y_i\neq y_i\}
}.
\]

This identifies cases where original lexical priors were harmful.

## 20.5 Pair consistency

\[
PC_T =
\frac{1}{N}
\sum_i
\mathbf 1[
\hat y_i = \hat y_{T(i)}
].
\]

High consistency is not sufficient if both answers are wrong. Always report consistency alongside correctness.

---

# 21. Orbit-Level Metrics

Let each base item have orbit:

\[
Orb(x_i)=\{x_i,T_1(x_i),\ldots,T_K(x_i)\}.
\]

## 21.1 Robust orbit accuracy

\[
ROA =
\frac{1}{N}
\sum_i
\mathbf 1[
\forall z\in Orb(x_i), f(z)=y_i
].
\]

## 21.2 Orbit consistency

\[
OC =
\frac{1}{N}
\sum_i
\mathbf 1[
\forall z,z'\in Orb(x_i), f(z)=f(z')
].
\]

## 21.3 Worst-condition accuracy

\[
WCA =
\min_{c\in Conditions} Acc_c.
\]

## 21.4 Average orbit degradation

For item \(i\):

\[
OD_i =
Correct(x_i)
-
\frac{1}{K}\sum_{k=1}^{K} Correct(T_k(x_i)).
\]

Analyze the distribution, not only the mean.

## 21.5 Orbit entropy

For probabilistic outputs:

\[
H_i =
H\left(
\frac{1}{K+1}
\sum_{z\in Orb(x_i)}
p_\theta(y\mid z)
\right).
\]

Also measure within-orbit probability variance.

---

# 22. Proof-Level Metrics

## 22.1 Support validity

\[
SupportValid =
\mathbf 1[
O_{S}\models q
]
\]

where \(S\) is the model-selected support.

## 22.2 Support precision

Given reference support union \(R\):

\[
Precision_S =
\frac{|S\cap R|}{|S|}.
\]

Use carefully because alternative valid supports may not appear in a limited reference set.

## 22.3 Minimality ratio

\[
MR =
\frac{|S|}
{|S_{min}|}
\]

where \(S_{min}\) is the size of the smallest known justification.

Label it “relative to smallest known justification,” not globally minimal unless all justifications are enumerated.

## 22.4 Proof-validity orbit accuracy

\[
PVOA =
\frac{1}{N}
\sum_i
\mathbf 1[
\forall z\in Orb(x_i),
AnswerCorrect(z)
\land ProofValid(z)
].
\]

## 22.5 Support equivariance

Inverse-map transformed support:

\[
SE_T =
Jaccard(
S_i,
\pi^{-1}(S_{T(i)})
).
\]

Interpretation must account for multiple valid proofs.

## 22.6 Rule-pattern consistency

Represent each proof as a multiset or sequence of rule categories. Compare:

- exact sequence equality;
- multiset Jaccard;
- edit distance;
- graph-kernel similarity.

Use rule-pattern consistency as descriptive analysis, not the primary correctness criterion.

## 22.7 Correct-answer invalid-proof rate

\[
CAIP =
P(
AnswerCorrect \land \neg ProofValid
).
\]

This is a central metric because it captures answer success without formal reasoning support.

---

# 23. Lexical-Channel Experimental Matrix

Use a factorial design.

| Condition | IRI local names | Labels | Definitions/synonyms |
|---|---|---|---|
| C0 | Original | Original | Original |
| C1 | Opaque | Original | Original |
| C2 | Original | Removed | Original |
| C3 | Original | Original | Removed |
| C4 | Opaque | Removed | Removed |
| C5 | Pseudoword | Removed | Removed |
| C6 | Random decoy | Removed | Removed |
| C7 | Adversarial decoy | Removed | Removed |
| C8 | Opaque | Misleading | Removed |
| C9 | Adversarial decoy | Original | Original |

The minimal pilot can use C0, C1, C4, C7, and C8.

## 23.1 Key causal comparisons

- C0 vs C1: effect of IRI local name when annotations remain;
- C0 vs C2: effect of labels;
- C1 vs C4: effect of annotations under opaque IRIs;
- C4 vs C5: identifier morphology/tokenization;
- C6 vs C7: random versus semantically adversarial names;
- C4 vs C8: misleading label effect when IRI is neutral.

---

# 24. Tokenization Controls

Renaming may change token count and fragmentation. This is a major confound.

For every model and entity name, record:

- number of tokenizer tokens;
- average tokens per entity;
- maximum tokens per entity;
- percentage of single-token names;
- context token count.

## 24.1 Matched renaming conditions

Construct matched opaque and pseudoword variants with similar:

- token count;
- character length;
- frequency;
- capitalization pattern.

## 24.2 Analysis

Regress correctness on:

- transformation type;
- token count difference;
- proof depth;
- context length;
- ontology;
- task type.

The transformation effect must remain after controlling for tokenization.

---

# 25. Statistical Analysis

## 25.1 Paired tests

Because transformed items correspond to the same base item, use paired tests.

Recommended:

- McNemar’s test for paired binary correctness;
- paired bootstrap confidence intervals;
- permutation tests for orbit metrics.

## 25.2 Mixed-effects model

A recommended logistic model:

\[
logit(P(correct)) =
\beta_0
+\beta_1 Transform
+\beta_2 ProofDepth
+\beta_3 TokenDelta
+\beta_4 TaskType
+\beta_5 LabelCondition
+u_{ontology}
+u_{item}.
\]

Random effects:

- ontology;
- base item.

Optional random effect:

- model family.

## 25.3 Multiple comparisons

Predefine primary comparisons and apply a correction such as Holm for secondary condition-wise tests.

## 25.4 Effect sizes

Report:

- percentage-point accuracy changes;
- odds ratios;
- paired risk differences;
- confidence intervals.

Do not rely only on p-values.

---

# 26. Pilot Experiment

## 26.1 Pilot size

Target:

- 3 ontologies;
- 300–500 base items per ontology;
- balanced positive and negative labels;
- 4 transformed conditions plus original;
- 3 models;
- 2 prompt styles.

Approximate number of deterministic predictions:

\[
3 \times 400 \times 5 \times 3 \times 2
=
36,000.
\]

This is large enough to reveal a stable effect but still practical.

## 26.2 Pilot phases

### Phase P0 — Pipeline smoke test

- 1 toy ontology;
- 20 queries;
- opaque renaming only;
- 1 local model.

Success condition:

- exact round-trip mapping;
- transformed labels all preserved;
- predictions and metrics run end to end.

### Phase P1 — Answer audit

- 3 ontologies;
- original, opaque, pseudoword, adversarial decoy;
- 3 models;
- direct prompt.

### Phase P2 — Lexical channels

- labels retained versus removed;
- definitions retained versus removed;
- IRI and label interaction.

### Phase P3 — Proof audit

- subset of 200–300 positive items;
- structured support output;
- symbolic support validation.

### Phase P4 — Defense feasibility

- one open-weight model;
- lightweight LoRA fine-tuning;
- original training versus isomorphism augmentation;
- unseen-ontology evaluation.

---

# 27. Go/No-Go Criteria

## 27.1 Continue to a full paper if

At least three of the following hold:

1. opaque or adversarial transformations create a large paired accuracy decrease on at least two models and two ontologies;
2. proof validity decreases more than final-answer accuracy;
3. a substantial `correct answer + invalid proof` category appears;
4. IRI and annotation channels produce distinct effects;
5. failure is systematically associated with OWL constructor or proof depth;
6. adversarial semantic decoys are substantially more damaging than token-matched pseudowords;
7. augmentation improves unseen-orbit robustness without a large loss on original data;
8. results remain significant after controlling for tokenization and context length.

## 27.2 Stop or pivot if

1. only opaque numeric identifiers reduce accuracy;
2. the entire effect is explained by tokenizer fragmentation;
3. proof metrics add no information beyond answer accuracy;
4. all models recover with one trivial instruction;
5. effects occur only on one ontology;
6. negatives are trivially solved by output bias;
7. augmentation merely memorizes renaming patterns and fails on unseen families;
8. the benchmark duplicates existing logical-obfuscation results without an OWL-specific finding.

---

# 28. Defense 1 — Isomorphism Augmentation

## 28.1 Training data

For each base training example, randomly sample a typed bijection per epoch.

Training conditions:

- original only;
- original plus opaque;
- original plus mixed transformations;
- mixed transformations plus consistency regularization.

## 28.2 Supervised objective

\[
\mathcal L_{sup}
=
-\log p_\theta(y\mid x).
\]

## 28.3 Consistency objective

For original \(x\) and transformed \(T(x)\):

\[
\mathcal L_{cons}
=
JS(
p_\theta(\cdot\mid x),
p_\theta(\cdot\mid T(x))
).
\]

Combined:

\[
\mathcal L =
\mathcal L_{sup}(x,y)
+
\mathcal L_{sup}(T(x),y)
+
\lambda\mathcal L_{cons}.
\]

For generative proof outputs, begin with answer-label consistency only. Proof-level consistency is more complex because multiple proofs can be valid.

## 28.4 Generalization protocol

Train on:

- opaque identifiers;
- one pseudoword family;
- selected training ontologies.

Test on:

- unseen opaque mappings;
- unseen pseudoword generator;
- random decoys;
- adversarial decoys;
- unseen ontologies;
- unseen domains.

## 28.5 Success metrics

The defense should improve:

- robust orbit accuracy;
- worst-condition accuracy;
- proof-validity orbit accuracy.

It should not reduce original accuracy by more than a predeclared tolerance, for example 2–3 percentage points.

---

# 29. Defense 2 — Optional Structural Encoder

This should be treated as a later extension, not required for the pilot.

## 29.1 Motivation

Text serialization makes entity names part of the token stream. A graph encoder can represent formal structure separately from lexical content.

## 29.2 Graph construction

Node types:

- named class;
- object property;
- data property;
- individual;
- existential constructor;
- conjunction constructor;
- axiom node.

Edge types encode argument roles:

- subclass source;
- subclass target;
- existential property;
- existential filler;
- conjunction operand;
- assertion class;
- assertion individual.

## 29.3 Equivariance goal

A graph neural network with shared parameters and no identity-specific embeddings should be equivariant to entity permutations.

For permutation matrix \(P\):

\[
G(PX,PAP^\top)=P\,G(X,A).
\]

The model can then combine:

\[
h_e =
g_e h^{lex}_e
+
(1-g_e)h^{struct}_e.
\]

## 29.4 Minimum baseline

Before building a complex architecture, compare:

1. text-only model;
2. text-only plus augmentation;
3. graph-only classifier;
4. dual-channel graph plus text.

Only pursue this direction if the pilot establishes a strong phenomenon.

---

# 30. Baselines

## 30.1 Prompting baselines

- direct classification;
- instruction to ignore names;
- few-shot logical examples;
- few-shot renamed examples;
- structured support selection.

## 30.2 Model baselines

- majority class;
- lexical classifier using only entity names;
- structural shallow classifier;
- symbolic reasoner upper reference;
- text LLM;
- augmented text LLM;
- optional graph model.

## 30.3 Diagnostic lexical baseline

Train a simple model using only:

- source entity label;
- target entity label;
- task type.

If this baseline performs well on original data and collapses under renaming, it quantifies lexical shortcut opportunity in the dataset.

## 30.4 Structural baseline

Use simple graph features:

- shortest hierarchy path;
- node degrees;
- ancestor overlap;
- relation type;
- proof-depth proxy.

This is not intended to replace the reasoner. It helps determine whether the task contains simple structural shortcuts.

---

# 31. Ablation Studies

Required ablations:

1. remove labels;
2. remove IRI local names;
3. remove definitions;
4. token-length matched renaming;
5. random versus adversarial decoy;
6. shallow versus deep proof;
7. positive versus non-entailed;
8. with versus without distractors;
9. direct answer versus structured support;
10. original fine-tuning versus augmentation;
11. augmentation without consistency loss;
12. consistency loss without mixed transformation families.

Optional:

- ontology syntax: Functional, Manchester-like verbalization, Turtle;
- axiom order;
- number of demonstrations;
- model size;
- context compression.

---

# 32. Experiment Configuration Example

```yaml
experiment:
  id: pilot_answer_audit_v1
  seed: 42
  output_dir: reports/pilot_answer_audit_v1

dataset:
  manifest: data/certified/pilot/manifest.jsonl
  task_types:
    - ATOMIC_SUBSUMPTION
    - INSTANCE_CHECKING
  labels:
    balance: true
  split:
    strategy: ontology_disjoint

conditions:
  - original
  - opaque_iri_original_labels
  - opaque_iri_no_labels
  - pseudoword_no_labels
  - adversarial_decoy_no_labels

models:
  - config: configs/models/local_small.yaml
  - config: configs/models/local_medium.yaml
  - config: configs/models/api_models.yaml

prompts:
  - direct
  - structured_proof

inference:
  temperature: 0.0
  max_new_tokens: 512
  batch_size: 16
  retries: 1

evaluation:
  answer_metrics: true
  orbit_metrics: true
  proof_metrics: true
  bootstrap_samples: 10000
  confidence_level: 0.95
```

---

# 33. Java CLI Specification

## 33.1 Inspect ontology

```bash
java -jar owl-certifier.jar inspect \
  --input data/raw/example.owl \
  --output data/normalized/example.stats.json
```

Outputs:

- profile;
- axiom counts;
- entity counts;
- annotations;
- consistency;
- unsatisfiable classes;
- imports;
- hash.

## 33.2 Generate queries

```bash
java -jar owl-certifier.jar generate-queries \
  --input data/normalized/example.owl \
  --reasoner ELK \
  --task atomic-subsumption \
  --positive-count 500 \
  --negative-count 500 \
  --output data/certified/example/queries.jsonl
```

## 33.3 Transform ontology

```bash
java -jar owl-certifier.jar transform \
  --input data/normalized/example.owl \
  --operator opaque \
  --seed 42 \
  --annotation-policy remove-lexical \
  --output data/certified/example/orbits/opaque42.owl \
  --mapping data/certified/example/orbits/opaque42.mapping.json
```

## 33.4 Validate orbit

```bash
java -jar owl-certifier.jar validate-orbit \
  --source data/normalized/example.owl \
  --target data/certified/example/orbits/opaque42.owl \
  --mapping data/certified/example/orbits/opaque42.mapping.json \
  --queries data/certified/example/queries.jsonl \
  --reasoner ELK \
  --report data/certified/example/orbits/opaque42.validation.json
```

## 33.5 Validate model support

```bash
java -jar owl-certifier.jar validate-support \
  --ontology data/certified/example/orbits/opaque42.owl \
  --predictions data/predictions/model_x.jsonl \
  --reasoner ELK \
  --output data/predictions/model_x.validated.jsonl
```

---

# 34. Python CLI Specification

## 34.1 Build prompts

```bash
python -m owl_equivariance.cli build-prompts \
  --config configs/experiments/pilot.yaml
```

## 34.2 Run inference

```bash
python -m owl_equivariance.cli infer \
  --config configs/experiments/pilot.yaml \
  --model local_medium
```

## 34.3 Parse and validate

```bash
python -m owl_equivariance.cli parse \
  --input data/predictions/raw/model.jsonl \
  --output data/predictions/parsed/model.jsonl
```

## 34.4 Evaluate

```bash
python -m owl_equivariance.cli evaluate \
  --config configs/experiments/pilot.yaml \
  --predictions data/predictions/validated/model.jsonl
```

## 34.5 Generate paper tables

```bash
python -m owl_equivariance.cli report \
  --experiment reports/pilot_answer_audit_v1 \
  --format latex
```

---

# 35. Testing Strategy

## 35.1 Java unit tests

- entity type preservation;
- bijection;
- inverse mapping;
- built-in vocabulary exclusion;
- constructor recursion;
- annotation conditions;
- serialization round trip;
- profile preservation where expected;
- query transformation;
- answer inverse mapping.

## 35.2 Java integration tests

- load ontology;
- classify with ELK;
- generate queries;
- transform;
- reclassify;
- compare labels;
- export validation report.

## 35.3 Python unit tests

- configuration validation;
- JSONL schema;
- grouping by orbit;
- answer parsing;
- invalid-output handling;
- metric calculations;
- bootstrap determinism;
- split leakage detection.

## 35.4 Golden tests

Maintain a small toy ontology with manually checked results.

Example:

```text
Professor ⊑ Employee
Employee ⊑ Person
Alice : Professor
```

Expected:

- `Professor ⊑ Person`: entailed;
- `Alice : Person`: entailed;
- `Person ⊑ Professor`: not entailed.

Run every transform and compare all expected outputs.

## 35.5 Property-based tests

Generate small random EL ontologies and random typed bijections.

Test:

\[
label(O,q)=label(\pi(O),\pi(q))
\]

for sampled supported queries.

---

# 36. Reproducibility

## 36.1 Required artifacts

Release:

- source ontology manifests;
- checksums;
- transformed ontologies;
- mappings;
- benchmark JSONL;
- query generator code;
- transformation proofs;
- prompts;
- raw model outputs where licenses permit;
- parsed outputs;
- evaluation scripts;
- environment lock files;
- hardware metadata;
- random seeds.

## 36.2 Dataset card

Document:

- source ontologies;
- licenses;
- selection criteria;
- exclusions;
- task distribution;
- transformation distribution;
- known limitations;
- ethical considerations;
- intended and unintended uses.

## 36.3 Deterministic regeneration

A single command should regenerate the pilot from frozen source files:

```bash
make reproduce-pilot
```

This should:

1. validate input hashes;
2. build Java service;
3. generate queries;
4. generate transformations;
5. validate orbits;
6. build prompts;
7. optionally run a small local baseline;
8. calculate metrics.

---

# 37. Compute Planning

## 37.1 Symbolic processing

ELK classification should be run once per normalized ontology and transformed ontology, then cached.

Cache keys should include:

- ontology hash;
- reasoner name;
- reasoner version;
- configuration;
- query hash.

## 37.2 LLM inference

Estimate tokens before running.

For each condition:

\[
TotalTokens =
N_{items}
\times
AvgInputTokens
\times
N_{models}
\times
N_{prompts}.
\]

Use context modules and fixed distractor budgets to keep conditions comparable.

## 37.3 Fine-tuning

Start with:

- one 7B–14B-class open model;
- LoRA or QLoRA;
- answer-label objective;
- small number of epochs;
- ontology-disjoint evaluation.

Do not begin with proof-generation fine-tuning. Establish answer robustness first.

---

# 38. Expected Tables

## Table 1 — Dataset statistics

Columns:

- ontology;
- domain;
- OWL profile;
- logical axioms;
- classes;
- properties;
- individuals;
- annotations;
- positive queries;
- negative queries;
- mean proof depth.

## Table 2 — Answer accuracy by condition

Rows: models  
Columns:

- original;
- opaque with labels;
- opaque without labels;
- pseudoword;
- random decoy;
- adversarial decoy;
- robust orbit accuracy.

## Table 3 — Lexical-channel decomposition

Rows: channel conditions  
Columns:

- accuracy;
- macro F1;
- flip rate;
- invalid output;
- average token count.

## Table 4 — Proof analysis

Columns:

- answer accuracy;
- support validity;
- correct-answer invalid-proof rate;
- proof-validity orbit accuracy;
- support equivariance.

## Table 5 — Failure by reasoning type

Rows:

- subclass transitivity;
- existential propagation;
- conjunction;
- property hierarchy;
- instance propagation.

Columns:

- original;
- opaque;
- adversarial;
- invariance gap.

## Table 6 — Defense results

Rows:

- base fine-tuning;
- opaque augmentation;
- mixed augmentation;
- mixed plus consistency.

Columns:

- original accuracy;
- unseen opaque;
- unseen pseudoword;
- adversarial;
- unseen ontology;
- robust orbit accuracy.

---

# 39. Expected Figures

1. **Accuracy by transformation condition**  
   Paired point or bar plot with confidence intervals.

2. **Orbit robustness distribution**  
   Percentage of items with 0, 1, 2, … failed variants.

3. **Accuracy versus proof depth**  
   Separate curves by transformation.

4. **Lexical-channel factorial plot**  
   IRI condition × label condition.

5. **Correct-answer versus proof-validity matrix**  
   Four-category stacked plot.

6. **Tokenization control plot**  
   Accuracy degradation versus token-count change.

7. **Defense trade-off**  
   Original accuracy versus robust orbit accuracy.

---

# 40. Risk Register

## Risk R1 — The effect is trivial

**Description:** All models fail on opaque names, reproducing known logical-obfuscation work.

**Mitigation:**

- emphasize lexical-channel decomposition;
- add proof validation;
- use adversarial versus token-matched controls;
- analyze real OWL constructors;
- stop early if no richer finding appears.

## Risk R2 — Proof extraction is unavailable

**Description:** The selected reasoner cannot export suitable proof graphs.

**Mitigation:**

- use justification support;
- validate model-selected axiom subsets;
- restrict proof-level analysis to a supported subset;
- treat full proof graph as an extension.

## Risk R3 — Negative queries are not query-complete

**Description:** A reduced context causes false interpretation of non-entailment.

**Mitigation:**

- use complete small ontologies;
- use verified query-preserving modules;
- verify each negative against the full ontology and supplied context;
- record the context-completeness method.

## Risk R4 — Tokenization explains the result

**Mitigation:**

- token-matched pseudowords;
- multiple identifier families;
- regression controls;
- report token statistics.

## Risk R5 — Adversarial mappings are subjective

**Mitigation:**

- define deterministic selection rules;
- use structural and lexical scores;
- release mappings;
- include random-decoy baseline.

## Risk R6 — LLM does not follow JSON

**Mitigation:**

- constrained decoding where available;
- simple schema;
- deterministic parser;
- report invalid-output rate;
- do not hide parser failures.

## Risk R7 — Dataset leakage through famous ontology facts

**Mitigation:**

- opaque and adversarial conditions;
- ontology-disjoint splits;
- use less famous ontologies;
- compare with annotations removed.

## Risk R8 — Augmentation is not novel

**Mitigation:**

- present it as an evaluated defense, not the main conceptual novelty;
- focus contribution on OWL-certified orbit benchmark and proof/channel analysis;
- pursue structural architecture only if needed.

---

# 41. Implementation Milestones

## Milestone M1 — Symbolic core

Deliverables:

- Java OWL loader;
- profile checker;
- ELK integration;
- query generator;
- toy ontology tests.

Exit criteria:

- 100% expected labels on golden fixtures.

## Milestone M2 — Certified renaming

Deliverables:

- opaque transform;
- pseudoword transform;
- inverse mapping;
- mapping manifest;
- preservation validation.

Exit criteria:

- no label disagreement across at least 10,000 generated orbit checks.

## Milestone M3 — Dataset builder

Deliverables:

- public ontology manifests;
- positive and matched negative queries;
- orbit JSONL;
- split generator;
- leakage checker.

Exit criteria:

- complete pilot dataset with reproducible hashes.

## Milestone M4 — LLM evaluation

Deliverables:

- prompt builder;
- model adapters;
- strict parser;
- answer and orbit metrics.

Exit criteria:

- end-to-end results for one model and all pilot conditions.

## Milestone M5 — Proof audit

Deliverables:

- support-output prompt;
- support validator;
- proof-level metrics.

Exit criteria:

- at least 200 verified positive items analyzed.

## Milestone M6 — Full pilot decision

Deliverables:

- statistical report;
- failure analysis;
- go/no-go decision.

## Milestone M7 — Defense

Deliverables:

- augmented training data;
- LoRA training;
- unseen-transformation evaluation.

Proceed only after M6 confirms a meaningful phenomenon.

---

# 42. Suggested Work Order for VS Code

1. Create the repository and Python environment.
2. Create the Java Maven project.
3. Implement the toy ontology fixtures.
4. Implement ontology inspection and profile checking.
5. Implement ELK entailment checking.
6. Implement query generation for atomic subsumption.
7. Implement typed opaque renaming.
8. Implement inverse mapping and orbit validation.
9. Define JSON schemas.
10. Build the Python dataset loader.
11. Build one direct classification prompt.
12. Run one local model.
13. Implement pair and orbit metrics.
14. Add real public ontologies.
15. Implement matched negatives.
16. Add annotation-channel conditions.
17. Add support selection and symbolic validation.
18. Run the pilot.
19. Make the go/no-go decision.
20. Only then implement augmentation training.

---

# 43. Minimal Viable Implementation

The smallest defensible prototype includes:

- one OWL 2 EL ontology;
- atomic subsumption only;
- 100 positive and 100 negative queries;
- original, opaque, and adversarial-decoy variants;
- one ELK validation pipeline;
- two LLMs;
- direct classification;
- paired accuracy and flip-rate analysis.

This prototype is not sufficient for publication, but it validates the core pipeline.

---

# 44. Full Paper Implementation Target

A full conference paper should include:

- at least 5–10 public ontologies;
- ontology-disjoint test split;
- several thousand base items;
- 4–6 transformation conditions;
- at least 3 model families;
- answer-level orbit evaluation;
- proof/support validation;
- lexical-channel factorial analysis;
- tokenization controls;
- one concrete augmentation defense;
- released code and certified dataset.

A journal extension should additionally include:

- more OWL constructs;
- full proof graphs;
- a structural or dual-channel architecture;
- broader model coverage;
- cross-syntax evaluation;
- adversarial transformation search;
- deeper formal analysis.

---

# 45. Paper Claim Checklist

Before writing the abstract, confirm that every intended claim has direct evidence.

## Allowed claims if supported

- typed renaming preserves the tested OWL entailments by construction;
- LLM answer accuracy changes under such renaming;
- proof validity changes independently from answer accuracy;
- lexical channels have separable effects;
- adversarial names are more harmful than token-matched neutral names;
- augmentation improves unseen-orbit robustness.

## Claims to avoid

- LLMs never reason;
- any accuracy drop proves no reasoning;
- the model’s private chain of thought is invalid;
- the transformation framework handles all possible OWL equivalences;
- symbolic reasoners are perfect;
- `NOT_ENTAILED` means false;
- one extracted justification is the unique proof;
- consistency training is a new general method.

---

# 46. Final Recommended Scope

The best first paper is:

> A certified benchmark and empirical audit of answer- and support-level equivariance under typed OWL signature isomorphisms, with a controlled decomposition of IRI and annotation channels and a modest augmentation defense.

The paper should be rejected internally before submission if its only conclusion is:

> Meaningful names help LLMs and opaque names hurt them.

It becomes scientifically worthwhile if it demonstrates at least one stronger result, such as:

- correct answers can conceal invalid transformed proofs;
- labels and IRI names have different causal roles;
- semantic decoys create failures that neutral pseudowords do not;
- specific OWL inference patterns are disproportionately name-dependent;
- a structure-aware or orbit-trained defense transfers to unseen ontologies.

---

# 47. References and Standards to Use During Implementation

Use the following as primary technical references:

1. **OWL 2 Web Ontology Language Direct Semantics, Second Edition**, W3C Recommendation.
2. **OWL 2 Web Ontology Language Structural Specification and Functional-Style Syntax**, W3C Recommendation.
3. **OWL 2 Web Ontology Language Profiles**, W3C Recommendation.
4. **OWLAPI** documentation and source repository.
5. **ELK Reasoner** documentation and publications.
6. **HermiT Reasoner** documentation for selected OWL 2 DL experiments.
7. **ROBOT** documentation for independent ontology workflow checks.
8. **OntoURL: A Benchmark for Evaluating Large Language Models on Symbolic Ontological Understanding, Reasoning and Learning**, arXiv:2505.11031.
9. **OBO Foundry** ontology registry and individual ontology license/version records.

Freeze exact software versions and ontology versions in the implementation manifest.

---

# 48. Immediate First Sprint

## Sprint objective

Produce a complete end-to-end result on a toy ontology and one public OWL 2 EL ontology.

## Tasks

### Symbolic layer

- [ ] Create Maven project.
- [ ] Add OWLAPI and ELK dependencies.
- [ ] Implement ontology statistics command.
- [ ] Implement atomic-subsumption query generator.
- [ ] Implement opaque typed bijection.
- [ ] Implement transformed-query generation.
- [ ] Verify source/transformed entailment equality.
- [ ] Export JSONL benchmark.

### Python layer

- [ ] Create `pyproject.toml`.
- [ ] Define Pydantic benchmark schema.
- [ ] Load JSONL.
- [ ] Build direct prompt.
- [ ] Add one Hugging Face model adapter.
- [ ] Parse JSON response.
- [ ] Compute original and transformed accuracy.
- [ ] Compute pair consistency and flip rate.
- [ ] Export one CSV result table.

### Quality

- [ ] Add golden ontology tests.
- [ ] Add mapping round-trip tests.
- [ ] Add split leakage test.
- [ ] Add deterministic seed test.
- [ ] Write a one-page pilot report.

## Sprint acceptance criteria

The sprint is complete when:

1. 200 base queries can be generated;
2. three transformed variants can be created;
3. every source/transformed label matches symbolically;
4. one LLM can be evaluated end to end;
5. the result table can be regenerated from one command.

---

# 49. Example Toy Ontology

```text
Prefix(:=<http://example.org/test#>)

Ontology(
 Declaration(Class(:Professor))
 Declaration(Class(:Employee))
 Declaration(Class(:Person))
 Declaration(Class(:University))
 Declaration(ObjectProperty(:worksFor))
 Declaration(NamedIndividual(:Alice))
 Declaration(NamedIndividual(:UTC))

 SubClassOf(:Professor :Employee)
 SubClassOf(:Employee :Person)
 ObjectPropertyDomain(:worksFor :Employee)
 ObjectPropertyRange(:worksFor :University)
 ClassAssertion(:Professor :Alice)
 ClassAssertion(:University :UTC)
 ObjectPropertyAssertion(:worksFor :Alice :UTC)
)
```

Example queries:

```text
SubClassOf(:Professor :Person)              → ENTAILED
ClassAssertion(:Person :Alice)              → ENTAILED
ClassAssertion(:University :Alice)          → NOT_ENTAILED
SubClassOf(:University :Employee)           → NOT_ENTAILED
```

Opaque mapping:

```text
Professor  → C_0001
Employee   → C_0002
Person     → C_0003
University → C_0004
worksFor   → OP_0001
Alice      → I_0001
UTC        → I_0002
```

All transformed query labels must remain identical.

---

# 50. Final Decision Rule

After the pilot, compute a concise evidence table.

| Criterion | Required evidence | Result |
|---|---|---|
| Nontrivial answer effect | Paired degradation beyond tokenization | Pending |
| Proof-specific effect | Proof validity adds new information | Pending |
| OWL-specific pattern | Effect varies by constructor/depth | Pending |
| Channel decomposition | IRI and labels show distinct roles | Pending |
| Defense value | Unseen-orbit robustness improves | Pending |
| Cross-ontology replication | At least two test ontologies | Pending |

Continue to a full paper only if at least four criteria are convincingly satisfied, including either **proof-specific effect** or **OWL-specific pattern**.

