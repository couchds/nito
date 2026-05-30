bl_info = {
    "name": "Quadruped Walk Cycle Generator",
    "author": "couchds",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > QWalk",
    "description": "Generate looping quadruped walk cycles for an armature using IK controls or FK leg chains.",
    "category": "Animation",
}

import bpy
import sys
from importlib import reload

from bpy.props import PointerProperty

MODULE_NAMES = (
    "constants",
    "gaits",
    "bone_mapping",
    "rig_utils",
    "properties",
    "skeleton",
    "operators",
    "ui",
)

for module_name in MODULE_NAMES:
    module = sys.modules.get(f"{__name__}.{module_name}")
    if module:
        reload(module)

from .operators import (
    QWG_OT_auto_map,
    QWG_OT_clear_cycle_keys,
    QWG_OT_generate_walk_cycle,
    QWG_OT_set_base_pose,
)
from .properties import QWG_Settings
from .skeleton import QWG_OT_create_fitted_quadruped_armature, QWG_OT_create_quadruped_armature
from .ui import QWG_PT_panel


CLASSES = (
    QWG_Settings,
    QWG_OT_create_quadruped_armature,
    QWG_OT_create_fitted_quadruped_armature,
    QWG_OT_auto_map,
    QWG_OT_generate_walk_cycle,
    QWG_OT_clear_cycle_keys,
    QWG_OT_set_base_pose,
    QWG_PT_panel,
)


def register():
    """Register Blender classes and attach add-on settings to the scene."""
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.qwg_settings = PointerProperty(type=QWG_Settings)


def unregister():
    """Remove scene settings and unregister Blender classes."""
    if hasattr(bpy.types.Scene, "qwg_settings"):
        del bpy.types.Scene.qwg_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
