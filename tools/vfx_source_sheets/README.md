# Badge VFX Source Sheets

These PNG files are build-time source material for the achievement badge
animation generator. They are intentionally stored under `tools/` instead of
`assets/` so PyInstaller does not bundle the raw source sheets into the EXE.

Runtime uses only the generated frames in:

```text
assets/images/badge_vfx
```

Regenerate after changing recipes or source sheets:

```powershell
python -B tools\generate_badge_vfx.py
```

## Sources And Licenses

All source sheets below are listed as CC0 / public domain on OpenGameArt at the
time they were added.

- Animated Particle Effects #2 by para:
  https://opengameart.org/content/animated-particle-effects-2
  - `air_bubbles_01.png`
  - `air_bubbles_02.png`
  - `fire_01.png`
  - `fire_01b.png`
  - `fire_01c.png`
  - `fire_02.png`
  - `lighter_flame_01.png`
  - `teleporter_01.png`
  - `teleporter_hit.png`
- Lots of Game Effects by Soluna Software:
  https://opengameart.org/content/lots-of-game-effects
  - `Fire01.png`
  - `Explosion25.png`
  - `Effect36.png`
  - `Effect51.png`
  - `ToonExplosion31.png`
- Energy Sprite Sheets by fzeeshan:
  https://opengameart.org/content/energy-sprite-sheets
  - `energy1_0.png`
  - `energy2.png`
  - `energy3.png`
  - `energy4.png`
- Animated Fire by clint bellanger:
  https://opengameart.org/content/animated-fire
  - `fire1_64.png`
  - `fire2_64_0.png`
  - `fire3_64.png`
  - `fire4_64.png`
  - `fire5_64.png`
  - `fire6_64.png`
  - `fire7_64.png`
  - `fire8_64.png`
- Smoke Particles by Fupi:
  https://opengameart.org/content/smoke-particles
  - `smoke1.png`
  - `smoke2.png`
  - `smoke3.png`
  - `smoke4.png`
- Magic Mirror by Clint Bellanger:
  https://opengameart.org/content/magic-mirror
  - `MagicMirror.png`
- Poof effect sheet:
  https://opengameart.org/content/poof-effect-spritesheet
  - `Poof.png`

Direct OpenGameArt file downloads were blocked on this workstation, so the PNGs
were fetched through an image proxy while preserving the original filenames and
source attribution above.
