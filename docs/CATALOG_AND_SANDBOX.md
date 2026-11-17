# Catalog UI and Sandbox Game

Shop and Inventory use icon categories, with labels, counts, hover descriptions, and keyboard focus. Both have local search with partial keywords, category synonyms, small typo tolerance, and up to eight suggestions. Selecting a suggestion focuses the matching item; it never buys or equips it. Inventory searches only owned items. Search relevance comes first, with the default item order resolving ties.

Inventory's default priority is currently equipped items, newest acquisition dates, highest use counts, then the previous stable order. Acquisition date takes precedence over usage frequency. Existing profiles have no reliable historical dates or use counts, so those values are not fabricated. From this update onward, purchases, free claims, newly earned badges, and the first custom wallpaper import record acquisition dates. Equipping items and launching games record use counts. Applying an existing selection during startup does not count as another use. History is stored in the existing rewards JSON and survives rebuilds.

Category and result widgets are created on demand. The category icons are transparent 256-pixel PNGs; their full generation prompts and source references are in `CATALOG_ICON_PROMPTS.json`.

Out of Spec: The Archivist Trials now lives in the sibling `SADM Autorouter Sandbox` project. Its code, 230 resource files, icon, documentation, preview tool, and 136 regression tests were transferred and checksum-verified. Sandbox saves and rewards use `%PUBLIC%\ach\Sandbox`. Existing production progress seeds a separate sandbox copy once; subsequent sandbox game saves and coin rewards stay there. Its game module is registered in the sandbox's PyInstaller hidden imports.

Production contains Tetris only and explicitly excludes the RPG module from PyInstaller. Approximately 330 MiB of RPG resources were removed from the production source payload. Existing EXEs are unchanged until rebuilt; the exact compressed size reduction depends on PyInstaller compression. Run `python build_with_loader.py --onefile` to produce the updated production EXE with the existing loader and Tesseract configuration.

Verification:

- `python -m unittest tests.test_catalog_search tests.test_inventory_order tests.test_rewards_progression tests.test_catalog_ui -q`
- `python tools/verify_catalog_ui.py` for a native preview with mocked data and an isolated profile.
- In the sandbox: `python tools/verify_archivist_sandbox.py` verifies native game launch, art, Inventory window lifetime, save migration, isolated rewards, and unchanged original test files. It uses a temporary profile.
- The original 136 game regressions passed in the sandbox. Decoded test artwork was reused between test canvases to avoid repeated disk decoding; each canvas received its own implicit Qt image copy.

The detailed transfer manifest is saved as `output/archivist-transfer-manifest.json` in production and `docs/ARCHIVIST_TRANSFER_MANIFEST.json` in the sandbox.
