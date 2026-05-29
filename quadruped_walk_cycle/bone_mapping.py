def normalize_name(name):
    lowered = name.lower()
    return "".join(ch for ch in lowered if ch.isalnum())


def leg_tokens(leg):
    return {
        "fl": {
            "front": ("front", "fore", "arm", "shoulder"),
            "side": ("left", ".l", "_l", "-l", " l"),
            "prefix": ("fl", "lf", "frontl", "lfront", "forel", "lfore"),
        },
        "fr": {
            "front": ("front", "fore", "arm", "shoulder"),
            "side": ("right", ".r", "_r", "-r", " r"),
            "prefix": ("fr", "rf", "frontr", "rfront", "forer", "rfore"),
        },
        "rl": {
            "front": ("rear", "hind", "back", "leg", "thigh", "hip"),
            "side": ("left", ".l", "_l", "-l", " l"),
            "prefix": ("rl", "lr", "lh", "hl", "rearl", "lrear", "hindl", "lhind"),
        },
        "rr": {
            "front": ("rear", "hind", "back", "leg", "thigh", "hip"),
            "side": ("right", ".r", "_r", "-r", " r"),
            "prefix": ("rr", "rh", "hr", "rearr", "rrear", "hindr", "rhind"),
        },
    }[leg]


def kind_tokens(kind):
    return {
        "ik": ("ik", "target", "ctrl", "control", "effector"),
        "upper": ("upper", "thigh", "femur", "humerus", "shoulder", "arm"),
        "lower": ("lower", "shin", "calf", "tibia", "forearm", "radius", "ulna"),
        "foot": ("foot", "paw", "hoof", "ankle", "toe", "tarsal"),
        "root": ("root", "master", "global", "cog", "center"),
        "body": ("body", "hips", "pelvis", "spine", "chest", "torso"),
    }[kind]


def score_bone_name(name, leg=None, kind=None):
    raw = name.lower()
    norm = normalize_name(name)
    score = 0

    if leg:
        tokens = leg_tokens(leg)
        if any(token in raw for token in tokens["front"]) or any(token in norm for token in tokens["prefix"]):
            score += 5
        if (
            any(token in raw for token in tokens["side"])
            or ("left" in norm and leg.endswith("l"))
            or ("right" in norm and leg.endswith("r"))
        ):
            score += 4
        if any(norm.startswith(token) or norm.endswith(token) for token in tokens["prefix"]):
            score += 3

    if kind:
        if any(token in raw or token in norm for token in kind_tokens(kind)):
            score += 6
        if kind == "ik" and any(token in raw for token in ("pole", "roll", "twist")):
            score -= 6
        if kind in {"upper", "lower", "foot"} and "ik" in norm:
            score -= 4

    return score


def find_best_bone(names, leg=None, kind=None, minimum=8):
    scored = sorted(
        ((score_bone_name(name, leg=leg, kind=kind), name) for name in names),
        key=lambda item: (item[0], -len(item[1])),
        reverse=True,
    )
    if scored and scored[0][0] >= minimum:
        return scored[0][1]
    return ""
