# Out of Spec: The Archivist Trials

`frontend/rpg` is the internal package for this self-contained RPG. It may read and award coins through
`utils.rewards`, but it does not import or modify autorouting workflows.

## Modules

- `window.py`: PyQt rendering, input, exploration, dialogue, and combat.
- `level_one.py`: declarative room, passage, encounter, puzzle, and reward content.
- `state.py`: versioned, serializable player progress.
- `persistence.py`: atomic save files and one-time completion rewards.
- `assets/rpg`: generated environment, character, NPC, boss, and catalog art.
- `docs/OUT_OF_SPEC_LORE_BIBLE.md`: internal canon and long-form character arcs.
- `docs/OUT_OF_SPEC_LEVEL_ONE_NARRATIVE_OUTLINE.md`: production story and reveal sequence for Level I.

## Player data

Progress is stored at `C:\Users\Public\ach\archivebound_save.json`, beside the
version-resilient rewards file. Replacing the application EXE does not reset it.

## Controls

- Move: arrow keys
- Interact/continue: `Space` or `Enter`
- Battle abilities: `Q`, `W`, `E`, and `R`
- Trial relics: `1`, `2`, and `3`
- Exit: `Esc`

## Level I

The Hall of Pending Things is a hub with three traversable passages. Each seal now
has its own prerequisite rather than being collected directly in the hub:

- Memory: restore the Past, Present, and Future Archives in any order, then pass the Chronometer's sequence test.
- Mercy: defeat the Red Tape Wraith.
- Order: restore Docket VII-13 through Identity, Sequence, and Authority, then defeat the Misfiled Mimic.

Each trial grants a unique item and gold. The central vault only opens after all
three are complete, preserving old save progress through the versioned migration.

Level I narrative progress is stored as versioned story flags alongside mechanical
progress. Legacy saves infer already-passed scenes from completed halls and vault state,
so updates do not replay introductions or overwrite player progress.

Room navigation uses authored floor regions, object-shaped solid footprints, reciprocal
door triggers, and safe arrival points. Collisions stop or slide the player without
masking any part of the character sprite. Combat cooldowns advance by turns; enemy families
have distinct damage and effects. Trial relics recharge once per encounter, and
Mara can spend trial gold to restore the Archivist between fights.

Future levels should add their content definitions separately and keep the save
schema versioned. Router modules must never depend on game state.
