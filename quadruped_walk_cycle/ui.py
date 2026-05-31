from bpy.types import Panel

from .constants import FK_FIELDS, IK_FIELDS, LEG_LABELS, LEG_ORDER
from .rig_utils import active_armature, resolve_leg_modes


GUIDE_BONE_LABELS = {
    "qwg_guide_pelvis": "Pelvis",
    "qwg_guide_spine": "Spine",
    "qwg_guide_chest": "Chest",
    "qwg_guide_neck": "Neck",
    "qwg_guide_head": "Head",
    "qwg_guide_tail": "Tail",
    "qwg_guide_front_left_upper": "Front Left Upper Leg",
    "qwg_guide_front_left_lower": "Front Left Lower Leg",
    "qwg_guide_front_left_foot": "Front Left Hoof",
    "qwg_guide_front_right_upper": "Front Right Upper Leg",
    "qwg_guide_front_right_lower": "Front Right Lower Leg",
    "qwg_guide_front_right_foot": "Front Right Hoof",
    "qwg_guide_rear_left_upper": "Rear Left Upper Leg",
    "qwg_guide_rear_left_lower": "Rear Left Lower Leg",
    "qwg_guide_rear_left_foot": "Rear Left Hoof",
    "qwg_guide_rear_right_upper": "Rear Right Upper Leg",
    "qwg_guide_rear_right_lower": "Rear Right Lower Leg",
    "qwg_guide_rear_right_foot": "Rear Right Hoof",
}


class QWG_PT_panel(Panel):
    bl_label = "Quadruped Walk"
    bl_idname = "QWG_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "QWalk"

    def draw(self, context):
        """Draw the QWalk sidebar panel."""
        layout = self.layout
        settings = context.scene.qwg_settings
        armature = active_armature(context)

        layout.operator("qwg.create_quadruped_armature", icon="OUTLINER_OB_ARMATURE")
        guide_row = layout.row()
        guide_row.enabled = self._has_selected_mesh(context)
        guide_row.operator("qwg.create_fit_guides", icon="EMPTY_AXIS")

        guide_build_row = layout.row()
        guide_build_row.enabled = self._has_selected_guide(context)
        guide_build_op = guide_build_row.operator("qwg.create_armature_from_guides", icon="ARMATURE_DATA")
        guide_build_op.symmetrize_legs = True
        guide_build_op.replace_existing_generated = True

        fit_row = layout.row()
        fit_row.enabled = self._has_selected_mesh(context)
        fit_row.operator("qwg.create_fitted_quadruped_armature", icon="MOD_ARMATURE")

        if not armature:
            layout.label(text="Select an armature.")
            return
        if armature.get("qwg_is_guide"):
            self._draw_guide_status(layout, context)
            layout.label(text="Edit guide bones, then generate the armature.")
            return

        row = layout.row(align=True)
        row.operator("qwg.auto_map", icon="VIEWZOOM")
        row.operator("qwg.generate_walk_cycle", icon="ARMATURE_DATA")

        bind_row = layout.row()
        bind_row.enabled = self._has_selected_mesh(context)
        bind_row.operator("qwg.bind_selected_meshes", icon="MOD_ARMATURE")

        layout.operator("qwg.clear_cycle_keys", icon="TRASH")
        layout.operator("qwg.set_base_pose", icon="PINNED")

        box = layout.box()
        box.label(text="Cycle")
        row = box.row(align=True)
        row.prop(settings, "frame_start")
        row.prop(settings, "frame_end")
        box.prop(settings, "key_step")
        box.prop(settings, "gait")
        box.prop(settings, "generation_mode")

        self._draw_motion(layout, settings, armature)

        box = layout.box()
        box.label(text="Axes")
        row = box.row(align=True)
        row.prop(settings, "forward_axis")
        row.prop(settings, "side_axis")
        row.prop(settings, "up_axis")
        fk_axis = box.row()
        fk_axis.enabled = self._has_fk_legs(armature, settings)
        fk_axis.prop(settings, "fk_bend_axis")

        box = layout.box()
        box.label(text="Output")
        box.prop(settings, "replace_existing")
        box.prop(settings, "add_cycles")
        box.prop(settings, "interpolation")

        self._draw_mapping(layout, settings, armature)

    def _draw_motion(self, layout, settings, armature):
        """Draw context-aware motion controls."""
        box = layout.box()
        box.label(text="Foot Motion")
        box.prop(settings, "stride_length")
        box.prop(settings, "step_height")

        box = layout.box()
        box.label(text="Body Motion")
        box.prop(settings, "body_bob")
        box.prop(settings, "body_sway")
        box.prop(settings, "body_pitch")
        box.prop(settings, "body_roll")

        box = layout.box()
        box.label(text="FK Legs")
        box.enabled = self._has_fk_legs(armature, settings)
        box.prop(settings, "fk_swing_degrees")
        box.prop(settings, "fk_lift_degrees")

    def _has_fk_legs(self, armature, settings):
        """Return whether the current settings will animate any FK chains."""
        return any(mode == "FK" for mode in resolve_leg_modes(armature, settings).values())

    def _has_selected_mesh(self, context):
        """Return whether any selected object is a mesh."""
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def _has_selected_guide(self, context):
        """Return whether any selected object is a QWalk guide armature."""
        return any(obj.type == "ARMATURE" and obj.get("qwg_is_guide") for obj in context.selected_objects)

    def _active_guide_bone_name(self, context):
        """Return the currently active or selected guide bone name."""
        active_bone = getattr(context, "active_bone", None)
        if active_bone:
            return active_bone.name

        active_pose_bone = getattr(context, "active_pose_bone", None)
        if active_pose_bone:
            return active_pose_bone.name

        for attr_name in ("selected_editable_bones", "selected_bones", "selected_pose_bones"):
            selected = getattr(context, attr_name, None)
            if selected:
                return selected[0].name
        return ""

    def _draw_guide_status(self, layout, context):
        """Draw the active guide bone label while editing a guide rig."""
        bone_name = self._active_guide_bone_name(context)
        box = layout.box()
        box.label(text="Guide Bone")
        if bone_name:
            box.label(text=GUIDE_BONE_LABELS.get(bone_name, bone_name), icon="BONE_DATA")
            box.label(text=bone_name)
        else:
            box.label(text="No guide bone selected.")

    def _draw_mapping(self, layout, settings, armature):
        """Draw body, IK, and FK bone mapping controls."""
        box = layout.box()
        box.label(text="Body Bones")
        self._prop_search(box, settings, "root_bone", armature, "Root")
        self._prop_search(box, settings, "body_bone", armature, "Body")

        ik_box = layout.box()
        ik_box.label(text="IK Targets")
        for leg in LEG_ORDER:
            self._prop_search(ik_box, settings, IK_FIELDS[leg], armature, LEG_LABELS[leg])

        fk_box = layout.box()
        fk_box.label(text="FK Chains")
        for leg in LEG_ORDER:
            col = fk_box.column(align=True)
            col.label(text=LEG_LABELS[leg])
            upper, lower, foot = FK_FIELDS[leg]
            self._prop_search(col, settings, upper, armature, "Upper")
            self._prop_search(col, settings, lower, armature, "Lower")
            self._prop_search(col, settings, foot, armature, "Foot")

    def _prop_search(self, layout, settings, prop_name, armature, label):
        """Draw a bone search field for one setting."""
        layout.prop_search(settings, prop_name, armature.data, "bones", text=label)
