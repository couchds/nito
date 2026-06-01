---
name: qwalk-gold-labeler
description: Create verified gold-standard QWalk quadruped guide skeleton labels for ML training from Blender meshes. Use when Codex needs to place, inspect, iteratively correct, or export perfect training labels for four-legged animal models, including horses, dogs, cats, turtles, lizards, giraffes, rams, and other quadrupeds in .blend files.
---

# QWalk Gold Labeler

## Objective

Produce only verified, training-eligible guide labels. A candidate guide is not ground truth. Iterate until every required view passes inspection, then export with `--verified`.

Use this workflow for any quadruped mesh in this repo. Prefer deterministic Blender scripts over ad hoc manual edits. Do not train on real labels unless their JSON has `verified_label: true`.

## Workflow

1. Identify the mesh object and animal-relative forward axis.
   - Use the axis from tail toward head: `POS_X`, `NEG_X`, `POS_Y`, or `NEG_Y`.
   - If there are multiple mesh objects, require or discover the exact mesh name before running fitting/export scripts.

2. Create a candidate guide-only blend.

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background INPUT.blend --python scripts\apply_qwalk_geometric_to_blend.py -- --mesh MESH_NAME --output LABEL_WORK.blend --guides-only --profile AUTO --mesh-forward-axis POS_X
```

3. Render a multi-view review set.

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background LABEL_WORK.blend --python scripts\render_qwalk_label_review.py -- --mesh MESH_NAME --guide GUIDE_NAME --out-dir data\real_quadrupeds\reviews\SAMPLE_ID --resolution 1200 --mesh-forward-axis POS_X
```

4. Inspect every rendered view using image viewing tools.
   - Required views: `left.png`, `right.png`, `front.png`, `rear.png`, `top.png`, `quarter.png`.
   - Read [review-checklist.md](references/review-checklist.md) when deciding if a label is good enough.
   - Treat a single failed view as a failed label.

5. Apply precise corrections with an edit JSON.

Use world-space edits when moving guide bones from Blender review coordinates:

```json
{
  "coordinate_space": "world",
  "guide_bones": {
    "qwg_guide_front_left_foot": {
      "tail": [1.23, -0.08, 0.03]
    }
  }
}
```

Then apply:

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background LABEL_WORK.blend --python scripts\apply_qwalk_guide_edits.py -- edits.json --guide GUIDE_NAME --output LABEL_WORK.blend
```

Use canonical edits only when editing a +Y-forward training JSON:

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background LABEL_WORK.blend --python scripts\apply_qwalk_guide_edits.py -- label.json --guide GUIDE_NAME --coordinate-space canonical --mesh-forward-axis POS_X --output LABEL_WORK.blend
```

6. Repeat review and correction.
   - Render new views after each meaningful edit.
   - Compare against the previous review directory.
   - Continue until the skeleton is correct from side, top, front/rear, and quarter views.

7. Export only after review passes.

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background LABEL_WORK.blend --python scripts\export_qwalk_guide_label.py -- --mesh MESH_NAME --guide GUIDE_NAME --out-dir data\real_quadrupeds --id SAMPLE_ID --split train --animal-type horse --morphology-type ungulate --source real_qwalk_label_gold --mesh-forward-axis POS_X --verified
```

8. Verify the export.
   - Confirm the JSON contains `verified_label: true` and `training_eligible: true`.
   - Confirm `manifest.jsonl` and `dataset_info.json` were updated.
   - Do not use `--allow-unverified-real` for training except for debugging.

## Strict Rules

- Never mark a label verified if any view is questionable.
- Never use generated candidate guides as training data without correction.
- Ignore tack, saddles, bridles, fur, manes, horns, shell ridges, and decorative accessories when placing bones.
- Keep guide bones inside the anatomical body/limb volume, not on the visual surface unless that is the intended QWalk guide landmark.
- Use side-view, top-view, and quarter-view evidence before deciding a guide is correct.
- Ask the user to inspect in Blender when visual ambiguity remains. Do not guess a verified label.

## Useful Scripts

- `scripts/apply_qwalk_geometric_to_blend.py`: create candidate editable guides from a mesh.
- `scripts/render_qwalk_label_review.py`: render multi-angle review images.
- `scripts/apply_qwalk_guide_edits.py`: apply exact guide coordinate corrections.
- `scripts/export_qwalk_guide_label.py`: export verified training OBJ/JSON labels.
- `scripts/train_guide_initializer.py`: trains only on verified real labels by default.
