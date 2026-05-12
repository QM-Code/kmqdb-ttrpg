# Barghest Four-Lane Parent Evaluation

Process guide: `docs/IMAGE_GENERATION_WORKFLOW.md`

Reference target: Pathfinder RPG Bestiary 1 page 27 Barghest. The image direction uses the Pathfinder fiendish goblin-hound reference rather than generic wolf, werewolf, or demon dog art.

Core Pathfinder traits: goblin-like wolf-fiend, gaunt hound body, clawed hand-like forelimbs, predatory crouch, sharp teeth, dark planar menace, and intelligent monster posture. Avoid ordinary wolf, werewolf, goblin soldier, armor/rider, and winged demon drift.

## Lane Outputs

1. Painterly/bestiary light
   - Image: `barghest-bestiary-light-goblin-hound.png`
   - Best use: clean light-theme inspection asset.

2. Readable game-enemy silhouette light
   - Image: `barghest-silhouette-light-handclaw-stalker.png`
   - Best use: thumbnail recognition of the hound body and hand-claw forelimbs.

3. Painterly/bestiary dark
   - Image: `barghest-bestiary-dark-goblin-stalker.png`
   - Best use: dark-theme bestiary panel.

4. Dynamic CRPG dark
   - Image: `barghest-crpg-dark-handclaw-prowl.png`
   - Best use: encounter-ready prowling fiend art.

## Checklist Evaluation

- Silhouette match: lanes 2 and 4 should be strongest for the hybrid goblin-hound shape.
- Anatomy match: all lanes target a gaunt hound body with clawed hand-like forelimbs.
- Avoids wrong interpretations: prompts avoid ordinary wolf, werewolf, armored goblin soldier, and winged demon drift.
- Creature-first read: all lanes should read as a planar monster rather than mundane animal.
- Tabletop/CRPG usefulness: two light and two dark variants are present.

## Parent Recommendation

Use `barghest-silhouette-light-handclaw-stalker.png` for UI readability and `barghest-crpg-dark-handclaw-prowl.png` for encounter presentation. Use `barghest-bestiary-dark-goblin-stalker.png` as the dark bestiary companion.
