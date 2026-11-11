package org.owleq.cli;

import picocli.CommandLine;

/** Entry point for the Java symbolic layer (spec section 33). */
@CommandLine.Command(
        name = "owl-certifier",
        mixinStandardHelpOptions = true,
        version = "owl-certifier 0.2.0",
        description = "Certified OWL signature-isomorphism benchmark generation and validation.",
        subcommands = {
                InspectCommand.class,
                BuildDatasetCommand.class,
                TransformCommand.class,
                ValidateOrbitCommand.class,
                ValidateSupportCommand.class
        })
public final class Main implements Runnable {

    @Override
    public void run() {
        new CommandLine(this).usage(System.out);
    }

    public static void main(String[] args) {
        int code = new CommandLine(new Main()).execute(args);
        System.exit(code);
    }
}
