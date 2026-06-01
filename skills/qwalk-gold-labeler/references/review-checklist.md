# QWalk Gold Label Review Checklist

Use this checklist before exporting a real quadruped label with `--verified`.

## Required Views

Pass all views from `scripts/render_qwalk_label_review.py`:

- `left.png` and `right.png`: side-profile joint placement and ground contact.
- `front.png` and `rear.png`: left/right limb width, symmetry, and vertical alignment.
- `top.png`: centerline, paired limb spacing, and forward-axis correctness.
- `quarter.png`: depth placement and whether bones sit inside the mesh volume.

## Centerline

- Pelvis starts near the hip/root of the torso, not inside the tail hair or decorative geometry.
- Spine and chest form a smooth chain through the intended QWalk body guide line.
- Neck starts from the chest/withers area and follows the neck volume, not the mane or bridle.
- Head guide ends in the head/skull volume, not on tack or an ear/horn.
- Tail guide starts at the pelvis/tail root and follows the actual tail base direction.

## Legs

- Front upper guide starts near the shoulder/scapula mass, not in the lower chest or bridle.
- Front mid/lower/foot points follow elbow, wrist/knee, and hoof/foot contact in the visible limb.
- Rear upper guide starts in the haunch/hip area, not too low on the thigh surface.
- Rear mid/lower/foot points follow stifle, hock, and hoof/foot contact.
- Feet sit on the ground/contact plane and inside the actual hoof or paw footprint.
- Limb chains should not cross outside the limb silhouette in side view.

## Width And Symmetry

- Top view shows the torso centerline on the mesh midline.
- Left/right limb pairs are laterally symmetric unless the mesh pose is intentionally asymmetric.
- Front and rear leg widths sit inside the real leg volumes, not outside fur/accessories.
- No bone endpoints should drift into saddle, shell decoration, hair, horns, reins, or other non-body geometry.

## Failure Conditions

Reject the label when any of these are true:

- A point is correct in side view but clearly wrong in top/front/rear view.
- A guide follows the visual outline instead of the anatomical guide location.
- The skeleton depends on accessories or stylized surface details.
- Any endpoint is guessed because the mesh occludes the landmark.
- The label would teach the model an obviously wrong joint position.

When in doubt, keep `verified_label: false` and ask for a Blender-side inspection.
