package org.owleq.cli;

import org.owleq.io.OntologyIO;
import org.owleq.model.Json;
import org.owleq.profile.ProfileChecker;
import org.semanticweb.owlapi.model.OWLOntology;
import picocli.CommandLine;

import java.nio.file.Path;
import java.util.concurrent.Callable;

/** {@code inspect}: profile, size statistics, consistency and content hash (spec section 33.1). */
@CommandLine.Command(name = "inspect", description = "Report profile, statistics and consistency.")
public final class InspectCommand implements Callable<Integer> {

    @CommandLine.Option(names = "--input", required = true, description = "Ontology file.")
    Path input;

    @CommandLine.Option(names = "--output", description = "Statistics JSON output path.")
    Path output;

    @CommandLine.Option(names = "--root-only",
            description = "Ignore unresolvable imports instead of failing.")
    boolean rootOnly;

    @CommandLine.Option(names = "--no-reasoner", description = "Skip consistency checking.")
    boolean noReasoner;

    @Override
    public Integer call() throws Exception {
        OWLOntology o = rootOnly ? OntologyIO.loadRootOnly(input) : OntologyIO.load(input);
        ProfileChecker.Stats stats = ProfileChecker.inspect(o, !noReasoner);
        if (output != null) {
            Json.writePretty(output, stats);
        }
        System.out.printf("%s: %s, %d logical axioms, %d classes, consistent=%s%n",
                input.getFileName(), stats.profile, stats.logicalAxioms, stats.classes,
                noReasoner ? "unchecked" : stats.consistent);
        if (!"OWL2_EL".equals(stats.profile)) {
            System.out.println("WARNING: outside OWL 2 EL; ELK is not complete for this ontology.");
        }
        return 0;
    }
}
