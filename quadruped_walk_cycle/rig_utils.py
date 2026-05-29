from .constants import FK_FIELDS, IK_FIELDS, LEG_ORDER


def active_armature(context):
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    return None


def bone_exists(armature, name):
    return bool(name) and armature and armature.pose and name in armature.pose.bones


def pose_bone(armature, name):
    if bone_exists(armature, name):
        return armature.pose.bones[name]
    return None


def axis_items():
    return (
        ("X", "X", ""),
        ("Y", "Y", ""),
        ("Z", "Z", ""),
        ("NEG_X", "-X", ""),
        ("NEG_Y", "-Y", ""),
        ("NEG_Z", "-Z", ""),
    )


def axis_index(axis):
    axis = axis.replace("NEG_", "")
    return {"X": 0, "Y": 1, "Z": 2}[axis]


def axis_sign(axis):
    return -1.0 if axis.startswith("NEG_") else 1.0


def axis_offset(forward_axis, forward, side_axis, side, up_axis, up):
    values = [0.0, 0.0, 0.0]
    values[axis_index(forward_axis)] += forward * axis_sign(forward_axis)
    values[axis_index(side_axis)] += side * axis_sign(side_axis)
    values[axis_index(up_axis)] += up * axis_sign(up_axis)
    return values


def rotation_offset(base, axis_name, angle):
    result = base.copy()
    result[axis_index(axis_name)] += angle * axis_sign(axis_name)
    return result


def ensure_euler(pose_bone):
    if pose_bone.rotation_mode in {"QUATERNION", "AXIS_ANGLE"}:
        pose_bone.rotation_mode = "XYZ"


def keyframe_pose_bone(pose_bone, frame, channels):
    for channel in channels:
        pose_bone.keyframe_insert(data_path=channel, frame=frame)


def bone_data_path(name, channel):
    return f'pose.bones["{name}"].{channel}'


def mapped_bones(settings):
    names = {settings.root_bone, settings.body_bone}
    for field in IK_FIELDS.values():
        names.add(getattr(settings, field))
    for fields in FK_FIELDS.values():
        for field in fields:
            names.add(getattr(settings, field))
    return {name for name in names if name}


def remove_keys_in_range(action, data_paths, frame_start, frame_end):
    if not action:
        return
    for fcurve in list(action.fcurves):
        if fcurve.data_path not in data_paths:
            continue

        for index in range(len(fcurve.keyframe_points) - 1, -1, -1):
            frame = fcurve.keyframe_points[index].co.x
            if frame_start <= frame <= frame_end:
                fcurve.keyframe_points.remove(fcurve.keyframe_points[index], fast=True)

        if len(fcurve.keyframe_points) == 0:
            action.fcurves.remove(fcurve)
        else:
            fcurve.update()


def resolve_leg_modes(armature, settings):
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
    if not action:
        return

    for fcurve in action.fcurves:
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
