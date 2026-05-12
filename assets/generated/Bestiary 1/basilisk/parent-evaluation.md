# Basilisk Three-Lane Parent Evaluation

Process guide: `docs/IMAGE_GENERATION_WORKFLOW.md`

Reference target: Pathfinder basilisk reference supplied by user. Desired direction was the same basilisk idea and color scheme, but with more of the dark spectral Ankou house style.

## Lane Outputs

1. Painterly/bestiary lane
   - Image: `assets/generated/basilisk/basilisk-bestiary-spectral-frilled-stalker.png`
   - Best use: clean tabletop bestiary portrait.
   - Notes: strongest anatomy preservation and creature readability. It keeps the pale underbelly, tan limbs, green frill, dorsal fins, clawed feet, and curved serrated tail. The smoky backdrop and sharper rendering improve it, but it is the least Ankou-like because the background remains light and the mood stays closer to classic bestiary art.

2. Readable game-enemy silhouette lane
   - Image: `assets/generated/basilisk/basilisk-silhouette-spectral-crouch.png`
   - Best use: CRPG/token silhouette and enemy selection.
   - Notes: strongest thumbnail read. The large head, crown/frill, dorsal spine line, low body mass, four splayed legs, and arched tail all read immediately. It also adopts the dark smoky Ankou treatment well. The main tradeoff is that it feels slightly more like a polished monster render than a spectral creature.

3. Dynamic CRPG enemy lane
   - Image: `assets/generated/basilisk/basilisk-crpg-advancing-spectral-hunter.png`
   - Best use: final creature direction if the goal is to match the Ankou set.
   - Notes: best overall style match to the Ankou variants. The darker background, stronger rim light, high-contrast shadows, forward threat posture, and glowing eyes create the most cohesive family resemblance. It preserves the key basilisk anatomy while feeling more encounter-ready and ominous.

## Checklist Evaluation

- Silhouette match: Agent 2 is strongest, Agent 3 close behind, Agent 1 readable but less dramatic.
- Anatomy match: Agent 1 is strongest, Agent 3 strong, Agent 2 strong with a slightly more render-polished emphasis.
- Avoids wrong interpretations: all three avoid dragon, serpent, wings, humanoid, rider, armor, text, and extra heads.
- Creature-first read: all three succeed. None looks like a person in costume.
- Eyes/posture/body language: Agent 3 is strongest for hostile encounter energy; Agent 1 is calmer; Agent 2 is readable and watchful.
- Tabletop/CRPG usefulness: Agent 1 is best for a printed bestiary entry, Agent 2 for token readability, Agent 3 for a final CRPG/bestiary asset paired with the Ankou.

## Parent Recommendation

Use `basilisk-crpg-advancing-spectral-hunter.png` as the leading candidate if this basilisk should sit beside the Ankou set. It has the best combination of basilisk identity, dark spectral mood, and encounter-ready posture.

Use `basilisk-silhouette-spectral-crouch.png` as the fallback if thumbnail readability matters most.

Use `basilisk-bestiary-spectral-frilled-stalker.png` if the goal is a cleaner, more traditional Pathfinder-style creature portrait.

## Suggested Next Correction

If doing a second refinement round, start from Agent 3 and ask for: keep the exact pose and dark smoky mood, preserve the full body and serrated tail, make the green head frill and dorsal fin shapes slightly broader and more leaf-like like the reference, and add a subtle spectral green glow through the chest/throat folds to echo the Ankou internal glow without turning the basilisk into an Ankou.
