"""Declarative content for Level 1 of The Archivist Trials."""

ROOMS = {
    "hub": {
        "name": "Hall of Pending Things",
        "background": "hall_of_pending_things_clean_v1.png",
        "objective": "Follow the Archive's lessons: Memory, Mercy, then Order",
    },
    "memory": {
        "name": "Hall of Memory",
        "background": "hall_of_memory_clean_v1.png",
        "objective": "Recover and restore the three temporal hourglasses",
    },
    "mercy": {
        "name": "Hall of Mercy",
        "background": "hall_of_mercy_v2.png",
        "objective": "Hear three appeals, expose their hidden costs, and face what the rulings summon",
    },
    "order": {
        "name": "Lower Registry",
        "background": "lower_registry_clean_v1.png",
        "objective": "Recover three docket shards and open the Registry chest",
    },
    "vault": {
        "name": "Vault of the Unclosed",
        "background": "vault_of_the_unclosed_v1.png",
        "objective": "Defeat The Pending and its returning retinue",
    },
}

TRIAL_IDS = ("memory", "mercy", "order")
HALL_SEQUENCE = TRIAL_IDS
# A Hall opens only after the previous Hall's lesson has been completed and
# understood at its matching main-hall seal.
HALL_PREREQUISITES = {
    "memory": None,
    "mercy": "memory",
    "order": "mercy",
}
VALID_ROOM_IDS = tuple(ROOMS)

NARRATIVE_FLAG_IDS = (
    "opening_seen",
    "lantern_recognition_seen",
    "movement_tutorial_started",
    "movement_tutorial_complete",
    "interaction_tutorial_complete",
    "onboarding_complete",
    "memory_threshold_seen",
    "mercy_threshold_seen",
    "order_threshold_seen",
    "hub_interlude_1_seen",
    "hub_interlude_2_seen",
    "hub_interlude_3_seen",
    "memory_vey_whisper_heard",
    "mercy_testimonies_read",
    "order_master_docket_seen",
    "key_inscription_seen",
    "pre_vault_conversation_seen",
    "vault_identity_phrase_heard",
    "first_vault_defeat_memory_check_seen",
    "pending_human_names_seen",
    "level_one_epilogue_seen",
    "orin_post_credit_seen",
)

RESPONSE_TENDENCY_IDS = ("practical", "vulnerable", "humorous")
ROOM_SAFE_SPAWNS = {
    "hub": (480.0, 525.0),
    "memory": (875.0, 320.0),
    "mercy": (85.0, 320.0),
    "order": (480.0, 185.0),
    "vault": (245.0, 360.0),
}

ROOM_NAVIGATION = {
    "hub": {
        "walk_areas": (
            (64, 190, 832, 355),
            (0, 220, 112, 96),
            (848, 220, 112, 96),
            (405, 520, 150, 120),
        ),
        "blockers": (
            {"shape": "ellipse", "center": (196, 230), "radii": (70, 55)},
            {"shape": "ellipse", "center": (770, 280), "radii": (72, 62)},
            {"shape": "ellipse", "center": (770, 480), "radii": (72, 62)},
            {"shape": "polygon", "points": ((65, 438), (252, 438), (276, 503), (65, 503))},
            {"shape": "ellipse", "center": (175, 403), "radii": (25, 15)},
        ),
    },
    "memory": {
        "walk_areas": (
            (64, 180, 832, 365),
            (848, 252, 112, 118),
        ),
        "blockers": (
            {"id": "past_archive_effect", "shape": "ellipse", "center": (194, 326), "radii": (84, 77)},
            {"id": "present_archive_effect", "shape": "ellipse", "center": (480, 326), "radii": (90, 80)},
            {"id": "future_archive_effect", "shape": "ellipse", "center": (742, 326), "radii": (86, 79)},
            {"id": "candle_compartment", "shape": "ellipse", "center": (302, 212), "radii": (28, 20)},
            {"id": "north_lockbox", "shape": "ellipse", "center": (615, 209), "radii": (29, 18)},
            {"id": "wall_astrolabe", "shape": "ellipse", "center": (80, 373), "radii": (21, 28)},
            {"id": "gear_debris", "shape": "ellipse", "center": (635, 492), "radii": (26, 18)},
            {
                "id": "west_archive_bank",
                "shape": "polygon",
                "points": ((35, 108), (275, 108), (275, 197), (35, 197)),
            },
            {
                "id": "east_book_bank",
                "shape": "polygon",
                "points": ((655, 105), (899, 105), (899, 198), (655, 198)),
            },
            {"shape": "polygon", "points": ((65, 480), (255, 480), (278, 542), (65, 542))},
            {"shape": "polygon", "points": ((730, 480), (887, 480), (896, 542), (720, 542))},
        ),
    },
    "mercy": {
        "walk_areas": (
            (64, 180, 832, 370),
            (0, 260, 112, 112),
        ),
        "blockers": (
            {"shape": "polygon", "points": ((75, 214), (184, 214), (192, 255), (68, 255))},
            {"shape": "polygon", "points": ((770, 215), (892, 215), (896, 258), (760, 258))},
            {"shape": "polygon", "points": ((68, 492), (212, 492), (225, 540), (64, 540))},
            {"shape": "polygon", "points": ((750, 492), (892, 492), (896, 540), (738, 540))},
            {"id": "mercy_pardon", "shape": "ellipse", "center": (250, 300), "radii": (52, 40)},
            {"id": "mercy_diversion", "shape": "ellipse", "center": (480, 255), "radii": (55, 42)},
            {"id": "mercy_cure", "shape": "ellipse", "center": (710, 300), "radii": (52, 40)},
        ),
    },
    "order": {
        "walk_areas": (
            (64, 180, 832, 370),
            (405, 0, 150, 230),
        ),
        "blockers": (
            {"shape": "ellipse", "center": (180, 310), "radii": (72, 62)},
            {"shape": "ellipse", "center": (780, 310), "radii": (72, 62)},
            {"shape": "ellipse", "center": (480, 470), "radii": (66, 56)},
            {
                "id": "mimic_chest",
                "shape": "polygon",
                "points": ((425, 265), (535, 265), (548, 320), (412, 320)),
            },
            {"shape": "polygon", "points": ((65, 474), (275, 474), (292, 542), (65, 542))},
            {"shape": "polygon", "points": ((718, 474), (891, 474), (896, 542), (700, 542))},
        ),
    },
    "vault": {
        "walk_areas": ((64, 190, 832, 360),),
        "blockers": (
            {"shape": "ellipse", "center": (700, 365), "radii": (115, 85)},
            {"shape": "ellipse", "center": (620, 265), "radii": (38, 28)},
            {"shape": "ellipse", "center": (700, 500), "radii": (38, 28)},
            {"shape": "ellipse", "center": (835, 500), "radii": (38, 28)},
        ),
    },
}

ROOM_ENVIRONMENT_SPRITES = {
    "hub": (
        {
            "id": "hub_crystal",
            "sheet": "environment/hub/crystal_idle_runtime_sheet.png",
            "position": (196, 220),
            "rect": (96, 82, 200, 262),
            "phase": 0,
        },
        {
            "id": "hub_lunar",
            "sheet": "environment/hub/lunar_v2_idle_locked_runtime_sheet.png",
            "position": (770, 286),
            "rect": (670, 113, 200, 262),
            "phase": 7,
        },
        {
            "id": "hub_armillary",
            "sheet": "environment/hub/armillary_idle_runtime_sheet.png",
            "position": (770, 470),
            "rect": (670, 323, 200, 262),
            "phase": 14,
        },
    ),
    "memory": (
        {
            "id": "past",
            "sheet": "environment/memory/past_idle_runtime_sheet.png",
            "position": (194, 315),
            "rect": (94, 163, 200, 262),
            "phase": 0,
        },
        {
            "id": "present",
            "sheet": "environment/memory/present_idle_runtime_sheet.png",
            "position": (480, 315),
            "rect": (380, 163, 200, 262),
            "phase": 9,
        },
        {
            "id": "future",
            "sheet": "environment/memory/future_v3_idle_runtime_sheet_locked.png",
            "position": (742, 315),
            "rect": (642, 163, 200, 262),
            "phase": 18,
        },
    ),
    "mercy": (),
    "order": (
        {
            "id": "order_west",
            "sheet": "environment/order/identity_station_runtime_sheet_v1.png",
            "position": (180, 300),
            "rect": (108, 176, 144, 212),
            "phase": 4,
            "shard_id": "west",
        },
        {
            "id": "order_east",
            "sheet": "environment/order/sequence_station_runtime_sheet_v1.png",
            "position": (780, 300),
            "rect": (704, 176, 152, 212),
            "phase": 15,
            "shard_id": "east",
        },
        {
            "id": "order_south",
            "sheet": "environment/order/authority_station_runtime_sheet_v1.png",
            "position": (480, 470),
            "rect": (415, 400, 130, 150),
            "phase": 24,
            "shard_id": "south",
        },
        {
            "id": "mimic_chest",
            "sheet": "environment/order/reward_chest_runtime_sheet_v1.png",
            "position": (480, 300),
            "rect": (385, 228, 190, 150),
            "phase": 11,
            "state": "dormant_mimic",
        },
    ),
    "vault": (),
}

ROOM_EXITS = {
    "hub": (
        {"trigger": (0, 235, 24, 66), "room": "memory", "spawn": (875, 320), "facing": "left"},
        {"trigger": (936, 235, 24, 66), "room": "mercy", "spawn": (85, 320), "facing": "right"},
        {"trigger": (440, 612, 80, 28), "room": "order", "spawn": (480, 185), "facing": "down"},
    ),
    "memory": (
        {"trigger": (936, 275, 24, 78), "room": "hub", "spawn": (85, 270), "facing": "right"},
    ),
    "mercy": (
        {"trigger": (0, 280, 24, 72), "room": "hub", "spawn": (875, 270), "facing": "left"},
    ),
    "order": (
        {"trigger": (440, 0, 80, 28), "room": "hub", "spawn": (480, 520), "facing": "up"},
    ),
    "vault": (),
}

MEMORY_PLINTHS = (
    {"id": "past", "position": (194, 315), "activation_rect": (166, 414, 56, 24), "line": "Dust slips upward. A page unburns itself, then waits."},
    {"id": "present", "position": (480, 315), "activation_rect": (452, 414, 56, 24), "line": "Fresh ink gathers on the open page. It spells your name and blots it out."},
    {"id": "future", "position": (742, 315), "activation_rect": (714, 414, 56, 24), "line": "The clock has no hands. Something inside it is still counting."},
)
MEMORY_SEQUENCE = tuple(plinth["id"] for plinth in MEMORY_PLINTHS)

MEMORY_ARCHIVE_RULES = {
    "past": {
        "seconds": 60,
        "movement": "reversed",
        "brief": "The room lurches backward. Your body remembers walking; history pulls the floor the other way.",
        "guidance": "The oldest hourglass has awakened somewhere in the room. Bring it back before the last grain rises.",
    },
    "present": {
        "seconds": 25,
        "movement": "accelerated",
        "brief": "The living hour strikes. Every candle flares, and for twenty-five seconds the room refuses to wait for you.",
        "guidance": "Find the living hourglass and return it while this moment still belongs to you.",
    },
    "future": {
        "seconds": 120,
        "movement": "slowed",
        "brief": "The next step grows heavy. Around you, every possible self chooses a different ending.",
        "guidance": "Find the unwritten hourglass. You have two minutes before this future decides it never contained you.",
    },
}

# Embedded entries promote furniture already authored into the room background.
# Other entries use the generated 4x2 transparent prop sheet.
MEMORY_SEARCH_OBJECTS = (
    {
        "id": "west_archive_bank",
        "label": "West Archive Cabinets",
        "position": (158, 207),
        "rect": (28, 98, 255, 132),
        "embedded": True,
        # Overlap the collision edge deliberately: the player's 13 px foot
        # radius stops at y=210, so a band beginning below that is unreachable.
        "interaction_rect": (70, 198, 200, 72),
        "lore": {
            "past": "A drawer opens on seven royal pardons, folded beneath a tax ledger. The signatures have been cut away.",
            "present": "A brass key lies behind the index cards. When you reach for it, a beetle drags it deeper into the cabinet.",
            "future": "Every drawer briefly bears your name. All but one are stamped CLOSED. Something scratches inside the last.",
        },
    },
    {
        "id": "north_votive_altar",
        "label": "Northern Votive Alcove",
        "position": (480, 205),
        "rect": (360, 62, 250, 123),
        "embedded": True,
        "interaction_rect": (422, 180, 116, 34),
        "lore": {
            "past": "The oldest candle is sealed around a note: One more day. No name. No explanation. The wax is still warm.",
            "present": "The flames bend toward a prayer scratched into the stone: NOT YET.",
            "future": "The alcove fills with candles bearing unfamiliar names. One has already been lit for you.",
        },
    },
    {
        "id": "east_book_bank",
        "label": "East Archive Cabinets",
        "position": (805, 210),
        "rect": (648, 90, 258, 158),
        "embedded": True,
        "interaction_rect": (675, 198, 210, 72),
        "lore": {
            "past": "Seven borrowing slips remain inside the same unfinished book. The final reader wrote: Do not return this to Final Disposition.",
            "present": "Three books offer three versions of the same decree. Each correction is in Mara's handwriting.",
            "future": "Blank volumes crowd the shelf. Their titles describe disasters that have not happened. The thinnest is called AVOIDABLE.",
        },
    },
    {
        "id": "west_scriptorium_desk",
        "label": "West Scriptorium Desk",
        "position": (286, 470),
        "rect": (46, 424, 280, 170),
        "embedded": True,
        "interaction_rect": (95, 430, 160, 48),
        "lore": {
            "past": "Ink seeps through the wood: EAST WING EVACUATED. LABELS CHANGED. THEY FOLLOWED THE WRONG MAP.",
            "present": "Every drawer is carefully labelled. Every label is wrong. A fresh fingerprint darkens the ink.",
            "future": "A future inventory contains one entry: PERSONAL EFFECTS, OWNER UNCONFIRMED. Your lantern is sketched beside it.",
        },
    },
    {
        "id": "east_scriptorium_desk",
        "label": "East Scriptorium Desk",
        "position": (688, 470),
        "rect": (684, 424, 270, 170),
        "embedded": True,
        "interaction_rect": (735, 430, 150, 48),
        "lore": {
            "past": "The evacuation ledger repeats the same note down an entire page: FOUND. RETURNED. MISSING AGAIN.",
            "present": "The current inventory is complete except for one unnumbered hourglass. Its location field is blank.",
            "future": "Fresh ink enters your lantern under ITEMS LEFT BEHIND. You pull it closer. The ink keeps writing.",
        },
    },
    {
        "id": "candle_compartment",
        "label": "Wax-Sealed Compartment",
        "position": (302, 205),
        "rect": (266, 171, 72, 72),
        "atlas_index": 1,
        "interaction_rect": (278, 235, 48, 32),
        "interaction_radius": 62,
        "lore": {
            "past": "Inside is a letter burned before it was opened. Only the farewell survived.",
            "present": "Warm wax. Cold brass. An empty velvet hollow shaped like an hourglass.",
            "future": "A city map flickers inside. Every road has been redrawn to end at this room.",
        },
    },
    {
        "id": "north_lockbox",
        "label": "Chronology Lockbox",
        "position": (615, 205),
        "rect": (578, 172, 74, 66),
        "atlas_index": 2,
        "interaction_rect": (591, 232, 48, 32),
        "interaction_radius": 62,
        "lore": {
            "past": "Twelve ownership marks circle the lock. A thirteenth name was carved over the first.",
            "present": "The lockbox contains a second lockbox and a note in cramped handwriting: I panicked.",
            "future": "A key waits inside. It rusts to powder a finger's width from your hand.",
        },
    },
    {
        "id": "wall_astrolabe",
        "label": "Wall Astrolabe",
        "position": (80, 363),
        "rect": (48, 326, 64, 74),
        "atlas_index": 4,
        "interaction_rect": (68, 409, 48, 38),
        "interaction_radius": 72,
        "lore": {
            "past": "The brass rings return to the night three registered stars disappeared. Someone has scratched ERROR beside each name.",
            "present": "The astrolabe predicts an eclipse. A meeting notice has been pinned directly over it.",
            "future": "The rings chart an open eye. Its pupil points toward the Vault instead of the sky.",
        },
    },
    {
        "id": "floor_parchments",
        "label": "Loose Parchments",
        "position": (345, 490),
        "rect": (307, 459, 76, 62),
        "atlas_index": 5,
        "interaction_rect": (316, 454, 58, 52),
        "interaction_radius": 65,
        "lore": {
            "past": "Candle receipts from the plague winter. The final column records names instead of amounts.",
            "present": "A note ends halfway through one warning: If the bell rings thirteen times, do not answer the -" ,
            "future": "The page is in your handwriting. It describes a choice you have not made. The consequence has been torn away.",
        },
    },
    {
        "id": "gear_debris",
        "label": "Gear Debris",
        "position": (635, 492),
        "rect": (596, 457, 78, 70),
        "atlas_index": 6,
        "interaction_rect": (608, 423, 54, 36),
        "interaction_radius": 70,
        "lore": {
            "past": "A gear is engraved E. VEY. Its teeth are scorched on only one side.",
            "present": "One loose gear turns when your lantern passes over it. The others answer from beneath the floor.",
            "future": "The debris assembles into a small clock. It counts down from three, then breaks before reaching zero.",
        },
    },
)

ORDER_SHARDS = {
    "west": (180, 300),
    "east": (780, 300),
    "south": (480, 470),
}

ORDER_INVESTIGATION_IDS = ("identity", "sequence", "authority")
ORDER_STATIONS = {
    "identity": {
        "shard_id": "west", "position": ORDER_SHARDS["west"],
        "activation_rect": (252, 286, 56, 28), "title": "Index of Identity",
    },
    "sequence": {
        "shard_id": "east", "position": ORDER_SHARDS["east"],
        "activation_rect": (652, 286, 56, 28), "title": "Ledger of Sequence",
    },
    "authority": {
        "shard_id": "south", "position": ORDER_SHARDS["south"],
        "activation_rect": (452, 376, 56, 28), "title": "Seal of Authority",
    },
}

# Every investigation uncovers a different facet of Docket VII-13. Variants
# change presentation and clue order without changing the history underneath.
ORDER_INVESTIGATIONS = {
    "identity": (
        {
            "brief": "Someone cut the keeper's name from the duty roll. The other staff records survived just well enough to argue with one another.",
            "clues": (
                "Vey signed the south dial's calibration slip; the matching chamber key was never checked back in.",
                "Marr's copy ledger records the fault, but places her at the east desk when the chamber was sealed.",
                "Vale authorized the late inspection, then signed the transfer from the Chancellor's gallery.",
            ),
            "clue_labels": ("CALIBRATION", "COPY LEDGER", "TRANSFER"),
            "options": (
                ("elian_vey", "Elian Vey", "Keeper of the Palimpsest Chronometer"),
                ("lysa_marr", "Lysa Marr", "Deputy registrar and copyist"),
                ("orren_vale", "Orren Vale", "Chancellor of Final Disposition"),
            ),
            "answer": "elian_vey",
        },
        {
            "brief": "TRANSFERRED was stamped across the keeper's line while the ink was still wet.",
            "clues": (
                "Vey's maintenance hand matches the surviving strokes beneath the stamp, including an odd open-tailed Y.",
                "Vale appears on the same sheet beneath AUTHORIZED; his seal never touches the keeper's line.",
                "Rook's bell ledger puts him in the western stacks before and after the transfer was signed.",
            ),
            "clue_labels": ("HANDWRITING", "AUTHORIZATION", "BELL LEDGER"),
            "options": (
                ("orren_vale", "Orren Vale", "Chancellor of Final Disposition"),
                ("elian_vey", "Elian Vey", "Keeper of the Palimpsest Chronometer"),
                ("tomas_rook", "Tomas Rook", "Bellwright of the western stacks"),
            ),
            "answer": "elian_vey",
        },
        {
            "brief": "One staff portrait has been scraped clean. The objects around it were left untouched.",
            "clues": (
                "Vey's inventory lists a brass hourglass key with a chipped blue stone; that key still hangs from the missing coat.",
                "Marr's portrait remains beside the copy desk, where her note asks why the south dial skipped thirteen.",
                "Rook's portrait still carries the iron bell key used in the western stacks.",
            ),
            "clue_labels": ("MISSING COAT", "COPY DESK", "BELL KEY"),
            "options": (
                ("tomas_rook", "Tomas Rook", "Bellwright of the western stacks"),
                ("lysa_marr", "Lysa Marr", "Deputy registrar and copyist"),
                ("elian_vey", "Elian Vey", "Keeper of the Palimpsest Chronometer"),
            ),
            "answer": "elian_vey",
        },
    ),
    "sequence": (
        {
            "brief": "Four scraps survived in different drawers. Rebuild the night they describe.",
            "events": (
                ("vanishing_petitions", "Vey: Third count. Seven petitions gone. Check the living index."),
                ("secret_copy", "Marr: I made one copy. East desk, false bottom. Tell no one."),
                ("black_seal", "Transfer approved below review. Chancellor's signature. Black Sun affixed."),
                ("bellglass_fire", "Western bell pulled at midnight. Blue flame in the stacks."),
            ),
            "answer": ("vanishing_petitions", "secret_copy", "black_seal", "bellglass_fire"),
        },
        {
            "brief": "Fire erased the timestamps, but not what each writer already knew.",
            "events": (
                ("secret_copy", "L.M.: Copy secured. If Vey is right, the original will not last the night."),
                ("bellglass_fire", "Bellwright's report: flame already blue when the western door opened."),
                ("vanishing_petitions", "E.V.: Names remain in wax. They have vanished only from ink."),
                ("black_seal", "By Black Sun authority, remove Docket VII-13 from public review."),
            ),
            "answer": ("vanishing_petitions", "secret_copy", "black_seal", "bellglass_fire"),
        },
        {
            "brief": "The official account begins with the fire. Three earlier scraps say otherwise.",
            "events": (
                ("black_seal", "Chancellor's instruction: Transfer before first bell. No public notation."),
                ("vanishing_petitions", "Keeper's count: eleven received, four present, seven unaccounted for."),
                ("bellglass_fire", "Western stacks lost. Blue flame resisted water."),
                ("secret_copy", "Marr: The copy is hidden. I pray that makes one of us difficult to erase."),
            ),
            "answer": ("vanishing_petitions", "secret_copy", "black_seal", "bellglass_fire"),
        },
    ),
    "authority": (
        {
            "brief": "Docket VII-13 remained alive after it vanished from public review. Which impression made that possible?",
            "clues": (
                "The Hourglass stopped the deadline, but the docket's lamp still burned in the living index.",
                "The Crown left space for a receiving desk. On VII-13, that space is blank.",
                "The Bell impression sits over blue ash. The transfer ink beneath it was already dry.",
                "The Black Sun impression crosses the public-access line; beneath it, the docket's pulse mark remains unbroken.",
            ),
            "clue_labels": ("HOURGLASS", "CROWN", "ASHEN BELL", "BLACK SUN"),
            "options": (
                ("hourglass", "Keeper's Hourglass", "A blue hourglass impression"),
                ("black_sun", "Chancellor's Black Sun", "A dark solar impression"),
                ("registry_crown", "Registry Crown", "A green crown impression"),
                ("ashen_bell", "Ashen Bell", "A bronze bell impression"),
            ),
            "answer": "black_sun",
        },
        {
            "brief": "Four seals touched the same order. Three recorded what happened. One made the disappearance lawful.",
            "clues": (
                "The Ashen Bell was pressed after the western fire, preserving what remained rather than ordering its removal.",
                "The Keeper's Hourglass sits beside OBJECTION, recording resistance to the order.",
                "The Registry Crown logged the docket's earlier move to the Chronometer chamber.",
                "The Chancellor's Black Sun overlaps the operative words BELOW REVIEW on the final transfer clause.",
            ),
            "clue_labels": ("ASHEN BELL", "HOURGLASS", "CROWN", "BLACK SUN"),
            "options": (
                ("ashen_bell", "Ashen Bell", "A bronze bell impression"),
                ("registry_crown", "Registry Crown", "A green crown impression"),
                ("black_sun", "Chancellor's Black Sun", "A dark solar impression"),
                ("hourglass", "Keeper's Hourglass", "A blue hourglass impression"),
            ),
            "answer": "black_sun",
        },
        {
            "brief": "A living docket disappeared without being closed or received elsewhere. Find the authority in the contradiction.",
            "clues": (
                "The Registry Crown closes or reassigns records; this docket remained active and lists no destination.",
                "The Keeper's Hourglass records a protest and delays action, but grants no transfer power.",
                "The Ashen Bell protects records threatened by disaster; the transfer predates the fire declaration.",
                "A Black Sun impression crosses the authorization line used for sealed final disposition.",
            ),
            "clue_labels": ("CROWN", "HOURGLASS", "ASHEN BELL", "BLACK SUN"),
            "options": (
                ("registry_crown", "Registry Crown", "A green crown impression"),
                ("hourglass", "Keeper's Hourglass", "A blue hourglass impression"),
                ("ashen_bell", "Ashen Bell", "A bronze bell impression"),
                ("black_sun", "Chancellor's Black Sun", "A dark solar impression"),
            ),
            "answer": "black_sun",
        },
    ),
}

TRIAL_REWARDS = {
    "memory": {"gold": 25, "item": "recall_lens", "label": "Recall Lens"},
    "mercy": {"gold": 40, "item": "appeal_tonic", "label": "Appeal Tonic"},
    "order": {"gold": 55, "item": "reset_compass", "label": "Reset Compass"},
}

MERCY_TESTIMONIES = (
    "PARDON GRANTED. The noble returned home. His servant woke with the sentence burned into her record.",
    "RELIEF APPROVED. The river turned from Bellmarket. At dawn, the village downstream was missing from every map.",
    "FEVER REMOVED. The physician remembers a child. The parents remember an empty room they cannot explain.",
)

MERCY_APPEAL_IDS = ("pardon", "diversion", "cure")
MERCY_APPEALS = {
    "pardon": {
        "title": "THE BORROWED SENTENCE",
        "position": (250, 300),
        "activation_rect": (214, 338, 72, 38),
        "summary": "A noble walked free. By morning, the same sentence had appeared in a servant's record.",
        "beats": (
            "The petitioner arrives with a sentence and a very expensive coat.",
            "The Hall grants relief. The wax accepts him immediately.",
            "Behind him, a servant's record begins to burn red.",
            "The petitioner leaves lighter. Someone else does not.",
        ),
        "question": "Who agreed to carry the sentence?",
        "options": (
            ("noble", "THE PETITIONER", "He asked for relief, not substitution."),
            ("servant", "THE SERVANT", "Her record changed. No consent survives."),
            ("none", "NO ONE", "The transfer has no willing bearer."),
        ),
        "answer": "none",
        "finding": "The pardon did not erase punishment. It moved punishment to someone who never entered the hearing.",
    },
    "diversion": {
        "title": "THE RIVER'S SECOND VERDICT",
        "position": (480, 255),
        "activation_rect": (444, 302, 72, 38),
        "summary": "Bellmarket stayed dry. A settlement downstream vanished from every map before dawn.",
        "beats": (
            "Bellmarket petitions the Hall while the river climbs.",
            "A brass gate turns the flood away from its walls.",
            "Downstream, another settlement takes the water instead.",
            "By morning, even the map pretends nobody lived there.",
        ),
        "question": "Whose safety was entered as expendable?",
        "options": (
            ("town", "BELLMARKET", "Its petition names only the town it saved."),
            ("settlement", "THE UNMAPPED", "They paid, but were never called to speak."),
            ("river", "THE RIVER", "Water keeps no hearing record."),
        ),
        "answer": "settlement",
        "finding": "The order protected the named town by removing the unnamed settlement from the account entirely.",
    },
    "cure": {
        "title": "THE PATIENT NO ONE REMEMBERS",
        "position": (710, 300),
        "activation_rect": (674, 338, 72, 38),
        "summary": "A fever broke. The physician remembers a child whose parents remember only an empty room.",
        "beats": (
            "A physician asks the Hall to spare a dying child.",
            "The fever breaks beneath the reliquary's blue light.",
            "Family portraits fade while the patient opens their eyes.",
            "One witness remembers the child. The family remembers an empty room.",
        ),
        "question": "What survived the cure?",
        "options": (
            ("health", "THE RECOVERY", "The fever is gone; the record celebrates that much."),
            ("memory", "ONE WITNESS", "The physician alone remembers the patient."),
            ("consent", "SIGNED CONSENT", "No signature appears in the surviving petition."),
        ),
        "answer": "memory",
        "finding": "The cure preserved a life but severed it from every relationship except one witness's memory.",
    },
}

# The main-hall seal asks the player to apply the Hall's lesson. Relief is not
# honest until the payer and consent are visible; one unknowable cost must stay
# open instead of being assigned for the comfort of a tidy verdict.
# The Mercy seal reconstructs the Hall's concealed accounting. The fourth link
# matters: uncertainty remains open instead of being assigned to a convenient
# victim merely to produce a tidy verdict.
MERCY_CONSEQUENCE_LINKS = (
    {
        "id": "sentence",
        "source": "BORROWED SENTENCE",
        "destination": "HOUSEHOLD LEDGER",
        "finding": "The petitioner left untouched. Before dawn, punishment appeared in the record of someone who served his house.",
    },
    {
        "id": "river",
        "source": "DIVERTED RIVER",
        "destination": "BLANK CARTOGRAPHY",
        "finding": "Bellmarket's gates stayed dry. Downstream, the map lost both a settlement and its name.",
    },
    {
        "id": "memory",
        "source": "SEVERED MEMORY",
        "destination": "LAST WITNESS",
        "finding": "The child lived, but only one physician could still remember the patient's face.",
    },
    {
        "id": "unknown",
        "source": "UNPROVEN COST",
        "destination": "OPEN FINDING",
        "finding": "No surviving page names a willing bearer. An honest ruling leaves that absence unresolved.",
    },
)

FRAGMENT_TESTIMONIES = {
    "memory": "Seven petitions vanished from ink but remained in wax.",
    "mercy": "The seven petitions were granted. Their costs were transferred to names later cut from the record.",
    "order": "The docket was not merely hidden. One authorized stamp taught every surviving registry to agree that it had never existed.",
}

ORDER_ROTOR_RECORDS = (
    ("IDENTITY", "Remove a name here and every later reference points to an empty chair."),
    ("SEQUENCE", "Move one event here and the dates beside it are pulled into the new order."),
    ("AUTHORITY", "A final-disposition stamp makes the altered record lawful enough to survive review."),
    ("CONCORDANCE", "Once sealed, every surviving copy is rewritten until the contradiction disappears."),
)

SEAL_REVELATIONS = {
    "memory": (
        ("THE CHRONOMETER", "The restored sequence catches on one final voice: Vey was trying to warn someone before the Bellglass Fire."),
    ),
    "mercy": (
        ("THE HIDDEN ACCOUNT", "A final line rises beneath the balanced pans: MERCY DOES NOT ERASE A COST. IT CHOOSES WHO PAYS."),
        ("LAST CLERK", "These people got what they asked for. Someone else paid for it."),
        ("MARA", "And whoever approved it removed their names. That was not mercy."),
    ),
    "order": (
        ("THE REGISTRY AUDIT", "The four north marks lock. One Black Sun stamp turns Identity, Sequence, Authority, and every surviving copy together."),
        ("LAST CLERK", "They changed every copy at once."),
        ("MARA", "Yes. That is why all the records agree. They were made to agree."),
    ),
}

SEAL_PUZZLES = {
    "memory": {
        "name": "The Palimpsest Chronometer",
        "relic": "recall_lens",
        "relic_name": "Recall Lens",
        "fragment_name": "Memory Key Fragment",
        "instruction": "Open each tube and read its scrap. Restore the hidden sequence, then pull the lever.",
    },
    "mercy": {
        "name": "The Hearing of Exceptions",
        "relic": "appeal_tonic",
        "relic_name": "Appeal Tonic",
        "fragment_name": "Mercy Key Fragment",
        "instruction": "Name who carries each consequence. Leave uncertainty open when the record cannot prove consent.",
    },
    "order": {
        "name": "The Coupled Registry",
        "relic": "reset_compass",
        "relic_name": "Reset Compass",
        "fragment_name": "Order Key Fragment",
        "instruction": "Each registry ring turns the mechanisms beside it. Bring all four marks to north.",
    },
}

ENEMIES = {
    "red_tape_wraith": {
        "name": "RED TAPE WRAITH",
        "max_hp": 82,
        "damage_range": (9, 14),
        "room": "mercy",
        "position": (500, 365),
        "trial": "mercy",
        "sprite_group": "red_tape",
        "attacks": ("Binding Clause", "Crimson Continuance", "Procedural Whiplash"),
    },
    "misfiled_mimic": {
        "name": "MISFILED MIMIC",
        "max_hp": 96,
        "damage_range": (12, 18),
        "room": "order",
        "position": (480, 300),
        "trial": "order",
        "sprite_group": "misfiled_mimic",
        "attacks": (
            "Drawer Slam",
            "Paper Cut Exhibit",
            "Missing Attachment",
            "False Classification",
            "Duplicate Record",
        ),
    },
    "pending": {
        "name": "THE PENDING",
        "max_hp": 125,
        "damage_range": (14, 21),
        "room": "vault",
        "position": (700, 275),
        "trial": None,
        "sprite_group": "pending",
        "attacks": ("Request for Clarification", "Infinite Attachment", "Reply-All of Despair"),
    },
}
