package org.owleq.transform;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Vocabulary for the O3 random-decoy operator.
 *
 * <p>Deliberately concrete, high-frequency, everyday words drawn from domains no research
 * ontology is about (furniture, weather, transport, kitchenware). The aim is a name that is
 * unmistakably a real word yet carries no plausible relation to any biomedical or engineering
 * concept, so O3 isolates "is a word" from "is the right word".
 */
public final class WordLists {

    private WordLists() {
    }

    public static final List<String> NOUNS = Collections.unmodifiableList(Arrays.asList(
            "River", "Bicycle", "Kettle", "Lantern", "Harbor", "Meadow", "Curtain", "Pebble",
            "Anchor", "Basket", "Candle", "Drawer", "Envelope", "Ferry", "Glacier", "Hammer",
            "Island", "Jacket", "Kitchen", "Ladder", "Mirror", "Needle", "Orchard", "Pillow",
            "Quarry", "Ribbon", "Saddle", "Teapot", "Umbrella", "Village", "Wagon", "Yarn",
            "Balcony", "Chimney", "Doorway", "Engine", "Fountain", "Garden", "Hillside", "Ivory",
            "Jigsaw", "Kayak", "Lagoon", "Marble", "Notebook", "Ocean", "Pantry", "Quilt",
            "Rooftop", "Sandal", "Thunder", "Utensil", "Valley", "Whistle", "Zipper", "Almond",
            "Bucket", "Compass", "Dolphin", "Eagle", "Feather", "Granite", "Hedge", "Igloo",
            "Kernel", "Lemon", "Mountain", "Nectar", "Orbit", "Parcel", "Quiver", "Raft",
            "Shovel", "Trumpet", "Vessel", "Willow", "Acorn", "Bridge", "Cabin", "Dune",
            "Ember", "Fossil", "Gallery", "Helmet", "Inkwell", "Jetty", "Keyboard", "Lighthouse",
            "Mailbox", "Nutmeg", "Otter", "Prairie", "Quartz", "Ranch", "Sailboat", "Tunnel",
            "Vineyard", "Wardrobe", "Yacht", "Zebra", "Awning", "Beacon", "Canyon", "Driftwood",
            "Elevator", "Fireplace", "Gondola", "Hangar", "Icicle", "Junction", "Kiosk", "Lobby",
            "Mantel", "Nursery", "Overpass", "Piano", "Quay", "Reservoir", "Silo", "Terrace",
            "Upholstery", "Veranda", "Windmill", "Yardstick", "Antler", "Bramble", "Cauldron",
            "Daffodil", "Eaves", "Furnace", "Gravel", "Haystack", "Ingot", "Juniper", "Kelp",
            "Lattice", "Mosaic", "Nomad", "Obelisk", "Plateau", "Quicksand", "Ridge", "Satchel",
            "Trellis", "Undertow", "Vault", "Wharf", "Xylophone", "Yeast", "Zenith", "Alcove",
            "Bellows", "Cobblestone", "Dredge", "Estuary", "Foghorn", "Gable", "Hearth", "Inlet"
    ));

    public static final List<String> VERBS = Collections.unmodifiableList(Arrays.asList(
            "surrounds", "carries", "polishes", "sketches", "borrows", "whistles", "anchors",
            "bakes", "climbs", "drifts", "engraves", "folds", "gathers", "hovers", "irrigates",
            "juggles", "knits", "launches", "moors", "navigates", "orbits", "paddles", "quilts",
            "rows", "sails", "trims", "unpacks", "varnishes", "wanders", "yields", "assembles",
            "brushes", "carves", "drapes", "embroiders", "fastens", "glazes", "hammers", "inlays",
            "jams", "kindles", "laminates", "mends", "notches", "oils", "plasters", "quarries",
            "rinses", "sands", "tiles", "unrolls", "veneers", "weaves", "zips", "braids",
            "chisels", "dusts", "etches", "files", "grinds", "hoists", "insulates", "joins",
            "kneads", "levels", "mounts", "nails", "paints", "pumps", "rakes", "scrubs",
            "tightens", "unbolts", "vents", "welds", "arches", "bridges", "coils", "dams",
            "encircles", "flanks", "girdles", "hedges", "inserts", "juts", "laces", "moulds",
            "nests", "overlaps", "props", "rims", "spans", "tethers", "underpins", "wraps",
            "abuts", "buttresses", "clasps", "docks", "embeds", "fringes", "grips", "hinges",
            "interlocks", "jackets", "latches", "meshes", "nudges", "overhangs", "pins", "rests",
            "straddles", "tops", "undercuts", "wedges", "yokes", "bands", "crowns", "drapes2"
    ));
}
