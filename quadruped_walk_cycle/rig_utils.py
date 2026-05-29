from .constants import FK_FIELDS, IK_FIELDS, LEG_ORDER

BASE_LOCATION_PROP = "qwg_base_location"
BASE_ROTATION_PROP = "qwg_base_rotation_euler"
BASE_OBJECT_LOCATION_PROP = "qwg_base_object_location"
BASE_OBJECT_ROTATION_PROP = "qwg_base_object_rotation_euler"


def active_armature(context):
    """Return the active object when it is an armature."""
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    return None


def bone_exists(armature, name):
    """Return whether a pose bone exists on an armature."""
    return bool(name) and armature and armature.pose and name in armature.pose.bones


def pose_bone(armature, name):
    """Return a pose bone by name, or None when missing."""
    if bone_exists(armature, name):
        return armature.pose.bones[name]
    return None


def axis_items():
    """Return Blender enum items for signed local axes."""
    return (
        ("X", "X", ""),
        ("Y", "Y", ""),
        ("Z", "Z", ""),
        ("NEG_X", "-X", ""),
        ("NEG_Y", "-Y", ""),
        ("NEG_Z", "-Z", ""),
    )


def axis_index(axis):
    """Return the Euler/vector index for a signed axis name."""
    axis = axis.replace("NEG_", "")
    return {"X": 0, "Y": 1, "Z": 2}[axis]


def axis_sign(axis):
    """Return -1 for negative axes and 1 for positive axes."""
    return -1.0 if axis.startswith("NEG_") else 1.0


def axis_offset(forward_axis, forward, side_axis, side, up_axis, up):
    """Build an XYZ offset from forward, side, and up components."""
    values = [0.0, 0.0, 0.0]
    values[axis_index(forward_axis)] += forward * axis_sign(forward_axis)
    values[axis_index(side_axis)] += side * axis_sign(side_axis)
    values[axis_index(up_axis)] += up * axis_sign(up_axis)
    return values


def rotation_offset(base, axis_name, angle):
    """Return an Euler rotation with an added signed-axis angle."""
    result = base.copy()
    result[axis_index(axis_name)] += angle * axis_sign(axis_name)
    return result


def ensure_euler(pose_bone):
    """Switch a pose bone to XYZ Euler rotation when needed."""
    if pose_bone.rotation_mode in {"QUATERNION", "AXIS_ANGLE"}:
        pose_bone.rotation_mode = "XYZ"


def keyframe_pose_bone(pose_bone, frame, channels):
    """Insert keyframes for selected pose-bone channels."""
    for channel in channels:
        pose_bone.keyframe_insert(data_path=channel, frame=frame)


def bone_data_path(name, channel):
    """Return the action data path for a pose-bone channel."""
    return f'pose.bones["{name}"].{channel}'


def mapped_bones(settings):
    """Return all non-empty bone names referenced by the settings."""
    names = {settings.root_bone, settings.body_bone}
    for field in IK_FIELDS.values():
        names.add(getattr(settings, field))
    for fields in FK_FIELDS.values():
        for field in fields:
            names.add(getattr(settings, field))
    return {name for name in names if name}


def _values_as_list(values):
    """Return a plain float list for ID-property storage."""
    return [float(values[index]) for index in range(3)]


def _prop_or_current(owner, prop_name, current):
    """Return a stored vector-like property, creating it when missing."""
    if prop_name not in owner:
        owner[prop_name] = _values_as_list(current)
    return owner[prop_name]


def stored_location(owner, current):
    """Return the stored base location for an object or pose bone."""
    return current.__class__(_prop_or_current(owner, BASE_LOCATION_PROP, current))


def stored_rotation(owner, current):
    """Return the stored base Euler rotation for an object or pose bone."""
    return current.__class__(_prop_or_current(owner, BASE_ROTATION_PROP, current), current.order)


def stored_object_location(armature):
    """Return the stored base object location, creating it when missing."""
    if BASE_OBJECT_LOCATION_PROP not in armature:
        armature[BASE_OBJECT_LOCATION_PROP] = _values_as_list(armature.location)
    return armature.location.__class__(armature[BASE_OBJECT_LOCATION_PROP])


def stored_object_rotation(armature):
    """Return the stored base object rotation, creating it when missing."""
    if BASE_OBJECT_ROTATION_PROP not in armature:
        armature[BASE_OBJECT_ROTATION_PROP] = _values_as_list(armature.rotation_euler)
    return armature.rotation_euler.__class__(armature[BASE_OBJECT_ROTATION_PROP], armature.rotation_euler.order)


def store_base_pose(armature, bone_names=None):
    """Store the current object and mapped pose-bone transforms as the base pose."""
    armature[BASE_OBJECT_LOCATION_PROP] = _values_as_list(armature.location)
    armature[BASE_OBJECT_ROTATION_PROP] = _values_as_list(armature.rotation_euler)

    names = set(bone_names) if bone_names is not None else {bone.name for bone in armature.pose.bones}
    for name in names:
        bone = pose_bone(armature, name)
        if not bone:
            continue
        ensure_euler(bone)
        bone[BASE_LOCATION_PROP] = _values_as_list(bone.location)
        bone[BASE_ROTATION_PROP] = _values_as_list(bone.rotation_euler)


def action_fcurve_collections(action):
    """Yield F-curve collections for legacy and layered Blender actions."""
    if not action:
        return

    if hasattr(action, "fcurves"):
        yield action.fcurves
        return

    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                if hasattr(channelbag, "fcurves"):
                    yield channelbag.fcurves


def remove_keys_in_range(action, data_paths, frame_start, frame_end):
    """Remove keyframes from matching F-curves inside a frame range."""
    for fcurves in action_fcurve_collections(action):
        for fcurve in list(fcurves):
            if fcurve.data_path not in data_paths:
                continue

            for index in range(len(fcurve.keyframe_points) - 1, -1, -1):
                frame = fcurve.keyframe_points[index].co.x
                if frame_start <= frame <= frame_end:
                    fcurve.keyframe_points.remove(fcurve.keyframe_points[index], fast=True)

            if len(fcurve.keyframe_points) == 0:
                fcurves.remove(fcurve)
            else:
                fcurve.update()


def resolve_leg_modes(armature, settings):
    """Choose IK or FK generation for each mapped leg."""
    result = {}
    for leg in LEG_ORDER:
        ik_bone = getattr(settings, IK_FIELDS[leg])
        fk_bones = [getattr(settings, field) for field in FK_FIELDS[leg]]
        has_ik = bone_exists(armature, ik_bone)
        has_fk = all(bone_exists(armature, bone_name) for bone_name in fk_bones)

        if settings.generation_mode == "IK" and has_ik:
            result[leg] = "IK"
        elif settings.generation_mode == "FK" and has_fk:
            result[leg] = "FK"
        elif settings.generation_mode == "AUTO":
            if has_ik:
                result[leg] = "IK"
            elif has_fk:
                result[leg] = "FK"
    return result


def data_paths_for_cleanup(settings, mode_by_leg):
    """Return action data paths touched by the current mappings."""
    data_paths = {"location", "rotation_euler"}
    for name in (settings.root_bone, settings.body_bone):
        if name:
            data_paths.add(bone_data_path(name, "location"))
            data_paths.add(bone_data_path(name, "rotation_euler"))

    for leg, mode in mode_by_leg.items():
        if mode == "IK":
            name = getattr(settings, IK_FIELDS[leg])
            data_paths.add(bone_data_path(name, "location"))
        elif mode == "FK":
            for field in FK_FIELDS[leg]:
                name = getattr(settings, field)
                data_paths.add(bone_data_path(name, "rotation_euler"))
    return data_paths


def apply_interpolation_and_cycles(action, frame_start, frame_end, add_cycles, interpolation, data_paths):
    """Set interpolation and optional cycles on generated F-curves."""
    for fcurves in action_fcurve_collections(action):
        for fcurve in fcurves:
            if fcurve.data_path not in data_paths:
                continue

            for key in fcurve.keyframe_points:
                if frame_start <= key.co.x <= frame_end:
                    key.interpolation = interpolation

            if add_cycles:
                has_cycles = any(modifier.type == "CYCLES" for modifier in fcurve.modifiers)
                if not has_cycles:
                    modifier = fcurve.modifiers.new(type="CYCLES")
                    modifier.mode_before = "REPEAT"
                    modifier.mode_after = "REPEAT"
