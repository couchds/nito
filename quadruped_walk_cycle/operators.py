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
    for name in group_names:
        group = mesh.vertex_groups.get(name)
        if group:
            mesh.vertex_groups.remove(group)
    groups = {name: mesh.vertex_groups.new(name=name) for name in group_names}

    armature_inverse = armature.matrix_world.inverted()
    influence_count = min(max_influences, len(segments))
    for vertex in mesh.data.vertices:
        point = armature_inverse @ (mesh.matrix_world @ vertex.co)
        scored = sorted(
            ((distance_to_segment(point, head, tail), name) for name, head, tail in segments),
            key=lambda item: item[0],
        )[:influence_count]
        weights = [(name, 1.0 / max(distance * distance, 0.0001)) for distance, name in scored]
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

    def _capture_baselines(self, armature, settings):
        """Read stable base transforms for object and mapped bones."""
        baselines = {
            "object_location": stored_object_location(armature),
            "object_rotation": stored_object_rotation(armature),
            "bones": {},
        }

        for name in mapped_bones(settings):
            bone = pose_bone(armature, name)
            if bone:
                ensure_euler(bone)
                baselines["bones"][name] = {
                    "location": stored_location(bone, bone.location),
                    "rotation": stored_rotation(bone, bone.rotation_euler),
                }

        return baselines

    def _animate_body(self, armature, settings, gait, baselines, frame, cycle_pos):
        """Key body bob, sway, pitch, and roll for one frame."""
        target_name = settings.body_bone or settings.root_bone
        bob = math.sin(cycle_pos * math.tau * gait.body_bobs_per_cycle) * settings.body_bob
        sway = math.sin(cycle_pos * math.tau * 2.0) * settings.body_sway
        pitch = math.sin(cycle_pos * math.tau) * math.radians(settings.body_pitch)
        roll = math.sin(cycle_pos * math.tau * 2.0) * math.radians(settings.body_roll)

        if bone_exists(armature, target_name):
            bone = armature.pose.bones[target_name]
            baseline = baselines["bones"][target_name]
            offset = axis_offset(settings.forward_axis, 0.0, settings.side_axis, sway, settings.up_axis, bob)
            bone.location = baseline["location"].copy()
            bone.location.x += offset[0]
            bone.location.y += offset[1]
            bone.location.z += offset[2]

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
        offset = axis_offset(settings.forward_axis, forward, settings.side_axis, 0.0, settings.up_axis, lift)

        bone.location = baseline.copy()
        bone.location.x += offset[0]
        bone.location.y += offset[1]
        bone.location.z += offset[2]
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
