# Image Generation Workflow

This note records the sequence that produced the most accurate Pathfinder-style
ankou images so future agents can replicate the process for other creatures.

## Successful Sequence

1. Start with the creature-specific visual reference, not a folklore summary.
2. Extract concrete anatomy and silhouette requirements from that reference.
3. Split exploration across three parallel prompt lanes so each lane can try a
   distinct interpretation.
4. Generate one image per lane.
5. Evaluate against explicit visual criteria.
6. Feed corrections back to every lane with the same reference image attached.
7. Generate a second round from the corrected reference-driven prompt.
8. Save the successful images and the prompt/evaluation notes in the repo.

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

## Reusable Agent Pattern

Use three agents in parallel when exploring a creature image:

```text
Agent 1: painterly/bestiary lane
Agent 2: readable game-enemy silhouette lane
Agent 3: dynamic CRPG enemy lane
```

Give every agent the same reference image and the same hard constraints, but let
each lane emphasize a different design priority. Ask agents to return the image
path plus two or three judging notes.

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
assets/generated/ankou/ankou-godel-spectral-winged-horror.png
assets/generated/ankou/ankou-poincare-bestiary-shadow-predator.png
assets/generated/ankou/ankou-kierkegaard-inhuman-winged-shade.png
```
