import math

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
        """Capture current object and mapped-bone transforms."""
        baselines = {
            "object_location": armature.location.copy(),
            "object_rotation": armature.rotation_euler.copy(),
            "bones": {},
        }

        for name in mapped_bones(settings):
            bone = pose_bone(armature, name)
            if bone:
                ensure_euler(bone)
                baselines["bones"][name] = {
                    "location": bone.location.copy(),
                    "rotation": bone.rotation_euler.copy(),
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
