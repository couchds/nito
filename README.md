# Quadruped Walk Cycle Generator

A Blender add-on that generates looping walk-cycle keys for four-legged armatures. It can animate foot or paw IK target bones when the rig has them, or fall back to simple FK rotation on upper/lower/foot bone chains.

## Install

1. Zip the `quadruped_walk_cycle` folder, or keep the folder as-is for development.
2. In Blender, open `Edit > Preferences > Add-ons > Install...`.
3. Select the zip file or the `quadruped_walk_cycle/__init__.py` file.
4. Enable **Quadruped Walk Cycle Generator**.
5. Select an armature and open `View3D > Sidebar > QWalk`.

## Basic Use

1. Select the animal armature.
2. Click **Auto Map Bones**.
3. Review the mapped fields. Auto mapping is best-effort because rigs use wildly different naming conventions.
4. Choose a gait: Walk, Trot, Pace, or Bound.
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

## Notes

- **Replace Keys** removes existing location/Euler rotation keys on mapped bones only inside the selected frame range.
- IK mode only moves target/control bones. Your rig's IK constraints still determine the final limb bending.
- FK mode is intentionally generic. It gives a usable blocking pass, but animal-specific polish usually still needs animator cleanup.
- The first and last frames are keyed to match, making the cycle loop cleanly.

## Package Layout

Blender loads the add-on from `quadruped_walk_cycle/__init__.py`, while the implementation is split into focused modules:

- `constants.py`: leg labels and property field names
- `gaits.py`: gait presets and stride math
- `bone_mapping.py`: best-effort bone-name detection
- `rig_utils.py`: armature, axis, keyframe, and F-curve helpers
- `properties.py`: Blender scene settings
- `operators.py`: auto-map, generate, and clear operators
- `ui.py`: QWalk sidebar panel
