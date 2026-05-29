import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator
from math import cos, sin
from mathutils import Vector

from .constants import FK_FIELDS, IK_FIELDS, LEG_ORDER


STANDARD_LEG_NAMES = {
    "fl": {
        "upper": "front_left_upper",
        "lower": "front_left_lower",
        "foot": "front_left_foot",
        "ik": "front_left_ik",
        "pole": "front_left_pole",
    },
    "fr": {
        "upper": "front_right_upper",
        "lower": "front_right_lower",
        "foot": "front_right_foot",
        "ik": "front_right_ik",
        "pole": "front_right_pole",
    },
    "rl": {
        "upper": "rear_left_upper",
        "lower": "rear_left_lower",
        "foot": "rear_left_foot",
        "ik": "rear_left_ik",
        "pole": "rear_left_pole",
    },
    "rr": {
        "upper": "rear_right_upper",
        "lower": "rear_right_lower",
        "foot": "rear_right_foot",
        "ik": "rear_right_ik",
        "pole": "rear_right_pole",
    },
}


def scaled(point, scale):
    """Return a Vector point multiplied by the armature scale."""
    return Vector(point) * scale


def add_edit_bone(edit_bones, name, head, tail, scale, parent=None, connected=False, deform=True):
    """Create an edit bone with common parent and deform settings."""
    bone = edit_bones.new(name)
    bone.head = scaled(head, scale)
    bone.tail = scaled(tail, scale)
    bone.parent = parent
    bone.use_connect = connected
    bone.use_deform = deform
    return bone


def get_widget_collection(context, armature_name):
    """Create a collection for generated control-shape objects."""
    collection_name = f"{armature_name}_widgets"
    collection = bpy.data.collections.get(collection_name)
    if not collection:
        collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(collection)
    return collection


def create_widget_object(collection, name, vertices, edges):
    """Create a hidden mesh object used as a custom bone shape."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj.hide_viewport = True
    return obj


def circle_points(radius=1.0, segments=24, y_scale=1.0):
    """Return vertices and edges for a flat circle-like widget."""
    vertices = []
    edges = []
    for index in range(segments):
        angle = (index / segments) * 6.283185307179586
        vertices.append((radius * cos(angle), radius * y_scale * sin(angle), 0.0))
        edges.append((index, (index + 1) % segments))
    return vertices, edges


def make_widget_shapes(context, armature_name):
    """Build the custom control shapes used by the generated rig."""
    collection = get_widget_collection(context, armature_name)
    square_vertices = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
    square_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    diamond_vertices = [(0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)]
    diamond_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    body_vertices, body_edges = circle_points(radius=1.0, segments=32, y_scale=1.6)

    return {
        "root": create_widget_object(collection, f"{armature_name}_root_shape", square_vertices, square_edges),
        "body": create_widget_object(collection, f"{armature_name}_body_shape", body_vertices, body_edges),
        "foot": create_widget_object(collection, f"{armature_name}_foot_shape", square_vertices, square_edges),
        "pole": create_widget_object(collection, f"{armature_name}_pole_shape", diamond_vertices, diamond_edges),
    }


def assign_custom_shape(pose_bone, shape, scale_xyz):
    """Assign a custom shape to a pose bone when Blender supports it."""
    pose_bone.custom_shape = shape
    if hasattr(pose_bone, "use_custom_shape_bone_size"):
        pose_bone.use_custom_shape_bone_size = False
    if hasattr(pose_bone, "custom_shape_scale_xyz"):
        pose_bone.custom_shape_scale_xyz = scale_xyz
    else:
        pose_bone.custom_shape_scale = max(scale_xyz)


def assign_control_shapes(context, armature_object, scale):
    """Assign custom widgets to generated control bones."""
    shapes = make_widget_shapes(context, armature_object.name)
    assign_custom_shape(armature_object.pose.bones["root"], shapes["root"], (0.35 * scale, 0.35 * scale, 0.35 * scale))
    assign_custom_shape(armature_object.pose.bones["body"], shapes["body"], (0.55 * scale, 0.35 * scale, 0.55 * scale))

    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        assign_custom_shape(armature_object.pose.bones[names["ik"]], shapes["foot"], (0.22 * scale, 0.16 * scale, 0.22 * scale))
        assign_custom_shape(armature_object.pose.bones[names["pole"]], shapes["pole"], (0.12 * scale, 0.12 * scale, 0.12 * scale))


def assign_bone_groups(armature_object):
    """Color generated control and deform bones in Blender versions that support it."""
    if not hasattr(armature_object.pose, "bone_groups"):
        return

    control_group = armature_object.pose.bone_groups.new(name="QWalk Controls")
    control_group.color_set = "THEME09"
    deform_group = armature_object.pose.bone_groups.new(name="QWalk Deform")
    deform_group.color_set = "THEME04"

    control_names = {"root", "body"}
    for leg in LEG_ORDER:
        control_names.add(STANDARD_LEG_NAMES[leg]["ik"])
        control_names.add(STANDARD_LEG_NAMES[leg]["pole"])

    for pose_bone in armature_object.pose.bones:
        pose_bone.bone_group = control_group if pose_bone.name in control_names else deform_group


def activate_body_control(armature_object):
    """Make the body control active when Blender allows it."""
    try:
        armature_object.data.bones.active = armature_object.data.bones["body"]
    except Exception:
        pass


def apply_standard_mapping(settings):
    """Fill scene settings with the generated armature's bone names."""
    settings.root_bone = "root"
    settings.body_bone = "body"

    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        setattr(settings, IK_FIELDS[leg], names["ik"])
        upper, lower, foot = FK_FIELDS[leg]
        setattr(settings, upper, names["upper"])
        setattr(settings, lower, names["lower"])
        setattr(settings, foot, names["foot"])


def create_standard_quadruped(context, name, scale=1.0, add_ik_constraints=True, display_type="STICK"):
    """Create and return a named quadruped armature object."""
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    armature_data = bpy.data.armatures.new(name)
    armature_object = bpy.data.objects.new(name, armature_data)
    context.collection.objects.link(armature_object)

    bpy.ops.object.select_all(action="DESELECT")
    armature_object.select_set(True)
    context.view_layer.objects.active = armature_object

    armature_data.display_type = display_type
    armature_object.show_in_front = True

    bpy.ops.object.mode_set(mode="EDIT")
    bones = armature_data.edit_bones

    root = add_edit_bone(bones, "root", (-0.18, 0.0, 0.0), (0.18, 0.0, 0.0), scale, deform=False)
    body = add_edit_bone(
        bones,
        "body",
        (0.0, -0.55, 0.92),
        (0.0, 0.55, 0.98),
        scale,
        root,
        deform=False,
    )
    pelvis = add_edit_bone(bones, "pelvis", (0.0, -0.72, 0.90), (0.0, -0.34, 0.92), scale, body)
    spine_01 = add_edit_bone(bones, "spine_01", (0.0, -0.34, 0.92), (0.0, 0.18, 0.97), scale, pelvis, True)
    chest = add_edit_bone(bones, "chest", (0.0, 0.18, 0.97), (0.0, 0.76, 0.98), scale, spine_01, True)
    neck = add_edit_bone(bones, "neck", (0.0, 0.76, 0.98), (0.0, 1.08, 1.12), scale, chest, True)
    add_edit_bone(bones, "head", (0.0, 1.08, 1.12), (0.0, 1.42, 1.06), scale, neck, True)
    tail_01 = add_edit_bone(bones, "tail_01", (0.0, -0.72, 0.90), (0.0, -1.08, 0.95), scale, pelvis)
    add_edit_bone(bones, "tail_02", (0.0, -1.08, 0.95), (0.0, -1.42, 0.84), scale, tail_01, True)

    leg_parents = {"fl": chest, "fr": chest, "rl": pelvis, "rr": pelvis}
    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        side = 1.0 if leg.endswith("l") else -1.0
        is_front = leg.startswith("f")
        x = side * (0.32 if is_front else 0.34)
        y = 0.58 if is_front else -0.58
        upper_z = 0.94 if is_front else 0.86
        knee_y = y - 0.12 if is_front else y - 0.16
        knee_z = 0.52 if is_front else 0.54
        ankle_y = y + 0.02 if is_front else y + 0.10
        ankle_z = 0.17
        toe_y = ankle_y + 0.24
        toe_z = 0.06
        pole_y = y - 0.55 if is_front else y - 0.62

        upper = add_edit_bone(
            bones,
            names["upper"],
            (x, y, upper_z),
            (x, knee_y, knee_z),
            scale,
            leg_parents[leg],
        )
        lower = add_edit_bone(
            bones,
            names["lower"],
            (x, knee_y, knee_z),
            (x, ankle_y, ankle_z),
            scale,
            upper,
            True,
        )
        add_edit_bone(
            bones,
            names["foot"],
            (x, ankle_y, ankle_z),
            (x, toe_y, toe_z),
            scale,
            lower,
            True,
        )
        add_edit_bone(
            bones,
            names["ik"],
            (x, toe_y - 0.11, toe_z),
            (x, toe_y + 0.11, toe_z),
            scale,
            root,
            deform=False,
        )
        add_edit_bone(
            bones,
            names["pole"],
            (x - 0.07 * side, pole_y, knee_z),
            (x + 0.07 * side, pole_y, knee_z),
            scale,
            root,
            deform=False,
        )

    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature_object.pose.bones:
        pose_bone.rotation_mode = "XYZ"

    if add_ik_constraints:
        for leg in LEG_ORDER:
            names = STANDARD_LEG_NAMES[leg]
            constraint = armature_object.pose.bones[names["foot"]].constraints.new(type="IK")
            constraint.name = "QWalk IK"
            constraint.target = armature_object
            constraint.subtarget = names["ik"]
            constraint.pole_target = armature_object
            constraint.pole_subtarget = names["pole"]
            constraint.chain_count = 3
            constraint.iterations = 24

    assign_control_shapes(context, armature_object, scale)
    assign_bone_groups(armature_object)
    activate_body_control(armature_object)
    return armature_object


class QWG_OT_create_quadruped_armature(Operator):
    bl_idname = "qwg.create_quadruped_armature"
    bl_label = "Create Quadruped Armature"
    bl_description = "Create a starter quadruped armature compatible with QWalk"
    bl_options = {"REGISTER", "UNDO"}

    armature_name: StringProperty(
        name="Name",
        description="Name for the generated armature object and data",
        default="QWalk_Quadruped",
    )
    scale: FloatProperty(
        name="Scale",
        description="Overall size multiplier for the generated armature",
        default=1.0,
        min=0.01,
        soft_max=10.0,
    )
    add_ik_constraints: BoolProperty(
        name="Add IK Constraints",
        description="Add IK constraints from lower-leg bones to generated IK targets",
        default=True,
    )
    display_type: EnumProperty(
        name="Display",
        description="Viewport display style for the generated armature",
        items=(
            ("STICK", "Stick", "Clean rig-style display"),
            ("OCTAHEDRAL", "Octahedral", "Classic Blender bone shapes"),
            ("BBONE", "B-Bone", "Thick bendy-bone shapes"),
            ("WIRE", "Wire", "Wireframe bone shapes"),
        ),
        default="STICK",
    )
    map_after_create: BoolProperty(
        name="Map for QWalk",
        description="Fill QWalk bone mapping fields after creating the armature",
        default=True,
    )

    def execute(self, context):
        """Create the standard armature and optionally map it for QWalk."""
        armature = create_standard_quadruped(
            context,
            self.armature_name,
            self.scale,
            self.add_ik_constraints,
            self.display_type,
        )

        if self.map_after_create:
            apply_standard_mapping(context.scene.qwg_settings)

        self.report({"INFO"}, f"Created quadruped armature {armature.name}.")
        return {"FINISHED"}
