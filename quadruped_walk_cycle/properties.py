from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from .rig_utils import axis_items


class QWG_Settings(PropertyGroup):
    frame_start: IntProperty(
        name="Start",
        description="First frame of the generated loop",
        default=1,
        min=0,
    )
    frame_end: IntProperty(
        name="End",
        description="Last frame of the generated loop",
        default=25,
        min=1,
    )
    key_step: IntProperty(
        name="Key Every",
        description="Frame spacing between generated keys",
        default=2,
        min=1,
        max=24,
    )
    gait: EnumProperty(
        name="Gait",
        description="Footfall pattern to generate",
        items=(
            ("WALK", "Walk", "Four-beat walk"),
            ("TROT", "Trot", "Diagonal two-beat trot"),
            ("PACE", "Pace", "Lateral two-beat pace"),
            ("BOUND", "Bound", "Rear pair then front pair"),
        ),
        default="WALK",
    )
    generation_mode: EnumProperty(
        name="Mode",
        description="Use IK target bones when available, FK chains otherwise",
        items=(
            ("AUTO", "Auto", "Prefer IK targets; fall back to FK chains"),
            ("IK", "IK Targets", "Animate foot or paw IK target/control bones"),
            ("FK", "FK Chains", "Animate upper, lower, and foot bones directly"),
        ),
        default="AUTO",
    )
    forward_axis: EnumProperty(
        name="Forward",
        description="Local axis used as the animal's forward direction",
        items=axis_items(),
        default="Y",
    )
    side_axis: EnumProperty(
        name="Side",
        description="Local axis used for side-to-side body motion",
        items=axis_items(),
        default="X",
    )
    up_axis: EnumProperty(
        name="Up",
        description="Local axis used as vertical lift",
        items=axis_items(),
        default="Z",
    )
    fk_bend_axis: EnumProperty(
        name="FK Bend",
        description="Local Euler axis used when rotating FK leg bones",
        items=axis_items(),
        default="X",
    )
    stride_length: FloatProperty(
        name="Stride",
        description="Forward/back distance for foot targets",
        default=0.65,
        min=0.0,
        soft_max=5.0,
        unit="LENGTH",
    )
    step_height: FloatProperty(
        name="Lift",
        description="Vertical foot lift during the swing phase",
        default=0.22,
        min=0.0,
        soft_max=2.0,
        unit="LENGTH",
    )
    body_bob: FloatProperty(
        name="Body Bob",
        description="Vertical body motion",
        default=0.04,
        min=0.0,
        soft_max=1.0,
        unit="LENGTH",
    )
    body_sway: FloatProperty(
        name="Body Sway",
        description="Side-to-side body motion",
        default=0.02,
        min=0.0,
        soft_max=1.0,
        unit="LENGTH",
    )
    body_pitch: FloatProperty(
        name="Pitch Deg",
        description="Forward/back body rotation in degrees",
        default=2.0,
        min=0.0,
        soft_max=20.0,
    )
    body_roll: FloatProperty(
        name="Roll Deg",
        description="Side-to-side body rotation in degrees",
        default=1.5,
        min=0.0,
        soft_max=20.0,
    )
    fk_swing_degrees: FloatProperty(
        name="FK Swing Deg",
        description="Maximum FK upper-leg swing in degrees",
        default=16.0,
        min=0.0,
        soft_max=60.0,
    )
    fk_lift_degrees: FloatProperty(
        name="FK Lift Deg",
        description="Maximum FK lower-leg bend in degrees during swing",
        default=22.0,
        min=0.0,
        soft_max=90.0,
    )
    replace_existing: BoolProperty(
        name="Replace Keys",
        description="Remove existing location and Euler rotation keys on mapped bones in the generated frame range",
        default=True,
    )
    add_cycles: BoolProperty(
        name="Loop F-Curves",
        description="Add cycles modifiers to generated animation curves",
        default=True,
    )
    interpolation: EnumProperty(
        name="Interpolation",
        description="Interpolation used for generated keyframes",
        items=(
            ("BEZIER", "Bezier", ""),
            ("SINE", "Sine", ""),
            ("LINEAR", "Linear", ""),
        ),
        default="SINE",
    )

    root_bone: StringProperty(name="Root")
    body_bone: StringProperty(name="Body")

    fl_ik_bone: StringProperty(name="Front Left IK")
    fr_ik_bone: StringProperty(name="Front Right IK")
    rl_ik_bone: StringProperty(name="Rear Left IK")
    rr_ik_bone: StringProperty(name="Rear Right IK")

    fl_upper_bone: StringProperty(name="FL Upper")
    fl_lower_bone: StringProperty(name="FL Lower")
    fl_foot_bone: StringProperty(name="FL Foot")

    fr_upper_bone: StringProperty(name="FR Upper")
    fr_lower_bone: StringProperty(name="FR Lower")
    fr_foot_bone: StringProperty(name="FR Foot")

    rl_upper_bone: StringProperty(name="RL Upper")
    rl_lower_bone: StringProperty(name="RL Lower")
    rl_foot_bone: StringProperty(name="RL Foot")

    rr_upper_bone: StringProperty(name="RR Upper")
    rr_lower_bone: StringProperty(name="RR Lower")
    rr_foot_bone: StringProperty(name="RR Foot")
