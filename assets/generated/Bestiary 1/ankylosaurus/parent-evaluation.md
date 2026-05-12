# Ankylosaurus Four-Lane Parent Evaluation

Process guide: `docs/IMAGE_GENERATION_WORKFLOW.md`

Reference target: Pathfinder RPG Bestiary 1 page 83 Ankylosaurus. The image direction uses the Pathfinder dinosaur reference rather than generic dragon, turtle, or fantasy mount art.

Core Pathfinder traits: low heavy quadrupedal dinosaur, broad armored body, bony back plates/scutes, short powerful legs, wedge-shaped head, and heavy clubbed tail. Avoid horns/wings, saddle/rider, dragon posture, and humanoid armor.

## Lane Outputs

1. Painterly/bestiary light
   - Image: `ankylosaurus-bestiary-light-clubtail-plates.png`
   - Best use: clean light-theme bestiary asset.

2. Readable game-enemy silhouette light
   - Image: `ankylosaurus-silhouette-light-armored-clubtail.png`
   - Best use: thumbnail profile with armored back and tail club.

3. Painterly/bestiary dark
   - Image: `ankylosaurus-bestiary-dark-clubtail-armor.png`
   - Best use: dark-theme bestiary presentation.

4. Dynamic CRPG dark
   - Image: `ankylosaurus-crpg-dark-volcanic-clubtail.png`
   - Best use: encounter-ready dark-theme creature asset.

## Checklist Evaluation

- Silhouette match: lanes 2 and 4 should be strongest if the low body and tail club remain readable.
- Anatomy match: all lanes target the armored quadruped dinosaur with bony plates and heavy club tail.
- Avoids wrong interpretations: prompts and lane notes avoid dragon, turtle-only, rider, and armored mount drift.
- Creature-first read: all lanes should read as a dinosaur first.
- Tabletop/CRPG usefulness: two light and two dark variants are present.

## Parent Recommendation

Use `ankylosaurus-silhouette-light-armored-clubtail.png` for clean recognition and `ankylosaurus-crpg-dark-volcanic-clubtail.png` for encounter art, after visual QA confirms the tail club is fully in frame.
