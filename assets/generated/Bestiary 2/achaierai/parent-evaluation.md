# Achaierai Three-Lane Parent Evaluation

Process guide: `docs/IMAGE_GENERATION_WORKFLOW.md`

Reference target: Pathfinder RPG Bestiary 2 page 7 Achaierai, illustration by Tyler Walpole. The image direction must use the Pathfinder version as the source, not folklore or other fantasy interpretations.

Core Pathfinder traits: fused black bird-like head/body mass, four long pinkish scaly stilt legs, clawed feet, hooked black beak, oily black plumage, tiny/atrophied wings mostly hidden by feathers, and toxic black vapor pouring from the beak.

## Lane Outputs

1. Painterly/bestiary lane
   - Image: `assets/generated/achaierai/achaierai-bestiary-oily-vapor-stalker.png`
   - Notes: cleanest bestiary reference image. It has the strongest neutral-background readability, strong four-legged anatomy, visible toxic vapor, and clear oily black plumage. The main risk is that the body reads a little more like a large conventional bird torso than the flattened fused mass in the original Pathfinder page art.

1a. Second light-background variant
   - Image: `assets/generated/achaierai/achaierai-bestiary-light-vapor-prowler.png`
   - Notes: additional light-background exploration added to satisfy the two-light/two-dark production preference. It preserves the same Pathfinder anatomy and keeps the black vapor readable against pale smoke. It is compositionally close to the first bestiary lane, so it is best treated as a light-background alternate rather than a distinct design direction.

2. Readable game-enemy silhouette lane
   - Image: `assets/generated/achaierai/achaierai-silhouette-black-vapor-stalker.png`
   - Notes: strongest thumbnail silhouette. The black body mass, hooked beak, four separated stilt legs, clawed feet, hidden wing, and vapor stream are legible against the dark smoky background. The main risk is slight raptor-head drift, though the four legs keep it from becoming a normal bird.

3. Dynamic CRPG enemy lane
   - Image: `assets/generated/achaierai/achaierai-crpg-toxic-vapor-lunge.png`
   - Notes: best encounter-ready action pose. The lunging body, open beak, toxic vapor, and long legs create strong CRPG threat. It is the most dramatic but also has the most environment-specific background, so it may need a cleaner light/dark production pass later.

## Checklist Evaluation

- Silhouette match: Agent 2 is strongest, Agent 3 close behind, Agent 1 clear but less graphic.
- Anatomy match: Agent 1 is strongest for reference clarity, Agent 3 strong for action, Agent 2 strong with minor raptor-head risk.
- Avoids wrong interpretations: all three avoid normal two-legged bird, large flight wings, humanoid/demon drift, dragon/wyvern cues, armor, rider, and extra heads.
- Creature-first read: all three succeed.
- Eyes/posture/body language: Agent 3 is strongest for hostile encounter energy; Agent 1 is best for calm bestiary inspection; Agent 2 is most readable as an enemy icon.
- Tabletop/CRPG usefulness: Agent 1 for a bestiary entry, Agent 2 for thumbnail/token readability, Agent 3 for encounter art.

## Parent Recommendation

Use `achaierai-crpg-toxic-vapor-lunge.png` as the leading candidate if the goal is a dramatic website/encounter creature asset.

Use `achaierai-bestiary-oily-vapor-stalker.png` if the goal is the most faithful, easy-to-read Pathfinder bestiary reference.

Use `achaierai-silhouette-black-vapor-stalker.png` if thumbnail clarity and dark-theme presentation matter most.

The current folder now contains two light-background explorations and two dark-background explorations:

- Light: `achaierai-bestiary-oily-vapor-stalker.png`
- Light: `achaierai-bestiary-light-vapor-prowler.png`
- Dark: `achaierai-silhouette-black-vapor-stalker.png`
- Dark: `achaierai-crpg-toxic-vapor-lunge.png`

## Suggested Next Correction

For a refinement round, start from Agent 3's pose and energy, but borrow Agent 1's clearer head/body fusion and Agent 2's clean silhouette. Ask for the background to be simpler and more production-friendly, with both light and dark variants on a 1440x1080 canvas.
