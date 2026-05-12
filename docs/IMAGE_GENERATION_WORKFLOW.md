# Image Generation Workflow

This note records the sequence that produced the most accurate Pathfinder-style
ankou images so future agents can replicate the process for other creatures.

## Successful Sequence

1. Start with the Pathfinder-specific creature visual reference, not a folklore
   summary or a general fantasy interpretation.
2. Extract concrete anatomy and silhouette requirements from that reference.
3. Split generation across four parallel prompt lanes so each lane owns one
   required light/dark production slot.
4. Generate one image per lane and save every generated exploration image in
   the repo immediately.
5. Evaluate against explicit visual criteria.
6. Feed corrections back to every lane with the same reference image attached.
7. Generate a second round from the corrected reference-driven prompt.
8. For production-ready creature assets, create both light-background and
   dark-background variants so the art remains usable across site themes
   without losing painterly smoke or atmosphere.
9. Save the successful images and the prompt/evaluation notes in the repo.

## Pathfinder Ankou Notes

The first attempts drifted toward a generic shadow humanoid. The accurate
direction came only after using a direct visual reference and these corrections:

- Broad manta-like wing/body silhouette.
- Wings form most of the body mass and encompass the creature.
- Wings are solid, leathery, and veined, not ragged bat wings.
- No legs or feet.
- Lower body ends in a tucked, barbed tail or lower point.
- Hooked neck and head forms.
- Small clawed arms emerge from the body.
- Red/orange glowing chest slits.
- Red or demonic glowing eyes and a predatory grin.
- Avoid Celtic folklore, reaper, hood, robe, scythe, cart, standing humanoid,
  boots, or grounded monster cues.

## Reference Source Rule

When recreating or refining a monster, use the Pathfinder version of that
monster as the source reference by default. Do not use folklore, mythology,
general fantasy art, other tabletop systems, or adjacent creature archetypes as
the primary visual source unless the user explicitly requests that direction.

## Reusable Agent Pattern

The main agent in the user-facing session is the batch parent. The batch parent
is the only agent responsible for talking to the human, interpreting corrections,
tracking progress, and deciding when to pause or continue. Sub-agents should be
used for production work, not for human coordination.

Use sub-agents aggressively to maximize image throughput. Spawn as many useful
sub-agents as the session allows, while keeping each sub-agent's file ownership
clear and non-overlapping. The parent can delegate by creature, by lane, or by
theme, whichever keeps the most image lanes productively in flight.

For a single creature image set, the default parallel pattern is four lane
agents:

```text
Agent 1: painterly/bestiary light-background lane
Agent 2: readable game-enemy silhouette light-background lane
Agent 3: painterly/bestiary dark-background lane
Agent 4: dynamic CRPG dark-background lane
```

Give every agent the same reference image and the same hard constraints, but let
each lane emphasize its assigned design priority and background value. Ask
agents to return the image path plus two or three judging notes.

Every sub-agent prompt must include:

- The exact creature directory it owns.
- The exact reference image path or paths to use.
- The lane it should generate.
- A reminder to copy the generated image from its own tool-managed
  `$HOME/.codex/generated_images/...` folder into the repo creature directory.
- A reminder to leave generated originals in place.
- A reminder not to overwrite existing files and not to touch other creature
  directories.
- A requirement to save a matching prompt/lane note and report exact repo paths.

As sub-agents finish, the batch parent should immediately give idle agents the
next missing lane from the current monster set. Keep agents warm until the
current assigned set is complete, then let them pause unless the human asks to
continue into another set.

## Repo Save Convention

Generated creature images are repo assets by default, even during discovery.
Do not leave useful generations only in a temporary or tool-managed image
folder.

Save each creature's outputs under:

```text
assets/generated/<book-name>/<creature-slug>/
```

Use descriptive filenames that include the creature and lane or purpose:

```text
<creature>-bestiary-light-<short-direction>.png
<creature>-silhouette-light-<short-direction>.png
<creature>-bestiary-dark-<short-direction>.png
<creature>-crpg-dark-<short-direction>.png
```

Also save prompt and evaluation notes in the same folder when a direction is
selected, refined, or useful for future comparison.

## Book Monster Lists

Each Bestiary directory should include a plain-text monster list extracted from
the Pathfinder book's AnyFlip alphabetical listing:

```text
assets/generated/Bestiary 1/monster-list.txt
assets/generated/Bestiary 2/monster-list.txt
assets/generated/Bestiary 3/monster-list.txt
assets/generated/Bestiary 4/monster-list.txt
assets/generated/Bestiary 5/monster-list.txt
assets/generated/Bestiary 6/monster-list.txt
```

Use these lists as the production queue. A monster is considered already started
when its creature directory exists under the matching book directory. Skip those
directories when selecting the next batch.

Each `monster-list.txt` should also include an `Image Generation Status` section
near the end. The batch parent owns this status section and updates it as work
progresses:

```text
## Image Generation Status

Status key: `pending`, `references saved`, `in progress`, `images complete`,
`evaluation complete`, `manual review`.

- Creature name — page — status detail — directory: `creature-slug`
```

Update the status when references are saved, lanes are assigned, images are
complete, and parent evaluations are complete. If a book has no creature
directories started yet, record that explicitly.

When a creature reaches `evaluation complete`, cross it off in the status
section so the next agent can scan the queue quickly:

```text
- [x] Creature name — page — evaluation complete — directory: `creature-slug`
- [ ] Next creature — page — pending — directory: `next-creature-slug`
```

Do not cross off a creature just because the directory exists. Cross it off only
after the required images, notes, references, and `parent-evaluation.md` are
saved, or after it is intentionally marked `manual review`.

## Five-Monster Batch Pattern

To produce images faster, run up to five monsters at a time. The top-level
parent agent owns the batch, talks to the human, and delegates image generation
to sub-agents. Prefer the delegation pattern that keeps the most useful image
lanes running in parallel.

Two efficient patterns are acceptable:

```text
Creature-supervisor pattern
Batch parent
Monster supervisor 1: owns creature 1 and generates its four lanes
Monster supervisor 2: owns creature 2 and generates its four lanes
Monster supervisor 3: owns creature 3 and generates its four lanes
Monster supervisor 4: owns creature 4 and generates its four lanes
Monster supervisor 5: owns creature 5 and generates its four lanes
```

```text
Lane-worker pattern
Batch parent
Lane agent 1: creature 1, bestiary light
Lane agent 2: creature 1, silhouette light
Lane agent 3: creature 1, bestiary dark
Lane agent 4: creature 1, CRPG dark
...
Lane agent 20: creature 5, CRPG dark
```

The parent may also group work by theme if that is more efficient, for example
one agent generating bestiary-light lanes for several creatures while another
agent generates CRPG-dark lanes. Use this only when ownership remains clear and
agents will not overwrite one another.

Each creature must still end with the same four-lane image pattern:

```text
Lane 1: painterly/bestiary light-background image
Lane 2: readable game-enemy silhouette light-background image
Lane 3: painterly/bestiary dark-background image
Lane 4: dynamic CRPG dark-background image
```

This creates a maximum of 20 image lanes in flight for a full five-monster
batch. Spawn as many of those 20 lanes as the current session allows. If fewer
than 20 sub-agents can run at once, keep a queue of missing lanes and assign the
next lane as soon as an agent reports a saved repo path.

Do not close or abandon a productive sub-agent merely because it has not written
notes yet. If images exist only in the tool-managed generated image folder,
instruct the agent to copy them into the repo creature directory and then
continue or pause according to the current batch plan.

Batch sequence:

1. Read the `monster-list.txt` files for the target books.
2. Select the next five monsters that do not already have creature directories.
3. For each selected monster, create:

   ```text
   assets/generated/<book-name>/<creature-slug>/
   ```

4. Use the page number from `monster-list.txt` to open the matching Pathfinder
   AnyFlip page.
5. Save the Pathfinder page image or cropped page reference in the creature
   directory with a name like:

   ```text
   pathfinder-bestiary-<number>-page-<page>-reference.webp
   ```

6. Extract concrete anatomy, silhouette, color, posture, and avoid-list
   constraints from that Pathfinder page art.
7. Spawn sub-agents to run the four image lanes with the same reference image
   and hard constraints. Maximize parallel production within the current session
   limits.
8. Save every generated image, prompt note, and lane note in the creature
   directory.
9. Have the monster supervisor write `parent-evaluation.md` for that creature.
10. Have the batch parent write a short batch summary listing completed
    monsters, any failed reference pulls, and any creatures needing a second
    correction round.
11. Keep the `Image Generation Status` section in the matching
    `monster-list.txt` current throughout the batch.
12. Cross off each creature in `monster-list.txt` as soon as it reaches
    `evaluation complete` or `manual review`.

Do not use non-Pathfinder reference art to fill gaps. If the page image is
missing, low quality, or ambiguous, record that blocker and leave the monster for
manual review rather than substituting folklore or unrelated fantasy art.

## Production Variant Pattern

Each creature generation set should produce four variants:

```text
2 light-background variants
2 dark-background variants
```

Use the same creature anatomy, silhouette, and art direction across all four.
Only vary the background value, smoke treatment, and lighting balance enough to
make each image usable on dark-theme and light-theme website surfaces.

Before final production, record the current generated image dimensions and
use a standard 4:3 production canvas:

```text
1440x1080
```

Keep the full creature inside the frame with enough padding for website display.
Do not crop important anatomy such as wings, tails, legs, frills, or weapon-like
silhouettes.

## Evaluation Checklist

For each generated creature image, check:

- Does the silhouette match the source creature at thumbnail size?
- Does the anatomy match the required traits?
- Does it avoid known wrong interpretations?
- Does it look like a creature first, not a person in costume?
- Are the eyes, posture, and body language aligned with the target creature?
- Is the image useful as a tabletop or CRPG bestiary asset?

## Saved Ankou Variants

The successful reference-informed variants are saved at:

```text
assets/generated/Bestiary 1/ankou/ankou-godel-spectral-winged-horror.png
assets/generated/Bestiary 1/ankou/ankou-poincare-bestiary-shadow-predator.png
assets/generated/Bestiary 1/ankou/ankou-kierkegaard-inhuman-winged-shade.png
```
