# QWalk Anatomical Landmarks

Use this reference when placing QWalk guide bones manually. These are guide skeleton landmarks for training, not a complete production rig.

## Centerline

- `qwg_guide_pelvis`: starts near the hip/root of the torso and ends forward along the back-body centerline. Do not start it in tail fur.
- `qwg_guide_spine`: continues through the torso midline, usually just below the visible top silhouette so it sits inside body volume.
- `qwg_guide_chest`: ends around the chest/withers/shoulder mass, not in the throat fur.
- `qwg_guide_neck`: follows the neck volume from chest/withers toward the skull base.
- `qwg_guide_head`: runs through the skull/muzzle volume. Avoid ears, horns, mane, beard, bridle, and loose fur.
- `qwg_guide_tail`: starts at the anatomical tail base. Its tail point follows the tail root direction, not the full decorative tail mass unless that is the body tail.

## Digitigrade Canids And Cats

Use for dogs, wolves, fox-like meshes, cats, and similar digitigrade animals.

- Front upper head: shoulder/scapula mass, high and slightly behind the visible front leg column.
- Front upper tail: elbow area, behind and below the shoulder, inside the upper foreleg.
- Front lower tail: wrist/carpus area, low on the foreleg above the paw.
- Front foot tail: paw/toe contact area. Put it inside the paw footprint, not at the fur fringe.
- Rear upper head: hip/haunch mass, high in the rear body volume.
- Rear upper tail: stifle/knee area, forward and below the hip inside the thigh.
- Rear lower tail: hock/ankle area, back and low, where the hind leg sharply changes angle.
- Rear foot tail: hind paw/toe contact area. It should be under the visible hind paw, not pulled under the belly.

Digitigrade rear legs normally have a clear zig-zag: hip to stifle forward/down, stifle to hock back/down, hock to paw forward/down. Do not force the rear leg into a horse-like vertical column.

## Ungulates

Use for horses, rams, deer-like meshes, giraffes, and similar hoofed animals.

- Front limb is comparatively columnar: shoulder/scapula high, elbow behind the upper foreleg, knee/carpus above cannon bone, hoof at ground contact.
- Rear limb still bends: hip high in haunch, stifle forward/down, hock back/down, hoof at ground contact.
- Feet should land in hoof volume. Ignore feathering/fur around hooves.

## Low And Sprawled Bodies

Use for lizards, turtles, and other sprawled forms.

- Centerline follows torso/shell midline, not shell decorations.
- Limb chains may project sideways before reaching the foot contact. Top view matters as much as side view.
- For turtles, shell surface is not the spine; place the guide through the body volume under the shell.

## Common Failure Patterns

- Head/tail swapped: `qwg_guide_head` appears near tail fur or `qwg_guide_tail` appears near skull.
- Paw endpoint drift: foot tail is correct in side silhouette but outside the paw footprint in top/front view.
- Belly pull: rear foot tail is pulled under the belly instead of the visible hind paw.
- Surface tracing: centerline rides the top fur/crest instead of passing through body volume.
- Accessory attraction: points snap to saddle, bridle, horns, shell ridges, mane, beard, or decorative fur.
