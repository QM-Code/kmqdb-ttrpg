# Assassin Vine Four-Lane Parent Evaluation

Process guide: `docs/IMAGE_GENERATION_WORKFLOW.md`

Reference target: Pathfinder RPG Bestiary 1 page 22 Assassin Vine. The image direction uses the Pathfinder plant monster entry rather than generic tentacles, treants, or floral monster art.

Core Pathfinder traits: predatory plant, thick coiling vine mass, grasping tendrils, thorny creepers, leafy growth, camouflage in undergrowth, and constricting ambush posture. Avoid humanoid face/body, walking tree-person design, sea-creature tentacles, and flower-centered creature drift.

## Lane Outputs

1. Painterly/bestiary light
   - Image: `assassin-vine-bestiary-light-coiling-grasp.png`
   - Best use: clean light-theme bestiary asset.

2. Readable game-enemy silhouette light
   - Image: `assassin-vine-silhouette-light-coiling-strangler.png`
   - Best use: thumbnail readability for coiling tendrils.

3. Painterly/bestiary dark
   - Image: `assassin-vine-bestiary-dark-thorned-undergrowth.png`
   - Best use: dark-theme bestiary panel.

4. Dynamic CRPG dark
   - Image: `assassin-vine-crpg-dark-bonecoil-ambush.png`
   - Best use: encounter-ready ambush art.

## Checklist Evaluation

- Silhouette match: lanes 2 and 4 should be strongest for the grasping vine outline.
- Anatomy match: all lanes target a plant mass with tendrils, leaves, and thorns.
- Avoids wrong interpretations: prompts avoid treant, humanoid, sea-tentacle, and flower-monster drift.
- Creature-first read: all lanes should read as an active predatory plant.
- Tabletop/CRPG usefulness: two light and two dark variants are present.

## Parent Recommendation

Use `assassin-vine-silhouette-light-coiling-strangler.png` where UI readability matters and `assassin-vine-crpg-dark-bonecoil-ambush.png` for encounter presentation. Use `assassin-vine-bestiary-dark-thorned-undergrowth.png` as the dark bestiary companion.

## Suggested Next Correction

If refining, compare against the saved page and correct any image that develops a humanoid face, trunk body, or non-plant tentacles. Preserve the coiling vine mass and thorned ambush posture.
