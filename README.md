# Quadruped Walk Cycle Generator

A Blender add-on that generates looping walk-cycle keys for four-legged armatures. It can animate foot or paw IK target bones when the rig has them, or fall back to simple FK rotation on upper/lower/foot bone chains.

## Install

1. Zip the `quadruped_walk_cycle` folder, or keep the folder as-is for development.
2. In Blender, open `Edit > Preferences > Add-ons > Install...`.
3. Select the zip file or the `quadruped_walk_cycle/__init__.py` file.
4. Enable **Quadruped Walk Cycle Generator**.
5. Select an armature and open `View3D > Sidebar > QWalk`.

## Basic Use

1. Select the animal armature, or click **Create Quadruped Armature** to make a starter rig.
2. Click **Auto Map Bones** when using your own rig. The generated starter rig maps itself automatically.
3. Review the mapped fields. Auto mapping is best-effort because rigs use wildly different naming conventions.
4. Choose a gait: Compact Walk, Walk, Trot, Pace, or Bound.
5. Choose generation mode:
   - **Auto**: uses IK target bones where mapped, otherwise FK chains.
   - **IK Targets**: animates mapped foot or paw controls by location.
   - **FK Chains**: animates mapped upper, lower, and foot bones by Euler rotation.
6. Set stride, lift, frame range, and axes.
7. Click **Generate Walk Cycle**.

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

## Generated Starter Armature

Click **Create Quadruped Armature** to generate a simple +Y-forward, Z-up quadruped rig. The default display is **Stick**, which reads more like a rig than a blocky proxy animal. The operator has a **Profile** option; `Medium Quadruped` is the default, `Stocky Quadruped` is better for compact goat/sheep/ram-like bodies, and `Horse` provides a longer body, neck, and limb template.

The generated rig includes:

- `root`, `body`, `pelvis`, `chest`, `neck`, `head`, and tail bones
- Four named FK leg chains such as `front_left_upper`, `front_left_lower`, and `front_left_foot`
- Four IK targets such as `front_left_ik`
- Four pole controls such as `front_left_pole`
- Optional IK constraints from each lower-leg bone to its IK target

Hidden non-deforming shoulder/hip helper bones keep the limb chains parented cleanly without becoming part of the visible deformation skeleton.
IK and pole controls are created with their bone heads on the actual target points so Blender's IK solver does not pull the neutral pose away from the fitted skeleton. Generated foot controls are aligned to the rig's local axes, and walk-cycle location offsets are converted from armature space into each control bone's local channels before keying.
Generated IK constraints set a neutral pole angle so Pose Mode matches the fitted rest chain instead of twisting the leg as soon as constraints are added.

The starter armature is meant as a clean animation test rig and naming template, not a production-ready anatomy rig. Use Blender's operator redo panel after creation if you want a different profile or Octahedral, B-Bone, or Wire display instead.

New generated rigs open in Pose Mode with the main animation controls selected. The control widgets are stored as hidden mesh objects in a `*_widgets` collection and assigned as custom bone shapes.

## Mesh Fitting Guides

Select a mesh and click **Create Fitting Guides** to create an editable QWalk guide armature. This is the preferred fitting workflow:

1. Create fitting guides from the mesh.
2. Edit the guide bones in Blender Edit Mode until the skeleton landmarks sit where you want them.
3. Click **Generate Armature From Guides** to create the final QWalk rig.
4. Select the mesh, Shift-select the final QWalk rig so the rig is active, then click **Bind Selected Meshes To Rig**.
5. Generate the walk cycle on the final rig.

The guide initializer still estimates the ground, main torso span, upper back surface, foot contact areas, and broad body type. Those guesses are only a starting point. The final generated armature comes from the edited guide bones, which is more reliable than trying to infer hidden shoulder, hip, knee, and ankle positions from a surface mesh alone.

By default, **Generate Armature From Guides** mirrors each left/right leg pair from one side-profile while preserving the edited guide joint positions. When guides were created by this version, QWalk detects which overlaid side changed from the generated starting point; for older guides it uses the active left/right guide bone as a hint. This avoids crossed duplicate leg chains when fitting from side view. Disable **Mirror Leg Pairs** in the operator redo panel only when you intentionally want asymmetric left/right limb placement.

The sidebar button always runs with mirrored leg pairs and replacement enabled. In mirrored mode, guide landmarks define the body span, shoulder/hip placement, hoof contact, and visible joint bends. QWalk only adds a small fallback bend when a guide chain is nearly straight. After the rig is generated, QWalk also enforces matching side-profile coordinates on both front and rear leg pairs. The guide generator replaces older rigs generated from the same guide by default, which prevents stale `*_Rig.001` armatures from overlapping the newest rig and making the leg chains look unsymmetrical.

The guide armature is hidden by default after **Generate Armature From Guides** so the viewport shows the final rig cleanly. Unhide the guide object in the Outliner if you want to edit and regenerate.

When a guide armature is selected, the QWalk panel shows the active guide bone label, such as `Head`, `Neck`, or `Front Left Hoof`, so you can tell which landmark you are placing.

The older **Create Fitted Quadruped Armature** button still creates a direct one-shot fitted armature, but it is best treated as a quick draft rather than the main workflow.

Binding defaults to QWalk's nearest-bone weights, which creates real vertex groups and an Armature modifier without relying on Blender's heat weighting. The QWalk binder biases torso, head, and belly vertices away from accidental leg influence, keeps central underbody vertices on the body instead of a left or right leg, limits each vertex to a plausible leg column before blending, then prunes weak leftover weights that can make horns, mouths, loose belly fur, or the wrong leg follow the moving feet. Use the operator redo panel if you want to try Blender Automatic instead. For production results, expect to clean up vertex weights around shoulders, hips, hooves, horns, and dense fur.

## Synthetic ML Dataset

The `scripts/generate_synthetic_quadrupeds.py` script creates rough synthetic quadruped OBJ meshes with exact QWalk guide labels. This is intended as seed data for an ML guide initializer, not as finished animal artwork.

Generate a 1,000-sample starter dataset:

```powershell
python scripts/generate_synthetic_quadrupeds.py --count 1000 --out data/synthetic_quadrupeds
```

Each sample writes:

- an `.obj` proxy mesh
- a `.json` label file with QWalk guide bone head/tail coordinates
- `animal_type`, `morphology_type`, and mesh-space forward/left/up axes
- a root `manifest.jsonl` and `dataset_info.json`

Current synthetic animal types are horse, dog, cat, giraffe, turtle, lizard, and ram. The generated `data/synthetic_quadrupeds/` directory is ignored by Git so the repo keeps the generator without storing bulky training assets.

By default the generator applies a random yaw rotation to each sample so the eventual model cannot assume every animal faces +Y. For visual inspection, generate aligned samples with:

```powershell
python scripts/generate_synthetic_quadrupeds.py --count 20 --out data/synthetic_quadrupeds --no-random-yaw
```

OBJ files are mesh-only and do not contain Blender armatures. To inspect a sample with its labeled QWalk guide bones, run the Blender helper against the matching `.json` label file:

```powershell
blender --python scripts/import_synthetic_quadruped_sample.py -- data/synthetic_quadrupeds/train/syn_000000.json
```

The helper imports the OBJ mesh with `Forward=Y` and `Up=Z`, creates an editable QWalk guide armature from the JSON label coordinates, selects both objects, and stores the synthetic `animal_type` and `morphology_type` on the guide object. If you import raw OBJ files manually, use the same `Forward=Y` and `Up=Z` axis settings.

## Notes

- **Replace Keys** removes existing location/Euler rotation keys on mapped bones only inside the selected frame range.
- **Set Base Pose** stores the current mapped transforms as the neutral pose used by future generations.
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
- `ui.py`: QWalk sidebar panel
