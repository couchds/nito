import math

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator

from .bone_mapping import find_best_bone
from .constants import FK_FIELDS, IK_FIELDS, LEG_ORDER
from .gaits import GAITS, cycle_position, leg_motion
from .rig_utils import (
    active_armature,
    apply_interpolation_and_cycles,
    axis_index,
    axis_offset,
    axis_sign,
    bone_exists,
    data_paths_for_cleanup,
    ensure_euler,
    keyframe_pose_bone,
    mapped_bones,
    pose_location_for_armature_offset,
    pose_bone,
    remove_keys_in_range,
    resolve_leg_modes,
    rotation_offset,
    store_base_pose,
    stored_location,
    stored_object_location,
    stored_object_rotation,
    stored_rotation,
)


LEG_BONE_PREFIXES = ("front_left_", "front_right_", "rear_left_", "rear_right_")
TORSO_BONE_NAMES = {"pelvis", "spine_01", "chest"}
TAIL_BONE_NAMES = {"tail_01", "tail_02"}


class QWG_OT_auto_map(Operator):
    bl_idname = "qwg.auto_map"
    bl_label = "Auto Map Bones"
    bl_description = "Try to fill quadruped bone fields from the selected armature's bone names"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Enable the operator only when an armature is selected."""
        return active_armature(context) is not None

    def execute(self, context):
        """Populate bone mapping fields from the selected armature."""
        armature = active_armature(context)
        settings = context.scene.qwg_settings
        names = [bone.name for bone in armature.pose.bones]

        settings.root_bone = find_best_bone(names, kind="root", minimum=6)
        settings.body_bone = find_best_bone(names, kind="body", minimum=6)

        for leg in LEG_ORDER:
            setattr(settings, IK_FIELDS[leg], find_best_bone(names, leg=leg, kind="ik", minimum=10))
            upper, lower, foot = FK_FIELDS[leg]
            setattr(settings, upper, find_best_bone(names, leg=leg, kind="upper", minimum=10))
            setattr(settings, lower, find_best_bone(names, leg=leg, kind="lower", minimum=10))
            setattr(settings, foot, find_best_bone(names, leg=leg, kind="foot", minimum=10))

        self.report({"INFO"}, "Auto-mapping complete. Review fields before generating.")
        return {"FINISHED"}


class QWG_OT_bind_selected_meshes(Operator):
    bl_idname = "qwg.bind_selected_meshes"
    bl_label = "Bind Selected Meshes To Rig"
    bl_description = "Bind selected mesh objects to the active QWalk armature"
    bl_options = {"REGISTER", "UNDO"}

    weighting_mode: EnumProperty(
        name="Weights",
        description="How vertex weights are assigned during binding",
        items=(
            ("NEAREST", "Nearest Bones", "Assign robust QWalk weights from nearest deform bones"),
            ("AUTOMATIC", "Blender Automatic", "Use Blender's automatic heat weighting"),
        ),
        default="NEAREST",
    )
    replace_existing_armatures: BoolProperty(
        name="Replace Armature Modifiers",
        description="Remove existing Armature modifiers before binding to this rig",
        default=True,
    )
    max_influences: IntProperty(
        name="Max Influences",
        description="Maximum deform bones assigned to each vertex for nearest-bone weights",
        default=4,
        min=1,
        max=8,
    )

    @classmethod
    def poll(cls, context):
        """Enable when an armature is active and at least one mesh is selected."""
        return active_armature(context) is not None and any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        """Parent selected meshes to the active armature and create skin weights."""
        armature = active_armature(context)
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not armature or not meshes:
            self.report({"ERROR"}, "Select mesh object(s), then Shift-select the QWalk rig so it is active.")
            return {"CANCELLED"}
        if armature.get("qwg_is_guide"):
            self.report({"ERROR"}, "Bind to the generated QWalk rig, not the guide armature.")
            return {"CANCELLED"}

        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bound_count = 0
        for mesh in meshes:
            if self.replace_existing_armatures:
                remove_armature_modifiers(mesh)

            if self.weighting_mode == "AUTOMATIC":
                if bind_with_automatic_weights(context, mesh, armature):
                    bound_count += 1
                else:
                    self.report({"WARNING"}, f"Automatic weights failed for {mesh.name}.")
            else:
                try:
                    bind_with_nearest_bone_weights(mesh, armature, self.max_influences)
                    bound_count += 1
                except RuntimeError as error:
                    self.report({"ERROR"}, f"Nearest weights failed for {mesh.name}: {error}")

        bpy.ops.object.select_all(action="DESELECT")
        for mesh in meshes:
            mesh.select_set(True)
        armature.select_set(True)
        context.view_layer.objects.active = armature

        if bound_count == 0:
            return {"CANCELLED"}

        self.report({"INFO"}, f"Bound {bound_count} mesh object(s) to {armature.name}.")
        return {"FINISHED"}


def bind_with_automatic_weights(context, mesh, armature):
    """Bind one mesh to an armature using Blender automatic weights."""
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    armature.select_set(True)
    context.view_layer.objects.active = armature

    try:
        return bpy.ops.object.parent_set(type="ARMATURE_AUTO") == {"FINISHED"}
    except RuntimeError:
        return False


def remove_armature_modifiers(mesh):
    """Remove existing armature modifiers from a mesh."""
    for modifier in list(mesh.modifiers):
        if modifier.type == "ARMATURE":
            mesh.modifiers.remove(modifier)


def ensure_armature_modifier(mesh, armature):
    """Create or update the QWalk armature modifier."""
    modifier = mesh.modifiers.get("QWalk Armature")
    if not modifier:
        modifier = mesh.modifiers.new("QWalk Armature", "ARMATURE")
    modifier.object = armature
    modifier.show_viewport = True
    modifier.show_render = True
    return modifier


def deform_bone_segments(armature):
    """Return usable deform bone line segments in armature local space."""
    segments = []
    for bone in armature.data.bones:
        if not bone.use_deform:
            continue
        if bone.name.endswith("_foot"):
            continue
        head = bone.head_local.copy()
        tail = bone.tail_local.copy()
        if (tail - head).length <= 0.0001:
            continue
        segments.append((bone.name, head, tail))
    return segments


def distance_to_segment(point, start, end):
    """Return distance from a point to a finite line segment."""
    segment = end - start
    length_sq = segment.length_squared
    if length_sq <= 0.000001:
        return (point - start).length
    amount = max(0.0, min(1.0, (point - start).dot(segment) / length_sq))
    closest = start + segment * amount
    return (point - closest).length


def leg_prefix(name):
    """Return the QWalk leg prefix for a bone name, or None for non-leg bones."""
    for prefix in LEG_BONE_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


def binding_metrics(segments):
    """Return rig-space landmarks used to keep body vertices off animated legs."""
    points = [point for _, head, tail in segments for point in (head, tail)]
    if not points:
        return {}

    ground_z = min(point.z for point in points)
    height = max(max(point.z for point in points) - ground_z, 0.001)
    leg_boxes = {}
    torso_points = []

    for name, head, tail in segments:
        prefix = leg_prefix(name)
        if prefix:
            box = leg_boxes.setdefault(prefix, {"xs": [], "ys": [], "zs": []})
            box["xs"].extend((head.x, tail.x))
            box["ys"].extend((head.y, tail.y))
            box["zs"].extend((head.z, tail.z))
        elif name in TORSO_BONE_NAMES:
            torso_points.extend((head, tail))

    tail_points = [
        point
        for name, head, tail in segments
        if name in TAIL_BONE_NAMES
        for point in (head, tail)
    ]

    for prefix, box in list(leg_boxes.items()):
        leg_boxes[prefix] = {
            "min_x": min(box["xs"]),
            "max_x": max(box["xs"]),
            "min_y": min(box["ys"]),
            "max_y": max(box["ys"]),
            "min_z": min(box["zs"]),
            "max_z": max(box["zs"]),
            "center_x": (min(box["xs"]) + max(box["xs"])) * 0.5,
            "center_y": (min(box["ys"]) + max(box["ys"])) * 0.5,
        }

    body_box = None
    midline_x = sum(point.x for point in points) / len(points)
    if torso_points:
        midline_x = sum(point.x for point in torso_points) / len(torso_points)
        body_box = {
            "min_y": min(point.y for point in torso_points),
            "max_y": max(point.y for point in torso_points),
        }
    leg_side_distances = [abs(box["center_x"] - midline_x) for box in leg_boxes.values()]

    tail_box = None
    if tail_points:
        tail_box = {
            "min_x": min(point.x for point in tail_points),
            "max_x": max(point.x for point in tail_points),
            "min_y": min(point.y for point in tail_points),
            "max_y": max(point.y for point in tail_points),
            "min_z": min(point.z for point in tail_points),
            "max_z": max(point.z for point in tail_points),
        }

    return {
        "body_box": body_box,
        "ground_z": ground_z,
        "height": height,
        "leg_boxes": leg_boxes,
        "midline_x": midline_x,
        "min_leg_side_distance": min(leg_side_distances) if leg_side_distances else 0.0,
        "tail_box": tail_box,
    }


def in_body_band(point, metrics):
    """Return whether a point sits in the main torso span."""
    body_box = metrics.get("body_box")
    if not body_box:
        return False

    height = metrics.get("height", 1.0)
    pad_y = max(height * 0.06, 0.04)
    belly_floor = metrics.get("ground_z", 0.0) + height * 0.12
    return (
        body_box["min_y"] - pad_y <= point.y <= body_box["max_y"] + pad_y
        and point.z >= belly_floor
    )


def in_torso_span(point, metrics):
    """Return whether a point sits between the main pelvis and chest landmarks."""
    body_box = metrics.get("body_box")
    if not body_box:
        return False

    height = metrics.get("height", 1.0)
    pad_y = max(height * 0.08, 0.05)
    return body_box["min_y"] - pad_y <= point.y <= body_box["max_y"] + pad_y


def in_midline_torso(point, metrics):
    """Return whether a point is central enough to prefer body weights over leg weights."""
    side_distance = metrics.get("min_leg_side_distance", 0.0)
    if side_distance <= 0.0 or not in_torso_span(point, metrics):
        return False
    return abs(point.x - metrics.get("midline_x", 0.0)) <= side_distance * 0.58


def closest_leg_prefix(point, metrics):
    """Return the closest plausible leg column for a point."""
    if in_midline_torso(point, metrics):
        return None

    height = metrics.get("height", 1.0)
    pad_x = max(height * 0.08, 0.04)
    pad_y = max(height * 0.10, 0.05)
    pad_z = max(height * 0.10, 0.05)
    best_prefix = None
    best_score = None

    for prefix, box in metrics.get("leg_boxes", {}).items():
        if point.z > box["max_z"] + pad_z:
            continue

        x_gap = max(box["min_x"] - pad_x - point.x, point.x - box["max_x"] - pad_x, 0.0)
        y_gap = max(box["min_y"] - pad_y - point.y, point.y - box["max_y"] - pad_y, 0.0)
        z_gap = max(box["min_z"] - pad_z - point.z, 0.0)
        if y_gap > height * 0.22 or x_gap > height * 0.18:
            continue

        center_bias = abs(point.x - box["center_x"]) * 0.25 + abs(point.y - box["center_y"]) * 0.10
        score = x_gap * 1.5 + y_gap + z_gap * 0.5 + center_bias
        if best_score is None or score < best_score:
            best_prefix = prefix
            best_score = score

    return best_prefix


def in_tail_region(point, metrics):
    """Return whether a point is likely centered tail geometry behind the pelvis."""
    body_box = metrics.get("body_box")
    tail_box = metrics.get("tail_box")
    if not body_box or not tail_box:
        return False

    height = metrics.get("height", 1.0)
    side_distance = metrics.get("min_leg_side_distance", 0.0)
    x_pad = max(side_distance * 0.62, height * 0.10, 0.05)
    y_pad = max(height * 0.16, 0.06)
    z_pad = max(height * 0.24, 0.08)
    return (
        point.y <= body_box["min_y"] + y_pad
        and abs(point.x - metrics.get("midline_x", 0.0)) <= x_pad
        and point.z <= tail_box["max_z"] + z_pad
    )


def filtered_binding_distances(point, raw_distances, closest_body_distance, metrics):
    """Limit candidate bones before distance biasing and weight normalization."""
    if in_tail_region(point, metrics):
        allowed = [
            (distance, segment)
            for distance, segment in raw_distances
            if segment[0] in TAIL_BONE_NAMES or segment[0] == "pelvis"
        ]
        return allowed or raw_distances

    assigned_leg = closest_leg_prefix(point, metrics)
    if assigned_leg:
        box = metrics.get("leg_boxes", {}).get(assigned_leg, {})
        height = metrics.get("height", 1.0)
        upper_blend_z = box.get("max_z", point.z) - height * 0.18
        allowed = []
        for distance, segment in raw_distances:
            prefix = leg_prefix(segment[0])
            if prefix == assigned_leg:
                allowed.append((distance, segment))
            elif not prefix and point.z >= upper_blend_z and segment[0] in TORSO_BONE_NAMES:
                allowed.append((distance, segment))
        return allowed or raw_distances

    if in_torso_span(point, metrics):
        if in_midline_torso(point, metrics):
            allowed = [(distance, segment) for distance, segment in raw_distances if not leg_prefix(segment[0])]
            return allowed or raw_distances

        allowed = []
        for distance, segment in raw_distances:
            prefix = leg_prefix(segment[0])
            if not prefix or distance <= closest_body_distance * 0.45:
                allowed.append((distance, segment))
        return allowed or raw_distances

    return raw_distances


def adjusted_binding_distance(point, segment, raw_distance, closest_body_distance, metrics):
    """Bias nearest-bone scoring away from accidental leg influence."""
    name, _, _ = segment
    prefix = leg_prefix(name)
    body_band = in_body_band(point, metrics)
    distance = raw_distance

    if prefix:
        box = metrics.get("leg_boxes", {}).get(prefix)
        height = metrics.get("height", 1.0)
        pad_y = max(height * 0.08, 0.05)
        pad_z = max(height * 0.08, 0.05)

        if box:
            if point.y < box["min_y"] - pad_y or point.y > box["max_y"] + pad_y:
                distance *= 5.0
            if point.z > box["max_z"] + pad_z:
                distance *= 8.0

        if body_band and closest_body_distance <= raw_distance * 2.5:
            distance *= 4.0
    elif body_band and name in TORSO_BONE_NAMES:
        distance *= 0.55

    return distance


def bind_with_nearest_bone_weights(mesh, armature, max_influences):
    """Bind one mesh using nearest deform bone segment weights."""
    segments = deform_bone_segments(armature)
    if not segments:
        raise RuntimeError("The active armature has no deform bones.")

    world_matrix = mesh.matrix_world.copy()
    mesh.parent = armature
    mesh.matrix_parent_inverse = armature.matrix_world.inverted()
    mesh.matrix_world = world_matrix
    ensure_armature_modifier(mesh, armature)

    group_names = {name for name, _, _ in segments}
    rig_group_names = {bone.name for bone in armature.data.bones}
    for name in rig_group_names:
        group = mesh.vertex_groups.get(name)
        if group:
            mesh.vertex_groups.remove(group)
    groups = {name: mesh.vertex_groups.new(name=name) for name in group_names}

    armature_inverse = armature.matrix_world.inverted()
    influence_count = min(max_influences, len(segments))
    metrics = binding_metrics(segments)
    for vertex in mesh.data.vertices:
        point = armature_inverse @ (mesh.matrix_world @ vertex.co)
        raw_distances = [(distance_to_segment(point, head, tail), (name, head, tail)) for name, head, tail in segments]
        body_distances = [distance for distance, segment in raw_distances if not leg_prefix(segment[0])]
        closest_body_distance = min(body_distances) if body_distances else float("inf")
        candidate_distances = filtered_binding_distances(point, raw_distances, closest_body_distance, metrics)
        scored = sorted(
            (
                (
                    adjusted_binding_distance(point, segment, distance, closest_body_distance, metrics),
                    segment[0],
                )
                for distance, segment in candidate_distances
            ),
            key=lambda item: item[0],
        )[:influence_count]
        weights = [(name, 1.0 / max(distance * distance, 0.0001)) for distance, name in scored]
        if weights:
            strongest = max(weight for _, weight in weights)
            weights = [(name, weight) for name, weight in weights if weight >= strongest * 0.20]
        total = sum(weight for _, weight in weights) or 1.0
        for name, weight in weights:
            groups[name].add([vertex.index], weight / total, "REPLACE")
    mesh.data.update()


class QWG_OT_generate_walk_cycle(Operator):
    bl_idname = "qwg.generate_walk_cycle"
    bl_label = "Generate Walk Cycle"
    bl_description = "Generate a looping quadruped walk cycle on the selected armature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Enable the operator only when an armature is selected."""
        return active_armature(context) is not None

    def execute(self, context):
        """Generate walk-cycle keys for the selected armature."""
        armature = active_armature(context)
        settings = context.scene.qwg_settings

        if settings.frame_end <= settings.frame_start:
            self.report({"ERROR"}, "End frame must be greater than start frame.")
            return {"CANCELLED"}

        gait = GAITS[settings.gait]
        frames = list(range(settings.frame_start, settings.frame_end + 1, settings.key_step))
        if settings.frame_end not in frames:
            frames.append(settings.frame_end)

        mode_by_leg = resolve_leg_modes(armature, settings)
        if not any(mode_by_leg.values()):
            self.report({"ERROR"}, "No usable IK targets or FK leg chains were mapped.")
            return {"CANCELLED"}

        self._prepare_ik_constraints(armature, settings, mode_by_leg)
        armature.animation_data_create()
        data_paths = data_paths_for_cleanup(settings, mode_by_leg)

        if settings.replace_existing and armature.animation_data.action:
            remove_keys_in_range(
                armature.animation_data.action,
                data_paths,
                settings.frame_start,
                settings.frame_end,
            )

        baselines = self._capture_baselines(armature, settings)

        for frame in frames:
            cycle_pos = cycle_position(frame, settings.frame_start, settings.frame_end)
            self._animate_body(armature, settings, gait, baselines, frame, cycle_pos)

            for leg in LEG_ORDER:
                leg_mode = mode_by_leg.get(leg)
                if not leg_mode:
                    continue
                phase = gait.phases[leg]
                forward, lift, is_swing = leg_motion(
                    cycle_pos,
                    phase,
                    gait.duty_factor,
                    settings.stride_length,
                    settings.step_height,
                )
                forward, lift = self._shape_leg_motion(settings, leg, forward, lift)
                if leg_mode == "IK":
                    self._animate_ik_leg(armature, settings, baselines, leg, frame, forward, lift)
                elif leg_mode == "FK":
                    self._animate_fk_leg(
                        armature,
                        settings,
                        baselines,
                        leg,
                        frame,
                        forward,
                        lift,
                        is_swing,
                    )

        apply_interpolation_and_cycles(
            armature.animation_data.action,
            settings.frame_start,
            settings.frame_end,
            settings.add_cycles,
            settings.interpolation,
            data_paths,
        )
        context.scene.frame_start = settings.frame_start
        context.scene.frame_end = settings.frame_end
        context.scene.frame_set(settings.frame_start)

        self.report({"INFO"}, f"Generated {gait.label.lower()} cycle on {armature.name}.")
        return {"FINISHED"}

    def _prepare_ik_constraints(self, armature, settings, mode_by_leg):
        """Keep generated IK feet from inheriting control-handle rotation."""
        for leg, mode in mode_by_leg.items():
            if mode != "IK":
                continue
            foot_name = getattr(settings, FK_FIELDS[leg][2])
            foot = pose_bone(armature, foot_name)
            if not foot:
                continue
            for constraint in foot.constraints:
                if constraint.type != "IK":
                    continue
                if constraint.name != "QWalk IK" and constraint.target != armature:
                    continue
                if hasattr(constraint, "use_rotation"):
                    constraint.use_rotation = False
                if hasattr(constraint, "use_stretch"):
                    constraint.use_stretch = False

    def _capture_baselines(self, armature, settings):
        """Read stable base transforms for object and mapped bones."""
        baselines = {
            "object_location": stored_object_location(armature),
            "object_rotation": stored_object_rotation(armature),
            "bones": {},
            "leg_limits": {},
        }

        for name in mapped_bones(settings):
            bone = pose_bone(armature, name)
            if bone:
                ensure_euler(bone)
                baselines["bones"][name] = {
                    "location": stored_location(bone, bone.location),
                    "rotation": stored_rotation(bone, bone.rotation_euler),
                }

        for leg in LEG_ORDER:
            length = self._leg_chain_length(armature, settings, leg)
            if length > 0.0:
                forward_factor = 0.18
                lift_factor = 0.10
                if settings.gait == "COMPACT_WALK":
                    forward_factor = 0.15 if leg.startswith("f") else 0.13
                    lift_factor = 0.065 if leg.startswith("f") else 0.055
                baselines["leg_limits"][leg] = {
                    "forward": max(length * forward_factor, 0.01),
                    "lift": max(length * lift_factor, 0.005),
                }

        return baselines

    def _shape_leg_motion(self, settings, leg, forward, lift):
        """Adjust generic stride values for gait-specific animal proportions."""
        if settings.gait != "COMPACT_WALK":
            return forward, lift

        reach_scale = 0.82 if leg.startswith("f") else 0.74
        lift_scale = 0.58 if leg.startswith("f") else 0.50
        return forward * reach_scale, lift * lift_scale

    def _leg_chain_length(self, armature, settings, leg):
        """Return the rest length of a mapped FK leg chain."""
        length = 0.0
        for field in FK_FIELDS[leg]:
            bone = armature.data.bones.get(getattr(settings, field))
            if bone:
                length += bone.length
        return length

    def _animate_body(self, armature, settings, gait, baselines, frame, cycle_pos):
        """Key body bob, sway, pitch, and roll for one frame."""
        target_name = settings.body_bone or settings.root_bone
        bob = (
            math.sin(cycle_pos * math.tau * gait.body_bob_frequency)
            * settings.body_bob
            * gait.body_bob_scale
        )
        sway = (
            math.sin(cycle_pos * math.tau * gait.body_sway_frequency)
            * settings.body_sway
            * gait.body_sway_scale
        )
        pitch = (
            math.sin(cycle_pos * math.tau * gait.body_pitch_frequency)
            * math.radians(settings.body_pitch)
            * gait.body_pitch_scale
        )
        roll = (
            math.sin(cycle_pos * math.tau * gait.body_roll_frequency)
            * math.radians(settings.body_roll)
            * gait.body_roll_scale
        )

        if bone_exists(armature, target_name):
            bone = armature.pose.bones[target_name]
            baseline = baselines["bones"][target_name]
            offset = axis_offset(settings.forward_axis, 0.0, settings.side_axis, sway, settings.up_axis, bob)
            local_offset = pose_location_for_armature_offset(bone, offset)
            bone.location = baseline["location"].copy()
            bone.location.x += local_offset.x
            bone.location.y += local_offset.y
            bone.location.z += local_offset.z

            bone.rotation_euler = baseline["rotation"].copy()
            bone.rotation_euler[axis_index(settings.side_axis)] += pitch * axis_sign(settings.side_axis)
            bone.rotation_euler[axis_index(settings.forward_axis)] += roll * axis_sign(settings.forward_axis)
            keyframe_pose_bone(bone, frame, ("location", "rotation_euler"))
            return

        offset = axis_offset(settings.forward_axis, 0.0, settings.side_axis, sway, settings.up_axis, bob)
        armature.location = baselines["object_location"].copy()
        armature.location.x += offset[0]
        armature.location.y += offset[1]
        armature.location.z += offset[2]
        armature.rotation_euler = baselines["object_rotation"].copy()
        armature.rotation_euler[axis_index(settings.side_axis)] += pitch * axis_sign(settings.side_axis)
        armature.rotation_euler[axis_index(settings.forward_axis)] += roll * axis_sign(settings.forward_axis)
        armature.keyframe_insert(data_path="location", frame=frame)
        armature.keyframe_insert(data_path="rotation_euler", frame=frame)

    def _animate_ik_leg(self, armature, settings, baselines, leg, frame, forward, lift):
        """Key one IK target's location for a frame."""
        bone_name = getattr(settings, IK_FIELDS[leg])
        bone = armature.pose.bones[bone_name]
        baseline = baselines["bones"][bone_name]["location"]
        limits = baselines.get("leg_limits", {}).get(leg)
        if limits:
            forward = max(-limits["forward"], min(limits["forward"], forward))
            lift = min(limits["lift"], lift)
        offset = axis_offset(settings.forward_axis, forward, settings.side_axis, 0.0, settings.up_axis, lift)
        local_offset = pose_location_for_armature_offset(bone, offset)

        bone.location = baseline.copy()
        bone.location.x += local_offset.x
        bone.location.y += local_offset.y
        bone.location.z += local_offset.z
        keyframe_pose_bone(bone, frame, ("location",))

    def _animate_fk_leg(self, armature, settings, baselines, leg, frame, forward, lift, is_swing):
        """Key one FK leg chain's rotations for a frame."""
        upper_name, lower_name, foot_name = [getattr(settings, field) for field in FK_FIELDS[leg]]
        upper = armature.pose.bones[upper_name]
        lower = armature.pose.bones[lower_name]
        foot = armature.pose.bones[foot_name]

        stride_half = max(0.001, settings.stride_length * 0.5)
        swing_amount = max(-1.0, min(1.0, forward / stride_half))
        upper_angle = swing_amount * math.radians(settings.fk_swing_degrees)
        lower_angle = (lift / max(0.001, settings.step_height)) * math.radians(settings.fk_lift_degrees)
        if not is_swing:
            lower_angle *= 0.25

        upper.rotation_euler = rotation_offset(
            baselines["bones"][upper_name]["rotation"],
            settings.fk_bend_axis,
            upper_angle,
        )
        lower.rotation_euler = rotation_offset(
            baselines["bones"][lower_name]["rotation"],
            settings.fk_bend_axis,
            -lower_angle,
        )
        foot.rotation_euler = rotation_offset(
            baselines["bones"][foot_name]["rotation"],
            settings.fk_bend_axis,
            -(upper_angle * 0.5) + lower_angle * 0.35,
        )

        keyframe_pose_bone(upper, frame, ("rotation_euler",))
        keyframe_pose_bone(lower, frame, ("rotation_euler",))
        keyframe_pose_bone(foot, frame, ("rotation_euler",))


class QWG_OT_clear_cycle_keys(Operator):
    bl_idname = "qwg.clear_cycle_keys"
    bl_label = "Clear Generated Range"
    bl_description = "Remove generated location and Euler rotation keys from mapped bones in the frame range"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Enable the operator only when an armature is selected."""
        return active_armature(context) is not None

    def execute(self, context):
        """Remove mapped animation keys from the configured range."""
        armature = active_armature(context)
        settings = context.scene.qwg_settings
        mode_by_leg = resolve_leg_modes(armature, settings)
        if not armature.animation_data or not armature.animation_data.action:
            self.report({"INFO"}, "Armature has no action to clear.")
            return {"FINISHED"}

        data_paths = data_paths_for_cleanup(settings, mode_by_leg)
        remove_keys_in_range(armature.animation_data.action, data_paths, settings.frame_start, settings.frame_end)
        self.report({"INFO"}, "Cleared mapped keys in the generated frame range.")
        return {"FINISHED"}


class QWG_OT_set_base_pose(Operator):
    bl_idname = "qwg.set_base_pose"
    bl_label = "Set Base Pose"
    bl_description = "Use the current mapped transforms as the base pose for future walk generation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Enable the operator only when an armature is selected."""
        return active_armature(context) is not None

    def execute(self, context):
        """Store current mapped transforms as the generation baseline."""
        armature = active_armature(context)
        settings = context.scene.qwg_settings
        store_base_pose(armature, mapped_bones(settings))
        self.report({"INFO"}, "Stored current mapped transforms as the QWalk base pose.")
        return {"FINISHED"}
