# Air Elemental Prompts and Lane Notes

Reference images:
- `pathfinder-bestiary-1-page-120-reference.webp`
- `pathfinder-bestiary-1-page-121-reference.webp`

Shared Pathfinder constraints:
- Living air / whirlwind creature.
- Smoky bird-like upper suggestion with glowing dark eye hollows and dark mouth.
- Gray-white wind ribbons, winglike gust forms, and a vortex / tornado column body.
- No solid legs, no feet, no humanoid clothing, no armor, no weapons.
- Avoid fire, water, earth, rock, dirt, lava, plant, humanoid, and page-layout drift.
- Production canvas requested as 4:3, target 1440x1080. Generated files are 1448x1086.

## Production Lanes

### Bestiary Light

Output:
- `air-elemental-bestiary-light-painterly-vortex.png`

Prompt:

```text
Use case: stylized-concept
Asset type: Pathfinder TTRPG bestiary creature production art, 4:3 canvas, target 1440x1080.
Lane: bestiary light-background.
Primary request: Create a Pathfinder-style Air Elemental: a living air and whirlwind creature, inspired by the provided Pathfinder Bestiary page reference. Painterly fantasy bestiary illustration on a pale parchment / light neutral background.
Subject: A gray-white smoky bird-like upper suggestion formed entirely from wind and cloud, with ragged featherlike gusts, glowing dark eye hollows and an ominous dark mouth hollow. The body must resolve into a tall rotating vortex/tornado column made of layered gray, white, and blue-gray wind ribbons. No solid legs. No feet. No humanoid clothing, armor, weapons, jewelry, or gear.
Composition: Full creature in frame, centered, dynamic S-curve tornado silhouette, enough padding on all sides, no cropped anatomy. The upper mass should feel avian and cloudlike rather than humanoid. Wind ribbons wrap around the vortex and trail outward like wings.
Lighting/style: Hand-painted high-fantasy bestiary art, crisp readable silhouette, ink-and-paint detail, subtle parchment texture, light background variant for website use.
Hard constraints: living air only; smoky bird-like upper suggestion with glowing dark eye hollows and mouth; gray-white wind ribbons; vortex body/tornado column; no solid legs; no humanoid clothing/armor; no fire, water, rock, dirt, lava, plants, or earth elemental drift; no text, watermark, stat block, border, or page layout.
```

Lane notes:
- Strong match for reference anatomy: cloud-bird head, dark mouth, and clear tornado body.
- Light parchment background supports bestiary use.
- Slightly broad wing ribbons, but still reads as air rather than fabric or limbs.

### Silhouette Light

Output:
- `air-elemental-silhouette-light-readable-vortex.png`

Prompt:

```text
Use case: stylized-concept
Asset type: readable game-enemy silhouette production art, 4:3 canvas, target 1440x1080.
Lane: silhouette light-background.
Primary request: Create a Pathfinder-style Air Elemental with maximum thumbnail readability on a clean light background.
Subject: A living whirlwind creature made only of air, smoke, and cloud. Upper body is a smoky bird-like suggestion: swept-back gust-feather crest, dark hollow eyes with faint glow, open dark mouth hollow. The lower body is a tapered tornado column, not legs. Gray-white and blue-gray wind ribbons form winglike side masses and spiral bands around the vortex.
Composition: Strong single readable silhouette, centered and fully visible with generous padding, large S-shaped tornado column, no ground contact except a small diffuse swirl of air. Avoid cluttered background. The creature should read as a bird-shaped storm riding a vertical vortex.
Lighting/style: Painterly fantasy creature art, high contrast edge design, light neutral background, clean game-token readability while preserving bestiary quality.
Hard constraints: living air/whirlwind creature; smoky bird-like upper suggestion; glowing dark eye hollows and mouth; gray-white wind ribbons; vortex body/tornado column; absolutely no solid legs, no feet, no humanoid costume, no armor, no weapons; no fire/water/earth/rock/plant/lava traits; no text, no border, no logo, no watermark.
```

Lane notes:
- Best light-background silhouette of the set; reads clearly at thumbnail size.
- Mouth and eye hollows are more aggressive and visible than the bestiary light lane.
- No solid legs or humanoid costume drift.

### Bestiary Dark

Output:
- `air-elemental-bestiary-dark-storm-vortex.png`

Prompt:

```text
Use case: stylized-concept
Asset type: Pathfinder TTRPG bestiary creature production art, 4:3 canvas, target 1440x1080.
Lane: bestiary dark-background.
Primary request: Create a Pathfinder-style Air Elemental for a dark website theme, matching the Pathfinder Bestiary visual: living smoke, wind, and tornado anatomy.
Subject: A gray-white smoky bird-like upper suggestion made of cloud and air, with deep black eye hollows containing subtle cold glow and a black howling mouth hollow. Its entire lower body is a spinning vortex/tornado column of gray, white, and blue-gray air bands. Long pale wind ribbons spiral around the body and flare outward like wings. No solid legs or feet anywhere.
Composition: Full creature inside frame, centered, dramatic but readable against a deep charcoal/blue-black storm background, enough padding, no cropped ribbons. The creature must remain air-like and translucent at the edges.
Lighting/style: Painterly high-fantasy bestiary illustration, luminous white-gray wind strands, dark atmospheric background, refined creature concept art, no page text.
Hard constraints: living air/whirlwind creature only; smoky bird-like upper suggestion with glowing dark eye hollows and mouth; gray-white wind ribbons; vortex/tornado column; no humanoid body, no clothing, no armor, no weapons, no solid legs; no flames, water splashes, rocks, dirt, crystal, lava, plants, or earth elemental cues; no text, watermark, logo, border, stat block, or book page.
```

Lane notes:
- Strong dark-theme usability, with pale wind ribbons separated from the background.
- Head and mouth remain readable; body stays a tornado column.
- Background includes storm clouds only, not water or earth cues.

### CRPG Dark

Output:
- `air-elemental-crpg-dark-swooping-vortex.png`

Prompt:

```text
Use case: stylized-concept
Asset type: CRPG enemy splash / combat portrait production art, 4:3 canvas, target 1440x1080.
Lane: CRPG dark-background.
Primary request: Create a dynamic Pathfinder-style Air Elemental for a dark CRPG bestiary/combat screen.
Subject: A living air elemental in attack motion: smoky bird-like upper form made from shredded cloud and gale-force wind, glowing dark eye hollows, open black howling mouth hollow, winglike arcs of gray-white wind ribbons, and a powerful tornado-column lower body. It is entirely wind, smoke, and vapor, with no solid legs, no feet, no armor, no clothing, no weapon.
Composition: Diagonal action pose, as if swooping out of a spinning vortex, but the whole creature remains fully inside the 4:3 frame with padding. Strong tornado base, spiral wind bands wrapping around the body, readable head and mouth at thumbnail scale.
Lighting/style: Dramatic painterly CRPG creature art, dark blue-black storm background, luminous cool highlights on gray-white ribbons, high contrast but not fire-lit, no UI text.
Hard constraints: Pathfinder air elemental visual, living air/whirlwind creature, smoky bird-like upper suggestion with glowing dark eye hollows and mouth, gray-white wind ribbons, vortex/tornado column, no solid legs, no humanoid clothing/armor, no fire, no water, no rocks, no dirt, no earth elemental drift, no text, watermark, logo, border, or stat block.
```

Lane notes:
- Most dramatic action option; strong face and sweeping ribbon motion.
- Tornado body is intact and fully inside frame.
- Dark background makes it suitable for CRPG presentation.

## Rejected Default-Folder Alternates

The user-specified default image folder also contained eight generated PNGs. They were copied into this directory with `air-elemental-rejected-default-*` filenames to preserve outputs, but they are not production candidates:

- `air-elemental-rejected-default-01-humanoid-light.png`: humanoid robed caster with staff; violates no-humanoid, no-clothing, no-weapon constraints.
- `air-elemental-rejected-default-02-humanoid-light.png`: humanoid robed caster with staff; violates no-humanoid, no-clothing, no-weapon constraints.
- `air-elemental-rejected-default-03-humanoid-dark.png`: humanoid robed caster with staff; violates no-humanoid, no-clothing, no-weapon constraints.
- `air-elemental-rejected-default-04-humanoid-dark.png`: humanoid robed caster with staff; violates no-humanoid, no-clothing, no-weapon constraints.
- `air-elemental-rejected-default-05-water-creature-light.png`: aquatic/serpentine creature; violates air elemental anatomy and water drift constraints.
- `air-elemental-rejected-default-06-water-creature-light.png`: aquatic/serpentine creature; violates air elemental anatomy and water drift constraints.
- `air-elemental-rejected-default-07-water-creature-dark.png`: aquatic/serpentine creature; violates air elemental anatomy and water drift constraints.
- `air-elemental-rejected-default-08-water-creature-dark.png`: aquatic/serpentine creature; violates air elemental anatomy and water drift constraints.
