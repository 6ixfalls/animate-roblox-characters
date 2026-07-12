"""Blender-only smoke test for changing R6 preview frames; does not save the blend."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "animate-roblox-characters" / "scripts"))

import bpy  # type: ignore

from animation_tools import render_animation_preview_frames


def main() -> int:
    output = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else Path("/tmp/r6-preview-smoke")
    armature = bpy.data.objects["__PrimaryArmature"]
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    control = armature.pose.bones["LeftArm_FK"]
    control.rotation_mode = "XYZ"
    for frame, angle in ((1, -12.0), (2, 16.0), (3, -4.0)):
        control.rotation_euler.z = math.radians(angle)
        control.keyframe_insert(data_path="rotation_euler", frame=frame, group=control.name)
    result = render_animation_preview_frames(
        armature.name,
        output,
        1,
        3,
        "r6-motion",
        False,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
