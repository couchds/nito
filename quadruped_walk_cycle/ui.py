from bpy.types import Panel

from .constants import FK_FIELDS, IK_FIELDS, LEG_LABELS, LEG_ORDER
from .rig_utils import active_armature


class QWG_PT_panel(Panel):
    bl_label = "Quadruped Walk"
    bl_idname = "QWG_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "QWalk"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.qwg_settings
        armature = active_armature(context)

        if not armature:
            layout.label(text="Select an armature.")
            return

        row = layout.row(align=True)
        row.operator("qwg.auto_map", icon="VIEWZOOM")
        row.operator("qwg.generate_walk_cycle", icon="ARMATURE_DATA")

        layout.operator("qwg.clear_cycle_keys", icon="TRASH")

        box = layout.box()
        box.label(text="Cycle")
        row = box.row(align=True)
        row.prop(settings, "frame_start")
        row.prop(settings, "frame_end")
        box.prop(settings, "key_step")
        box.prop(settings, "gait")
        box.prop(settings, "generation_mode")

        box = layout.box()
        box.label(text="Motion")
        box.prop(settings, "stride_length")
        box.prop(settings, "step_height")
        box.prop(settings, "body_bob")
        box.prop(settings, "body_sway")
        row = box.row(align=True)
        row.prop(settings, "body_pitch")
        row.prop(settings, "body_roll")
        row = box.row(align=True)
        row.prop(settings, "fk_swing_degrees")
        row.prop(settings, "fk_lift_degrees")

        box = layout.box()
        box.label(text="Axes")
        row = box.row(align=True)
        row.prop(settings, "forward_axis")
        row.prop(settings, "side_axis")
        row.prop(settings, "up_axis")
        box.prop(settings, "fk_bend_axis")

        box = layout.box()
        box.label(text="Output")
        box.prop(settings, "replace_existing")
        box.prop(settings, "add_cycles")
        box.prop(settings, "interpolation")

        self._draw_mapping(layout, settings, armature)

    def _draw_mapping(self, layout, settings, armature):
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
        layout.prop_search(settings, prop_name, armature.data, "bones", text=label)
