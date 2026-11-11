package org.owleq.transform;

import org.semanticweb.owlapi.model.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * A fixed-point-free permutation of entities that pairs each entity with a structurally
 * confusable one.
 *
 * <p>Shared by the O4 adversarial-decoy operator (which steals the partner's local name) and the
 * misleading-label annotation policy (which steals the partner's {@code rdfs:label}), so that both
 * interventions point the lexical channel at the same wrong concept.
 *
 * <p>Confusability is approximated by asserted sibling structure: entities under a common parent
 * are the ones whose names a reader would most plausibly swap. Within each sibling group the
 * permutation is a cyclic shift, which is fixed-point-free for any group of size at least two.
 */
public final class Derangement {

    private Derangement() {
    }

    public static Map<OWLEntity, OWLEntity> siblingShift(List<OWLEntity> entities,
                                                         OWLOntology source) {
        return siblingShift(entities, source, Naming.displayNames(source));
    }

    public static Map<OWLEntity, OWLEntity> siblingShift(List<OWLEntity> entities,
                                                         OWLOntology source,
                                                         Map<OWLEntity, String> display) {
        Map<String, List<OWLEntity>> byParent = new TreeMap<>();
        for (OWLEntity e : entities) {
            byParent.computeIfAbsent(parentKey(e, source, display), k -> new ArrayList<>()).add(e);
        }

        Map<OWLEntity, OWLEntity> out = new LinkedHashMap<>();
        List<OWLEntity> leftovers = new ArrayList<>();
        List<List<OWLEntity>> groups = new ArrayList<>(byParent.values());
        for (List<OWLEntity> g : groups) {
            g.sort(Comparator.comparing(x -> x.getIRI().toString()));
        }

        for (List<OWLEntity> g : groups) {
            if (g.size() < 2) {
                leftovers.addAll(g);
                continue;
            }
            for (int i = 0; i < g.size(); i++) {
                out.put(g.get(i), g.get((i + 1) % g.size()));
            }
        }

        if (leftovers.size() == 1) {
            // One orphan cannot be deranged alone: splice it into an existing cycle by stealing
            // that cycle's first element as its partner, and giving the orphan away in return.
            for (List<OWLEntity> g : groups) {
                if (g.size() >= 2) {
                    OWLEntity orphan = leftovers.get(0);
                    OWLEntity head = g.get(0);
                    OWLEntity tail = g.get(g.size() - 1);
                    out.put(orphan, head);
                    out.put(tail, orphan);
                    leftovers.clear();
                    break;
                }
            }
        }
        if (leftovers.size() >= 2) {
            leftovers.sort(Comparator.comparing(e -> e.getIRI().toString()));
            for (int i = 0; i < leftovers.size(); i++) {
                out.put(leftovers.get(i), leftovers.get((i + 1) % leftovers.size()));
            }
        }
        // A lone orphan with no cycle anywhere in the ontology maps to itself; unavoidable and
        // harmless at that size, but recorded honestly rather than faked.
        for (OWLEntity e : entities) {
            out.putIfAbsent(e, e);
        }
        return out;
    }

    private static String parentKey(OWLEntity e, OWLOntology source,
                                    Map<OWLEntity, String> display) {
        if (e instanceof OWLClass) {
            List<String> parents = source.getSubClassAxiomsForSubClass((OWLClass) e).stream()
                    .map(OWLSubClassOfAxiom::getSuperClass)
                    .filter(c -> !c.isAnonymous())
                    .map(c -> c.asOWLClass().getIRI().toString())
                    .sorted()
                    .collect(Collectors.toList());
            if (!parents.isEmpty()) {
                return "C:" + parents.get(0);
            }
        } else if (e instanceof OWLNamedIndividual) {
            List<String> types = source.getClassAssertionAxioms((OWLNamedIndividual) e).stream()
                    .map(OWLClassAssertionAxiom::getClassExpression)
                    .filter(c -> !c.isAnonymous())
                    .map(c -> c.asOWLClass().getIRI().toString())
                    .sorted()
                    .collect(Collectors.toList());
            if (!types.isEmpty()) {
                return "I:" + types.get(0);
            }
        } else if (e instanceof OWLObjectProperty) {
            List<String> parents = source.getObjectSubPropertyAxiomsForSubProperty(
                            (OWLObjectPropertyExpression) e).stream()
                    .map(OWLSubObjectPropertyOfAxiom::getSuperProperty)
                    .filter(p -> !p.isAnonymous())
                    .map(p -> p.asOWLObjectProperty().getIRI().toString())
                    .sorted()
                    .collect(Collectors.toList());
            if (!parents.isEmpty()) {
                return "OP:" + parents.get(0);
            }
        }
        // No structural neighbour: bucket by the display name's prefix so similarly-*named*
        // entities compete for each other's identities. Bucketing on the IRI local name
        // would put every OBO class in one bucket, since they all begin "CL_".
        String ln = display.getOrDefault(e, Naming.localName(e)).toLowerCase(Locale.ROOT);
        return "L:" + ln.substring(0, Math.min(2, ln.length()));
    }
}
