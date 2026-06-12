from textwrap import wrap

from bpy.props import StringProperty
from bpy.types import Operator, Panel

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
    "qwg_guide_front_left_foot": "Front Left Foot / Paw / Hoof",
    "qwg_guide_front_right_upper": "Front Right Upper Leg",
    "qwg_guide_front_right_lower": "Front Right Lower Leg",
    "qwg_guide_front_right_foot": "Front Right Foot / Paw / Hoof",
    "qwg_guide_rear_left_upper": "Rear Left Upper Leg",
    "qwg_guide_rear_left_lower": "Rear Left Lower Leg",
    "qwg_guide_rear_left_foot": "Rear Left Foot / Paw / Hoof",
    "qwg_guide_rear_right_upper": "Rear Right Upper Leg",
    "qwg_guide_rear_right_lower": "Rear Right Lower Leg",
    "qwg_guide_rear_right_foot": "Rear Right Foot / Paw / Hoof",
}


GUIDE_BONE_HELP = {
    "qwg_guide_pelvis": {
        "role": "Rear torso and hip block. This defines where the spine leaves the rump and where the rear legs should be anchored.",
        "head": "Place at the rear center of the body mass, near the top/front of the hip bowl and just forward of the tail base. Keep it on the animal centerline, inside the body rather than on the outer fur silhouette.",
        "tail": "Place forward along the back into the lumbar area, where the rump transitions into the main spine. It should stay inside the torso and roughly follow the top mass of the hips.",
        "check": "Do not put this on the tail hair, saddle, armor, or the visible outside contour. It is an internal skeletal guide for the hip/pelvis area.",
    },
    "qwg_guide_spine": {
        "role": "Middle torso segment. This bridges the pelvis to the rib cage and controls the main back line.",
        "head": "This should connect from the pelvis tail at the rear/mid back.",
        "tail": "Place around the middle of the rib cage or saddle area, still on the centerline and inside the body mass.",
        "check": "Keep the spine smooth and centered through the body. Ignore saddles, plates, fur clumps, and other surface props.",
    },
    "qwg_guide_chest": {
        "role": "Front torso and shoulder block. This sets the front-leg anchor and the base of the neck.",
        "head": "This should connect from the spine tail near the middle/front of the back.",
        "tail": "Place at the withers or upper chest/base-neck area, above and slightly behind where the front legs enter the torso.",
        "check": "For horses, think withers/shoulder area. For dogs/cats, think upper shoulder blade area. Keep it inside the body, not on armor or tack.",
    },
    "qwg_guide_neck": {
        "role": "Neck chain from chest to skull. This controls the animal's head carriage.",
        "head": "Place at the chest tail/base of neck, where the neck rises out of the shoulders.",
        "tail": "Place near the poll/base of skull, behind the ears and before the face/muzzle begins.",
        "check": "Follow the center of the neck volume, not the mane or fur outline. On long-necked animals, keep this as the main neck axis.",
    },
    "qwg_guide_head": {
        "role": "Head direction and skull length. This gives the generated rig a head bone that can rotate naturally.",
        "head": "Place at the base of skull where the neck ends.",
        "tail": "Place toward the center/front of the skull or muzzle direction. For long snouts, aim through the face but avoid stretching all the way to tiny nose details unless the whole head is long.",
        "check": "Use the skull/head mass, not ears, horns, reins, bridle straps, or decorative armor. Ears and horns usually should not define the head bone.",
    },
    "qwg_guide_tail": {
        "role": "Bony tail direction. This is a skeleton guide for the tail root and main tail line.",
        "head": "Place at the tail base, where the tail exits the pelvis/rump.",
        "tail": "Place along the bony tail direction. For fluffy tails, aim through the core of the tail rather than the outer fur edge.",
        "check": "If the animal has no visible tail or only a stub, keep this short and close to the rump. Do not chase long hair volume.",
    },
}


LEG_BONE_HELP = {
    ("front", "upper"): {
        "role": "Front upper limb. This approximates shoulder to elbow, even when the shoulder is hidden inside the torso.",
        "head": "Place at the shoulder socket area, slightly inside the chest where the front leg enters the body. On horses this is high and behind the visible upper front leg; on dogs/cats it is inside the shoulder blade mass.",
        "tail": "Place at the elbow, usually the first major bend below the chest and behind the front leg column.",
        "check": "Do not start at the top surface of the shoulder or at armor straps. This bone is internal, from shoulder joint to elbow.",
    },
    ("front", "lower"): {
        "role": "Front lower limb. This runs from elbow to wrist/carpus, the long lower front-leg segment.",
        "head": "Place at the elbow, matching the upper front-leg tail.",
        "tail": "Place at the wrist/carpus bend just above the paw or hoof. On a horse this is the visible front knee/carpus; on a dog/cat it is the wrist area above the paw.",
        "check": "This should usually be mostly vertical in a standing pose. Avoid placing the tail at the ground contact; that belongs to the foot guide.",
    },
    ("front", "foot"): {
        "role": "Front foot, paw, or hoof. This defines the contact direction from wrist/carpus to the toe/hoof.",
        "head": "Place at the wrist/carpus or ankle-like bend where the lower front limb ends.",
        "tail": "Place at the front/center of the toe, paw pad, or hoof contact point on the ground.",
        "check": "Tail should land on the contact point used for animation. For hooves, use the hoof tip/centerline; for paws, use the front pad/toe center.",
    },
    ("rear", "upper"): {
        "role": "Rear upper limb. This approximates hip to stifle/knee through the thigh.",
        "head": "Place at the hip socket area inside the rump, usually forward/down from the tail base and inside the rear body mass.",
        "tail": "Place at the stifle/knee, the forward-facing bend of the rear leg under the flank. This is not the hock.",
        "check": "This bone is often partly hidden by body volume. Use the anatomical thigh direction rather than the outer rump silhouette.",
    },
    ("rear", "lower"): {
        "role": "Rear lower limb. This runs from stifle/knee to hock/ankle.",
        "head": "Place at the stifle/knee, matching the rear upper-limb tail.",
        "tail": "Place at the hock, the backward-pointing ankle bend above the rear foot or hoof.",
        "check": "For horses and dogs this usually angles backward/down before the foot drops to the ground. Do not put the tail at the hoof or paw contact.",
    },
    ("rear", "foot"): {
        "role": "Rear foot, paw, or hoof. This defines the contact direction from hock/ankle to toe/hoof.",
        "head": "Place at the hock/ankle where the rear lower limb ends.",
        "tail": "Place at the front/center of the toe, paw pad, or hoof contact point on the ground.",
        "check": "Use the animation contact point, not the back of the heel/hock. The foot guide should describe how the foot rests on the ground.",
    },
}


def guide_help_data(bone_name):
    """Return placement help for a guide bone."""
    if bone_name in GUIDE_BONE_HELP:
        return GUIDE_BONE_HELP[bone_name]

    parts = bone_name.split("_")
    if len(parts) < 5 or parts[0:2] != ["qwg", "guide"]:
        return None

    limb_region = parts[2]
    segment = parts[-1]
    if limb_region not in {"front", "rear"} or segment not in {"upper", "lower", "foot"}:
        return None
    return LEG_BONE_HELP.get((limb_region, segment))


def is_leg_guide_bone(bone_name):
    """Return whether a guide bone belongs to a leg chain."""
    return any(token in bone_name for token in ("_front_", "_rear_"))


def draw_wrapped_text(layout, text, width):
    """Draw readable wrapped helper text in Blender UI labels."""
    for line in wrap(text, width=width, break_long_words=False):
        layout.label(text=line)


def guide_short_help(bone_name):
    """Return a very short sidebar-safe placement hint."""
    if bone_name == "qwg_guide_pelvis":
        return "Hip / rear-leg anchor"
    if bone_name == "qwg_guide_spine":
        return "Middle back axis"
    if bone_name == "qwg_guide_chest":
        return "Shoulder / chest anchor"
    if bone_name == "qwg_guide_neck":
        return "Neck centerline"
    if bone_name == "qwg_guide_head":
        return "Skull direction"
    if bone_name == "qwg_guide_tail":
        return "Tail root line"

    parts = bone_name.split("_")
    if len(parts) < 5:
        return "Guide landmark"
    limb_region = parts[2]
    segment = parts[-1]
    region_label = "Front" if limb_region == "front" else "Rear"
    segment_labels = {
        "upper": "upper limb",
        "lower": "lower limb",
        "foot": "foot contact",
    }
    segment_label = segment_labels.get(segment, "limb")
    return f"{region_label} {segment_label}"


class QWG_OT_show_guide_bone_help(Operator):
    bl_idname = "qwg.show_guide_bone_help"
    bl_label = "Nito Bone Placement Notes"
    bl_description = "Show detailed placement notes for the selected Nito guide bone"
    bl_options = {"INTERNAL"}

    bone_name: StringProperty(default="")

    def invoke(self, context, event):
        """Open a wider dialog for long-form placement guidance."""
        return context.window_manager.invoke_props_dialog(self, width=680)

    def draw(self, context):
        """Draw long-form placement help in a dialog."""
        layout = self.layout
        help_data = guide_help_data(self.bone_name)
        title = GUIDE_BONE_LABELS.get(self.bone_name, self.bone_name or "Guide Bone")

        layout.label(text=title, icon="BONE_DATA")
        if self.bone_name:
            layout.label(text=self.bone_name)
        if not help_data:
            draw_wrapped_text(layout, "No placement notes are available for this bone yet.", width=46)
            return

        for label, key in (("Role", "role"), ("Head placement", "head"), ("Tail placement", "tail"), ("Common checks", "check")):
            box = layout.box()
            box.label(text=label)
            draw_wrapped_text(box, help_data[key], width=46)

        if is_leg_guide_bone(self.bone_name):
            box = layout.box()
            box.label(text="Side-view note")
            draw_wrapped_text(
                box,
                "Left and right legs often overlap in a side view. Correct the visible chain cleanly; Preview Rig From Guide mirrors leg pairs by default unless you disable Mirror Leg Pairs.",
                width=46,
            )

    def execute(self, context):
        """Close the help dialog."""
        return {"FINISHED"}


class QWG_PT_panel(Panel):
    bl_label = "Nito Labeling"
    bl_idname = "QWG_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nito"

    def draw(self, context):
        """Draw the Nito sidebar panel."""
        layout = self.layout
        settings = context.scene.qwg_settings
        armature = active_armature(context)
        has_mesh = self._has_selected_mesh(context)
        has_guide = self._has_selected_guide(context)

        guide_box = layout.box()
        guide_box.label(text="Nito Guide", icon="EMPTY_AXIS")
        guide_box.label(text="Place this guide for training labels.")

        guide_model_row = guide_box.row()
        guide_model_row.enabled = has_mesh
        guide_model_op = guide_model_row.operator(
            "qwg.create_fit_guides",
            text="Generate Nito Guide from Model",
            icon="OUTLINER_DATA_ARMATURE",
        )
        guide_model_op.use_learned_initializer = True

        guide_sampler_row = guide_box.row()
        guide_sampler_row.enabled = has_mesh
        guide_sampler_op = guide_sampler_row.operator(
            "qwg.create_fit_guides",
            text="Generate Nito Guide from Sampler",
            icon="EMPTY_AXIS",
        )
        guide_sampler_op.use_learned_initializer = False

        guide_build_row = guide_box.row()
        guide_build_row.enabled = has_guide
        guide_build_op = guide_build_row.operator(
            "qwg.create_armature_from_guides",
            text="Preview Rig From Guide",
            icon="ARMATURE_DATA",
        )
        guide_build_op.symmetrize_legs = True
        guide_build_op.replace_existing_generated = True

        guide_bind_row = guide_box.row()
        guide_bind_row.enabled = has_mesh and has_guide
        guide_bind_row.operator("qwg.generate_bind_test_rig", text="Preview + Bind From Guide", icon="MOD_ARMATURE")

        if armature and armature.get("qwg_is_guide"):
            self._draw_guide_status(guide_box, context)
            guide_box.label(text="Guide is the label source of truth.")
            guide_box.label(text="Preview only to validate placement.")
            return

        rig_box = layout.box()
        rig_box.label(text="Nito Preview Rig", icon="OUTLINER_OB_ARMATURE")
        rig_box.label(text="Temporary rig generated from a guide.")

        if not armature:
            rig_box.label(text="Select a mesh to create a guide.")
            rig_box.label(text="Select a guide to preview validation.")
            return

        row = rig_box.row(align=True)
        row.operator("qwg.auto_map", text="Remap Bones", icon="VIEWZOOM")
        row.operator("qwg.generate_walk_cycle", text="Pose Test Walk", icon="ARMATURE_DATA")

        bind_row = rig_box.row()
        bind_row.enabled = has_mesh
        bind_row.operator("qwg.bind_selected_meshes", text="Bind Mesh To Preview Rig", icon="MOD_ARMATURE")

        row = rig_box.row(align=True)
        row.operator("qwg.clear_cycle_keys", text="Clear Preview Keys", icon="TRASH")
        row.operator("qwg.set_base_pose", text="Store Base Pose", icon="PINNED")

        box = layout.box()
        box.label(text="Pose Test")
        row = box.row(align=True)
        row.prop(settings, "frame_start")
        row.prop(settings, "frame_end")
        box.prop(settings, "key_step")
        box.prop(settings, "gait")
        box.prop(settings, "generation_mode")

        self._draw_motion(layout, settings, armature)

        box = layout.box()
        box.label(text="Rig Axes")
        row = box.row(align=True)
        row.prop(settings, "forward_axis")
        row.prop(settings, "side_axis")
        row.prop(settings, "up_axis")
        fk_axis = box.row()
        fk_axis.enabled = self._has_fk_legs(armature, settings)
        fk_axis.prop(settings, "fk_bend_axis")

        box = layout.box()
        box.label(text="Preview Output")
        box.prop(settings, "replace_existing")
        box.prop(settings, "add_cycles")
        box.prop(settings, "interpolation")

        self._draw_mapping(layout, settings, armature)

    def _draw_motion(self, layout, settings, armature):
        """Draw context-aware motion controls."""
        box = layout.box()
        box.label(text="Foot Preview Motion")
        box.prop(settings, "stride_length")
        box.prop(settings, "step_height")

        box = layout.box()
        box.label(text="Body Preview Motion")
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
        """Return whether any selected object is a Nito guide armature."""
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
        """Draw the active guide bone label and placement help."""
        bone_name = self._active_guide_bone_name(context)
        box = layout.box()
        box.label(text="Nito Guide Bone")
        if bone_name:
            box.label(text=GUIDE_BONE_LABELS.get(bone_name, bone_name), icon="BONE_DATA")
            box.label(text=bone_name)
            self._draw_guide_help(box, bone_name)
        else:
            box.label(text="No guide bone selected.")
            self._draw_wrapped_text(
                box,
                "Select a guide bone in Edit Mode or Pose Mode to see placement guidance for that landmark.",
            )

    def _draw_guide_help(self, layout, bone_name):
        """Draw detailed placement notes for the selected guide bone."""
        help_data = self._guide_help_data(bone_name)
        if not help_data:
            return

        layout.separator()
        layout.label(text="Placement", icon="INFO")
        layout.label(text=guide_short_help(bone_name))
        layout.label(text="Head / tail in notes.")
        help_op = layout.operator("qwg.show_guide_bone_help", text="Placement Notes", icon="HELP")
        help_op.bone_name = bone_name

        if is_leg_guide_bone(bone_name):
            layout.separator()
            layout.label(text="Side view mirrors pairs.")

    def _guide_help_data(self, bone_name):
        """Return placement help for a guide bone."""
        return guide_help_data(bone_name)

    def _draw_wrapped_text(self, layout, text, width=16):
        """Draw readable wrapped helper text in Blender's narrow sidebar."""
        draw_wrapped_text(layout, text, width=width)

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
