package org.owleq.cli;

import org.owleq.io.OntologyIO;
import org.owleq.model.Json;
import org.owleq.transform.Condition;
import org.owleq.transform.SignatureIsomorphism;
import org.semanticweb.owlapi.model.OWLOntology;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Callable;

/** {@code transform}: write pi(O) and its mapping manifest (spec sections 12, 13, 33.3). */
@CommandLine.Command(name = "transform",
        description = "Apply a typed signature isomorphism and write the mapping manifest.")
public final class TransformCommand implements Callable<Integer> {

    @CommandLine.Option(names = "--input", required = true)
    Path input;

    @CommandLine.Option(names = "--condition", required = true,
            description = "Condition id from the lexical-channel matrix, e.g. C4.")
    String condition;

    @CommandLine.Option(names = "--output", required = true, description = "Transformed ontology.")
    Path output;

    @CommandLine.Option(names = "--mapping", required = true, description = "Mapping manifest JSON.")
    Path mapping;

    @CommandLine.Option(names = "--namespace-base", defaultValue = "urn:owleq:")
    String namespaceBase;

    @CommandLine.Option(names = "--root-only")
    boolean rootOnly;

    @Override
    public Integer call() throws Exception {
        OWLOntology source = rootOnly ? OntologyIO.loadRootOnly(input) : OntologyIO.load(input);
        Condition c = Condition.of(condition);
        SignatureIsomorphism iso = c.isomorphism(source, namespaceBase);
        OWLOntology target = iso.apply(source);
        OntologyIO.save(target, output);

        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("mapping_id", "map:" + input.getFileName() + ":" + c.id);
        manifest.put("condition", c.id);
        manifest.put("operator", iso.operatorId());
        manifest.put("seed", iso.seed());
        manifest.put("annotation_policy", iso.annotationPolicy().name());
        manifest.put("target_namespace", iso.targetNamespace());
        manifest.put("entity_count", iso.size());
        manifest.put("certificate_type", "BY_CONSTRUCTION");
        manifest.put("hashes", hashes(source, target));
        manifest.put("mapping", iso.byTypeStrings());
        Json.writePretty(mapping, manifest);

        System.out.printf("%s -> %s (%d entities renamed, policy %s)%n",
                input.getFileName(), output.getFileName(), iso.size(), iso.annotationPolicy());
        return 0;
    }

    private Map<String, String> hashes(OWLOntology source, OWLOntology target) {
        Map<String, String> h = new LinkedHashMap<>();
        h.put("source_ontology", OntologyIO.ontologyHash(source));
        h.put("target_ontology", OntologyIO.ontologyHash(target));
        return h;
    }
}
