package org.owleq.io;

import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.formats.FunctionalSyntaxDocumentFormat;
import org.semanticweb.owlapi.model.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Ontology loading, deterministic serialization and content hashing.
 *
 * <p>The "normalized serialization" here is a reproducibility device only (spec section 9.4).
 * It is explicitly NOT a semantic canonical form: two logically equivalent ontologies may
 * serialize differently. It exists so that a rebuild of the pipeline produces byte-identical
 * artifacts and therefore identical SHA-256 hashes.
 */
public final class OntologyIO {

    private OntologyIO() {
    }

    /** Load with imports resolved by the manager's default policy. */
    public static OWLOntology load(Path file) throws OWLOntologyCreationException {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        // Missing imports must not silently produce a truncated ontology: fail loudly by
        // default, callers that want root-only must say so explicitly.
        return m.loadOntologyFromOntologyDocument(file.toFile());
    }

    /** Load ignoring unresolvable imports (import policy "root ontology only"). */
    public static OWLOntology loadRootOnly(Path file) throws OWLOntologyCreationException {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        OWLOntologyLoaderConfiguration cfg = new OWLOntologyLoaderConfiguration()
                .setMissingImportHandlingStrategy(MissingImportHandlingStrategy.SILENT)
                .setFollowRedirects(true);
        return m.loadOntologyFromOntologyDocument(
                new org.semanticweb.owlapi.io.FileDocumentSource(file.toFile()), cfg);
    }

    /**
     * Materialize the full import closure into a single flat ontology.
     * Preferred policy per spec section 9.1: one self-contained, checksummable artifact.
     */
    public static OWLOntology flatten(OWLOntology o, IRI newIri) throws OWLOntologyCreationException {
        OWLOntologyManager m = OWLManager.createOWLOntologyManager();
        Set<OWLAxiom> all = new HashSet<>();
        for (OWLOntology imported : o.getImportsClosure()) {
            all.addAll(imported.getAxioms());
        }
        return m.createOntology(all, newIri);
    }

    public static void save(OWLOntology o, Path out) throws OWLOntologyStorageException, IOException {
        Files.createDirectories(out.toAbsolutePath().getParent());
        FunctionalSyntaxDocumentFormat fmt = new FunctionalSyntaxDocumentFormat();
        try (OutputStream os = Files.newOutputStream(out)) {
            o.getOWLOntologyManager().saveOntology(o, fmt, os);
        }
    }

    /**
     * Deterministic serialization: axioms rendered one per line and sorted by their
     * functional-syntax string, with Unix line endings. Independent of OWLAPI's internal
     * hash-set iteration order, which is not stable across JVM runs.
     */
    public static String canonicalText(OWLOntology o) {
        List<String> lines = o.getAxioms().stream()
                .map(OntologyIO::renderAxiom)
                .sorted()
                .collect(Collectors.toList());
        StringBuilder sb = new StringBuilder();
        sb.append("Ontology(").append(o.getOntologyID().getOntologyIRI().isPresent()
                ? o.getOntologyID().getOntologyIRI().get().toString() : "anonymous").append(")\n");
        for (String l : lines) {
            sb.append(l).append('\n');
        }
        return sb.toString();
    }

    /**
     * Canonical text of the logical axioms only. Used by the annotation-isolation test
     * (spec section 14.4) to assert that annotation-channel interventions leave the
     * logical content untouched.
     */
    public static String canonicalLogicalText(OWLOntology o) {
        List<String> lines = o.getLogicalAxioms().stream()
                .map(OntologyIO::renderAxiom)
                .sorted()
                .collect(Collectors.toList());
        return String.join("\n", lines) + "\n";
    }

    /**
     * Render one axiom in functional syntax, stripped of its own annotations so that the
     * string is a stable key. Axiom annotations are compared separately where relevant.
     */
    public static String renderAxiom(OWLAxiom ax) {
        return ax.getAxiomWithoutAnnotations().toString().replaceAll("\\s+", " ").trim();
    }

    public static String sha256(String s) {
        return sha256(s.getBytes(StandardCharsets.UTF_8));
    }

    public static String sha256(byte[] bytes) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest(bytes);
            StringBuilder sb = new StringBuilder(d.length * 2);
            for (byte b : d) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static String sha256File(Path p) throws IOException {
        return sha256(Files.readAllBytes(p));
    }

    /** Content hash of an ontology, computed from its deterministic serialization. */
    public static String ontologyHash(OWLOntology o) {
        return sha256(canonicalText(o));
    }
}
