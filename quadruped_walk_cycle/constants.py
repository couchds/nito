LEG_ORDER = ("fl", "fr", "rl", "rr")

LEG_LABELS = {
    "fl": "Front Left",
    "fr": "Front Right",
    "rl": "Rear Left",
    "rr": "Rear Right",
}

IK_FIELDS = {
    "fl": "fl_ik_bone",
    "fr": "fr_ik_bone",
    "rl": "rl_ik_bone",
    "rr": "rr_ik_bone",
}

FK_FIELDS = {
    "fl": ("fl_upper_bone", "fl_lower_bone", "fl_foot_bone"),
    "fr": ("fr_upper_bone", "fr_lower_bone", "fr_foot_bone"),
    "rl": ("rl_upper_bone", "rl_lower_bone", "rl_foot_bone"),
    "rr": ("rr_upper_bone", "rr_lower_bone", "rr_foot_bone"),
}
