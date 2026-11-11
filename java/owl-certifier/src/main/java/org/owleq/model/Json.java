package org.owleq.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;

/** Shared Jackson configuration. Java stays camelCase, JSON is snake_case as the spec writes it. */
public final class Json {

    private Json() {
    }

    public static final ObjectMapper MAPPER = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategy.SNAKE_CASE)
            .setSerializationInclusion(JsonInclude.Include.NON_NULL)
            // Key order is fixed so that regenerating the dataset yields byte-identical files
            // and therefore stable SHA-256s.
            .configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static final ObjectWriter PRETTY = MAPPER.writerWithDefaultPrettyPrinter();

    public static void writePretty(Path out, Object value) throws IOException {
        Files.createDirectories(out.toAbsolutePath().getParent());
        String s = PRETTY.writeValueAsString(value).replace("\r\n", "\n");
        Files.write(out, (s + "\n").getBytes(StandardCharsets.UTF_8));
    }

    /**
     * Atomically replace a mutable status/checkpoint JSON file.
     *
     * <p>Long ontology builds can be terminated between writes. Writing beside the destination
     * and then renaming prevents a monitor from mistaking a truncated JSON document for a valid
     * checkpoint. The fallback covers filesystems that do not advertise atomic moves.
     */
    public static void writePrettyAtomic(Path out, Object value) throws IOException {
        Path absolute = out.toAbsolutePath();
        Files.createDirectories(absolute.getParent());
        Path temporary = Files.createTempFile(absolute.getParent(),
                absolute.getFileName().toString() + ".", ".tmp");
        try {
            writePretty(temporary, value);
            try {
                Files.move(temporary, absolute, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(temporary, absolute, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    /** One JSON object per line, Unix endings, UTF-8. */
    public static void writeJsonl(Path out, List<?> values) throws IOException {
        Files.createDirectories(out.toAbsolutePath().getParent());
        try (BufferedWriter w = Files.newBufferedWriter(out, StandardCharsets.UTF_8)) {
            for (Object v : values) {
                w.write(MAPPER.writeValueAsString(v));
                w.write("\n");
            }
        }
    }

    /** Atomically publish a JSONL artifact after every row has serialized successfully. */
    public static void writeJsonlAtomic(Path out, List<?> values) throws IOException {
        Path absolute = out.toAbsolutePath();
        Files.createDirectories(absolute.getParent());
        Path temporary = Files.createTempFile(absolute.getParent(),
                absolute.getFileName().toString() + ".", ".tmp");
        try {
            writeJsonl(temporary, values);
            try {
                Files.move(temporary, absolute, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(temporary, absolute, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public static <T> List<T> readJsonl(Path in, Class<T> type) throws IOException {
        List<T> out = new java.util.ArrayList<>();
        try (BufferedReader r = Files.newBufferedReader(in, StandardCharsets.UTF_8)) {
            String line;
            while ((line = r.readLine()) != null) {
                if (!line.trim().isEmpty()) {
                    out.add(MAPPER.readValue(line, type));
                }
            }
        }
        return out;
    }

    public static <T> T read(Path in, Class<T> type) throws IOException {
        return MAPPER.readValue(in.toFile(), type);
    }

    public static ObjectNode obj() {
        return MAPPER.createObjectNode();
    }
}
