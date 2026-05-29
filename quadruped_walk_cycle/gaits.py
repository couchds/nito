import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Gait:
    label: str
    phases: dict
    duty_factor: float
    body_bobs_per_cycle: int


GAITS = {
    "WALK": Gait(
        label="Walk",
        phases={"fl": 0.00, "rr": 0.25, "fr": 0.50, "rl": 0.75},
        duty_factor=0.68,
        body_bobs_per_cycle=4,
    ),
    "TROT": Gait(
        label="Trot",
        phases={"fl": 0.00, "rr": 0.00, "fr": 0.50, "rl": 0.50},
        duty_factor=0.52,
        body_bobs_per_cycle=2,
    ),
    "PACE": Gait(
        label="Pace",
        phases={"fl": 0.00, "rl": 0.00, "fr": 0.50, "rr": 0.50},
        duty_factor=0.55,
        body_bobs_per_cycle=2,
    ),
    "BOUND": Gait(
        label="Bound",
        phases={"rl": 0.00, "rr": 0.00, "fl": 0.50, "fr": 0.50},
        duty_factor=0.45,
        body_bobs_per_cycle=2,
    ),
}


def smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def lerp(start, end, amount):
    return start + (end - start) * amount


def cycle_position(frame, start, end):
    duration = max(1.0, float(end - start))
    return ((float(frame) - float(start)) / duration) % 1.0


def leg_motion(cycle_pos, phase, duty_factor, stride_length, step_height):
    foot_phase = (cycle_pos + phase) % 1.0
    swing_fraction = max(0.05, 1.0 - duty_factor)

    if foot_phase < swing_fraction:
        swing_t = smoothstep(foot_phase / swing_fraction)
        forward = lerp(-stride_length * 0.5, stride_length * 0.5, swing_t)
        lift = math.sin(math.pi * swing_t) * step_height
    else:
        stance_t = (foot_phase - swing_fraction) / max(0.05, duty_factor)
        forward = lerp(stride_length * 0.5, -stride_length * 0.5, stance_t)
        lift = 0.0

    return forward, lift, foot_phase < swing_fraction
