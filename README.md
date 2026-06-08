# Nito

Nito is a local training-asset pipeline for quadruped characters. It helps create prompt-backed samples, generate multi-view reference art, turn those views into Tripo3D models, prepare the models for Blender skeleton placement, and collect verified labels for training a guide initializer that can place skeleton landmarks on new meshes.

The repo includes the Nito Blender Tools add-on for manual guide placement and rig checks. The Nito guide is the training label skeleton you edit by hand; the generated Nito preview rig is a temporary normal Blender armature created from that guide so you can bind the mesh, inspect Pose Mode, and run walk previews without changing the label source of truth.

## Nito Workflow

1. Create a sample from a prompt or from the quadruped prompt catalog.
2. Generate left, right, front, and back reference art with OpenAI image generation, passing earlier views into later views for consistency.
3. Submit the generated views to Tripo3D to create a 3D model.
4. Open the prepared Blender file and place or correct the skeleton guides manually.
5. Export verified labels for future model training.
6. Train and evaluate a guide initializer that predicts skeleton landmarks and animal/body-plan labels for unseen meshes.

## Blender Add-on

Use this section when you want to install the bundled Blender add-on directly, place a training guide, or preview how a generated quadruped rig would behave.

## Install

1. Zip the `quadruped_walk_cycle` folder, or keep the folder as-is for development.
2. In Blender, open `Edit > Preferences > Add-ons > Install...`.
3. Select the zip file or the `quadruped_walk_cycle/__init__.py` file.
4. Enable **Nito Blender Tools**.
5. Select a mesh, guide, or armature and open `View3D > Sidebar > Nito`.

## Basic Use

1. Select the animal mesh and click **Create Nito Guide**.
2. Edit the guide bones until the skeleton landmarks match the mesh.
3. Export the verified label when the guide is correct.
4. Optional: click **Preview + Bind From Guide** to create a temporary normal Blender armature, bind the selected mesh, and enter Pose Mode.
5. Use **Remap Bones** when using your own rig. Generated Nito preview rigs map themselves automatically.
6. Review the mapped fields. Auto mapping is best-effort because rigs use wildly different naming conventions.
7. Choose a gait: Compact Walk, Walk, Trot, Pace, or Bound.
8. Choose generation mode:
   - **Auto**: uses IK target bones where mapped, otherwise FK chains.
   - **IK Targets**: animates mapped foot or paw controls by location.
   - **FK Chains**: animates mapped upper, lower, and foot bones by Euler rotation.
9. Set stride, lift, frame range, and axes.
10. Click **Pose Test Walk**.

The add-on adds cyclic F-curve modifiers by default so the generated cycle loops past the selected frame range.

## Rig Expectations

For best results, use a rig with four foot or paw IK target/control bones:

- Front left IK
- Front right IK
- Rear left IK
- Rear right IK

If the rig does not have IK controls, map each leg as an FK chain:

- Upper bone
- Lower bone
- Foot/paw/hoof bone

The generator assumes one local axis is forward, one is side-to-side, and one is up. Defaults are:

- Forward: `Y`
- Side: `X`
- Up: `Z`

If the motion goes sideways, backwards, or downward, change the axis settings before regenerating.

## Generated Preview Rig

The preview rig is generated from an edited Nito guide. It is not a second annotation skeleton and should not require different landmark placement. If the preview rig bends badly, either the guide landmarks need correction or the guide-to-rig conversion needs improvement.

The generated preview rig includes:

- `root`, `body`, `pelvis`, `chest`, `neck`, `head`, and tail bones
- Four named FK leg chains such as `front_left_upper`, `front_left_lower`, and `front_left_foot`
- Four IK targets such as `front_left_ik`
- Four pole controls such as `front_left_pole`
- Optional IK constraints from each lower-leg bone to its IK target

Hidden non-deforming shoulder/hip helper bones keep the limb chains parented cleanly without becoming part of the visible deformation skeleton.
IK and pole controls are created with their bone heads on the actual target points so Blender's IK solver does not pull the neutral pose away from the fitted skeleton. Generated foot controls are aligned to the rig's local axes, and walk-cycle location offsets are converted from armature space into each control bone's local channels before keying.
Generated IK constraints set a neutral pole angle so Pose Mode matches the fitted rest chain instead of twisting the leg as soon as constraints are added.

The generated armature is meant as a clean animation preview and naming template, not a production-ready anatomy rig. Use Blender's operator redo panel after creation if you want a different profile or Octahedral, B-Bone, or Wire display instead.

New generated rigs open in Pose Mode with the main animation controls selected. The control widgets are stored as hidden mesh objects in a `*_widgets` collection and assigned as custom bone shapes.

Generated Nito preview rigs bake their mesh-alignment transform into the armature rest bones at creation time. The armature object stays at identity, so Object Mode, Pose Mode, and Edit Mode use the same visible skeleton placement.

## Nito Guides

Select a mesh and click **Create Nito Guide** to create an editable Nito guide armature. This is the preferred fitting workflow:

1. Create a Nito guide from the mesh.
2. Edit the guide bones in Blender Edit Mode until the skeleton landmarks sit where you want them.
3. Export the verified label from Nito when the guide placement is correct.
4. Optional: click **Preview Rig From Guide** to create a temporary Nito preview rig from the exact guide placement.
5. Optional: select the mesh and guide, then click **Preview + Bind From Guide** to bind the mesh and enter Pose Mode.
6. Use **Pose Test Walk** or Blender Pose Mode to check whether the preview rig bends the way you expect.

The **Preview + Bind From Guide** button combines preview-rig creation and mesh binding when a Nito guide and mesh are both selected.

The guide initializer still estimates the ground, main torso span, upper back surface, foot contact areas, and broad body type. Those guesses are only a starting point. The final training label comes from the edited guide bones, which is more reliable than trying to infer hidden shoulder, hip, knee, and ankle positions from a surface mesh alone.

By default, **Preview Rig From Guide** mirrors each left/right leg pair from one side-profile while preserving the edited guide joint positions. When guides were created by this version, Nito detects which overlaid side changed from the generated starting point; for older guides it uses the active left/right guide bone as a hint. This avoids crossed duplicate leg chains when fitting from side view. Disable **Mirror Leg Pairs** in the operator redo panel only when you intentionally want asymmetric left/right limb placement.

The sidebar button always runs with mirrored leg pairs and replacement enabled. In mirrored mode, guide landmarks define the body span, shoulder/hip placement, hoof contact, and visible joint bends. Nito only adds a small fallback bend when a guide chain is nearly straight. After the preview rig is generated, Nito also enforces matching side-profile coordinates on both front and rear leg pairs. The preview generator replaces older rigs generated from the same guide by default, which prevents stale `*_Rig.001` armatures from overlapping the newest rig and making the leg chains look unsymmetrical.

The guide armature is hidden by default after **Preview Rig From Guide** so the viewport shows the preview rig cleanly. Unhide the guide object in the Outliner if you want to edit and regenerate.

When a guide armature is selected, the Nito panel shows the active guide bone label, such as `Head`, `Neck`, or `Front Left Foot / Paw / Hoof`, so you can tell which landmark you are placing. It also shows short placement guidance in the sidebar and a **Placement Notes** dialog with head/tail instructions, anatomical landmarks, common mistakes, and the side-view mirroring note for leg bones.

The old starter/draft preview-rig operators are kept for development and debugging, but they are no longer part of the main sidebar workflow.

Binding defaults to Nito's nearest-bone weights, which creates real vertex groups and an Armature modifier without relying on Blender's heat weighting. The Nito binder biases torso, head, and belly vertices away from accidental leg influence, keeps central underbody vertices on the body instead of a left or right leg, limits each vertex to a plausible leg column before blending, then prunes weak leftover weights that can make horns, mouths, loose belly fur, or the wrong leg follow the moving feet. Use the operator redo panel if you want to try Blender Automatic instead. For production results, expect to clean up vertex weights around shoulders, hips, hooves, horns, and dense fur.

## Synthetic ML Dataset

The `scripts/generate_synthetic_quadrupeds.py` script creates rough synthetic quadruped OBJ meshes with exact Nito guide labels. This is intended as seed data for an ML guide initializer, not as finished animal artwork.

Generate a 1,000-sample starter dataset:

```powershell
python scripts/generate_synthetic_quadrupeds.py --count 1000 --out data/synthetic_quadrupeds
```

Each sample writes:

- an `.obj` proxy mesh
- a `.json` label file with Nito guide bone head/tail coordinates
- `animal_type`, `morphology_type`, and mesh-space forward/left/up axes
- a root `manifest.jsonl` and `dataset_info.json`

Current synthetic animal types are horse, dog, cat, giraffe, turtle, lizard, and ram. The generated `data/synthetic_quadrupeds/` directory is ignored by Git so the repo keeps the generator without storing bulky training assets.

By default generated samples are +Y-forward and Z-up. This is the preferred training setup because the predictor can rotate real meshes into the same canonical orientation before inference. To deliberately stress-test arbitrary yaw, opt in with `--random-yaw`:

```powershell
python scripts/generate_synthetic_quadrupeds.py --count 20 --out data/synthetic_quadrupeds --random-yaw
```

OBJ files are mesh-only and do not contain Blender armatures. To inspect a sample with its labeled Nito guide bones, run the Blender helper against the matching `.json` label file:

```powershell
blender --python scripts/import_synthetic_quadruped_sample.py -- data/synthetic_quadrupeds/train/syn_000000.json
```

The helper imports the OBJ mesh with `Forward=Y` and `Up=Z`, creates an editable Nito guide armature from the JSON label coordinates, selects both objects, and stores the synthetic `animal_type` and `morphology_type` on the guide object. If you import raw OBJ files manually, use the same `Forward=Y` and `Up=Z` axis settings.

Train a first PointNet-style guide initializer from the synthetic dataset:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch numpy
.\.venv\Scripts\python.exe scripts/train_guide_initializer.py --data data/synthetic_quadrupeds --epochs 40
```

The trainer samples point clouds from the OBJ meshes, predicts the 23 guide points needed to reconstruct the Nito guide bones, and uses `animal_type` plus `morphology_type` as auxiliary classification tasks. Training artifacts are written under `models/qwalk_guide_initializer/`, including `qwalk_guide_initializer.pt`, `metrics.json`, and a small `test_predictions_preview.jsonl`.

Real labels are treated as ground truth and are only loaded from `--real-data` when their JSON has `verified_label: true`. Use `scripts/export_qwalk_guide_label.py --verified` only after the guide placement has been visually reviewed and corrected in Blender. Candidate labels can still be tested with `--allow-unverified-real`, but they should not be used for model training.

For repeatable real-label creation, use the repo-local Codex skill at `skills/qwalk-gold-labeler/SKILL.md`. It defines the gold-label loop: create a candidate guide, render side/front/rear/top/quarter review images with `scripts/render_qwalk_label_review.py`, apply exact coordinate corrections with `scripts/apply_qwalk_guide_edits.py`, repeat until every view passes, then export with `--verified`.

## Nito Training Asset Workflow

The `scripts/automated_training_workflow.py` script scaffolds Nito's end-to-end real-data pipeline:

1. Create one or more catalog-backed sample specs.
2. Generate left/right/front/back reference art with OpenAI `gpt-image-2`, using earlier views as image references for later views.
3. Submit a multiview-to-model task to Tripo3D from those generated views.
4. Poll and download the generated model before Tripo result URLs expire.
5. Import the model into Blender.
6. Create a candidate Nito guide and render multi-view review images.
7. Use `skills/qwalk-gold-labeler/SKILL.md` to iterate until the label is perfect.
8. Export a verified real training label.

Sample prompts live in `prompts/quadruped_reference_prompts.json`. The catalog stores body plan, optional animal type metadata, variant tags, armor state, mesh axis defaults, and the per-view prompt template used for OpenAI reference generation. Body plan is still stored as `morphology_type` in workflow and training data for compatibility with the current trainer, but conceptually it should answer "what skeleton placement family is this?" rather than "what species is this?". The same catalog maps each body plan to a `skeleton_schema_id`; the skeleton schema defines the shared bone graph and chain order for that rig family, while individual joint placement is still corrected per mesh in Blender. Generated workflow state is written under `data/automated_training/`, which is ignored by Git.

```powershell
Copy-Item .env.example .env.local
# Edit .env.local and set OPENAI_API_KEY and TRIPO_API_KEY. .env.local is ignored by Git.

.\.venv\Scripts\python.exe scripts\automated_training_workflow.py init-batch `
  --count 4 `
  --sample-prefix nito `
  --seed 42

$sampleId = "paste_created_sample_id_here"
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py generate-reference --sample-id $sampleId

.\.venv\Scripts\python.exe scripts\automated_training_workflow.py submit-tripo --sample-id $sampleId --face-limit 5000
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py poll-tripo --sample-id $sampleId
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py prepare-label-work --sample-id $sampleId --profile AUTO
```

`init-batch` samples from the prompt catalog and creates resumable per-sample state. Use `--animal-type dog` or `--armor-state armored` to restrict the random choices. The sample IDs include the current timestamp; copy the actual IDs from command output.

`generate-reference` uses sequential model-sheet generation by default. It generates the left profile from text, generates the right profile from the left image, generates the front view from the left and right images, then generates the back view from the previous three images. The resulting `front`, `left`, `right`, and `back` images are stored under the sample's `reference/` directory. By default it uses the catalog image settings, currently `gpt-image-2`, `1024x1024`, `medium`, opaque PNG output. Use `--reference-strategy independent` when you want separate text-only generations for debugging.

`submit-tripo` uploads the generated OpenAI view images to Tripo3D and submits `multiview_to_model` in Tripo's required order: front, left, back, right. The `--face-limit` value can be randomized by callers; values from 3000 to 8000 are the intended training range.

For local batch generation, use `run-batch`. It creates `N` catalog-backed samples, generates OpenAI reference views, submits each model to Tripo3D with a random `--face-limit` between 3000 and 8000, polls/downloads the result, and writes a batch summary under `data/automated_training/batch_runs/`.

```powershell
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py run-batch `
  --count 8 `
  --sample-prefix nito `
  --seed 42
```

Add `--prepare-label-work` to immediately import each downloaded model into Blender, create candidate Nito guides, and render review images for manual correction. Use `--dry-run` to create local sample state and print the planned random face counts without calling OpenAI or Tripo3D.

Start Nito when you want a dashboard over the same batch runner:

```powershell
.\.venv\Scripts\python.exe scripts\qwalk_ui_server.py
```

Then open `http://127.0.0.1:8765`. The Home page shows actively running UI jobs and samples that have not reached the verified training-export state yet. Nito uses route-backed pages for `/samples`, `/samples/<sample_id>`, `/batches`, `/batches/<run_id>`, `/create`, `/jobs`, and `/settings`, so detail pages can be opened directly.

Use the Create page to make a prompt-backed sample with a two-step flow: enter the character prompt, then choose the skeleton/body type from the visual cards. Creating a sample immediately starts the automatic machine pipeline: sequential OpenAI reference views, Tripo generation, model download, and Blender label-file prep. Nito then pauses for the only manual step: opening the prepared Blender file and placing/correcting the skeleton guide. The original prompt and generated front/left/right/back OpenAI prompts are stored in the sample workflow state. Each sample detail page shows the expected rig family, bone chains, an anatomical placement diagram, placement guidance for the guide bones, pipeline state, reference images, Blender review renders, and downloaded GLB/GLTF model when those artifacts exist. After a verified label is exported, the 3D viewport adds a **Skeleton** toggle and loads the exported canonical OBJ label mesh so the overlay matches the Blender label-work coordinate frame. Batches remain candidate training sets, and a sample can appear in multiple batches because membership is computed from saved batch summaries.

Tripo submission uses the saved OpenAI reference images directly. `submit-tripo` uploads the local `front`, `left`, `right`, and `back` files, sends them to Tripo in the required `front`, `left`, `back`, `right` order, and stores the returned model task id in the sample workflow state.

Blender label-work files are normalized to a canonical frame before guide fitting: +Z is up, +Y points from tail toward head, the mesh is centered on the origin, and the lowest point rests on Z=0. If the generated model imports with a different head-to-tail axis than the reference image implied, rerun only the Blender label/review stage with `--mesh-forward-axis` set to the imported model's current tail-to-head axis:

```powershell
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py prepare-label-work --sample-id auto_horse_000 --profile HORSE --mesh-forward-axis POS_X
```

After the review images pass the gold-label skill checklist, export the corrected guide from the sample page with **Export Verified Label**, or run the same step from PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\automated_training_workflow.py export-verified --sample-id auto_horse_000 --verified
```

Omit `--verified` to export a candidate label that remains blocked from training.

Predict guide bones for an OBJ mesh:

```powershell
.\.venv\Scripts\python.exe scripts/predict_guide_initializer.py data/synthetic_quadrupeds/train/syn_000007.obj --checkpoint models/qwalk_guide_initializer/qwalk_guide_initializer.pt --mesh-forward-axis AUTO
```

This writes a sibling `*.qwalk_prediction.json` file with predicted guide points, reconstructed Nito guide bones, animal probabilities, and morphology probabilities. The predictor rotates the mesh into +Y-forward canonical space before inference, then rotates predictions back. `AUTO` uses the dominant horizontal extent; pass `POS_X`, `NEG_X`, `POS_Y`, or `NEG_Y` when you know the true tail-to-head axis. The predictor also applies a small postprocess pass by default to mirror leg pairs, keep centerline bones centered, ground the feet, and keep limb joints above the ground plane.

Evaluate a saved checkpoint:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_guide_initializer.py --data data/synthetic_quadrupeds --checkpoint models/qwalk_guide_initializer/qwalk_guide_initializer.pt --split test
```

Import the prediction into Blender as an editable guide armature:

```powershell
& "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe" --python scripts/import_synthetic_quadruped_sample.py -- data/synthetic_quadrupeds/train/syn_000007.qwalk_prediction.json
```

If Blender is on your `PATH`, `blender --python ...` works too. The same import helper accepts both synthetic label JSON files and prediction JSON files.

## Notes

- **Replace Keys** removes existing location/Euler rotation keys on mapped bones only inside the selected frame range.
- **Store Current Pose As Base** stores the current mapped transforms as the neutral pose used by future generations.
- IK walk motion is clamped per leg from the rest chain length so compact fitted rigs are not overdriven by the default stride and lift values.
- **Compact Walk** is the default for goat, sheep, ram, and other stocky rigs. It uses a grounded four-beat order, shorter rear reach, lower foot lift, and reduced body bob compared with the generic walk.
- Generated IK constraints use target rotation so hoof/end-effector bones stay more controlled instead of freely twisting through the IK solve.
- IK mode only moves target/control bones. Your rig's IK constraints still determine the final limb bending.
- FK mode is intentionally generic. It gives a usable blocking pass, but animal-specific polish usually still needs animator cleanup.
- `FK Swing`, `FK Lift`, and `FK Bend` only apply when the current mode resolves to FK. The panel disables them when the mapped rig is using IK.
- The first and last frames are keyed to match, making the cycle loop cleanly.

## Package Layout

Blender loads the add-on from `quadruped_walk_cycle/__init__.py`, while the implementation is split into focused modules:

- `constants.py`: leg labels and property field names
- `gaits.py`: gait presets and stride math
- `bone_mapping.py`: best-effort bone-name detection
- `rig_utils.py`: armature, axis, keyframe, and F-curve helpers
- `skeleton.py`: starter quadruped armature generation
- `properties.py`: Blender scene settings
- `operators.py`: auto-map, generate, and clear operators
- `ui.py`: Nito sidebar panel
