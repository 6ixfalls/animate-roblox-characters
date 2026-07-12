#!/usr/bin/env python3
"""Deterministic Blender helpers for Roblox character animation workflows.

Import this module inside Blender through MCP Python execution. Public helpers
return JSON-serializable dictionaries and never silently pass an unavailable
verification step.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from authentic_rig import export_rbxanim, inspect_authenticity  # noqa: E402


R15_REQUIRED = {
    "Root",
    "HumanoidRootNode",
    "LowerTorso",
    "UpperTorso",
    "Head",
    "LeftUpperArm",
    "LeftLowerArm",
    "LeftHand",
    "RightUpperArm",
    "RightLowerArm",
    "RightHand",
    "LeftUpperLeg",
    "LeftLowerLeg",
    "LeftFoot",
    "RightUpperLeg",
    "RightLowerLeg",
    "RightFoot",
}

R6_REQUIRED = {
    "Torso",
    "Head",
    "Left Arm",
    "Right Arm",
    "Left Leg",
    "Right Leg",
}


def detect_rig_type(bone_names: Iterable[str]) -> str:
    names = set(bone_names)
    if R15_REQUIRED.issubset(names):
        return "R15"
    if R6_REQUIRED.issubset(names) and ({"Root", "HumanoidRootPart"} & names):
        return "R6"
    return "CUSTOM"


def _require_blender():
    try:
        import bpy  # type: ignore
        from mathutils import Vector  # type: ignore
    except ImportError as exc:  # pragma: no cover - Blender-only path
        raise RuntimeError("Run animation_tools.py inside Blender") from exc
    return bpy, Vector


def _set_available_render_engine(scene) -> str:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            return engine
        except TypeError:
            continue
    raise RuntimeError("No supported Blender render engine is available")


def _as_list(values) -> list[float]:
    return [round(float(value), 8) for value in values]


def _error(message: str, **extra) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "rig_type": None,
        "armature": None,
        "bones": {},
        "metrics": {},
        "artifacts": {},
        "warnings": [],
        "errors": [message],
    }
    result.update(extra)
    return result


def _armature_candidates(bpy):
    return sorted((obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"), key=lambda obj: obj.name)


def _select_armature(bpy, armature_name: str | None = None):
    if armature_name:
        obj = bpy.data.objects.get(armature_name)
        if obj is None or obj.type != "ARMATURE":
            raise ValueError(f"Armature not found: {armature_name}")
        return obj
    active = bpy.context.view_layer.objects.active
    if active and active.type == "ARMATURE":
        return active
    candidates = _armature_candidates(bpy)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError("No armature exists in the current scene")
    names = ", ".join(obj.name for obj in candidates)
    raise ValueError(f"Multiple armatures are available; specify one: {names}")


def _activate_pose_mode(bpy, armature) -> None:
    active = bpy.context.view_layer.objects.active
    if active and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")


def _constraint_snapshot(constraint) -> dict[str, Any]:
    data = {"name": constraint.name, "type": constraint.type, "mute": bool(constraint.mute)}
    target = getattr(constraint, "target", None)
    if target is not None:
        data["target"] = target.name
    subtarget = getattr(constraint, "subtarget", "")
    if subtarget:
        data["subtarget"] = subtarget
    pole_target = getattr(constraint, "pole_target", None)
    if pole_target is not None:
        data["pole_target"] = pole_target.name
    pole_subtarget = getattr(constraint, "pole_subtarget", "")
    if pole_subtarget:
        data["pole_subtarget"] = pole_subtarget
    return data


def _bone_snapshot(armature, pose_bone) -> dict[str, Any]:
    rotation = pose_bone.rotation_euler
    if pose_bone.rotation_mode == "QUATERNION":
        rotation = pose_bone.rotation_quaternion.to_euler("XYZ")
    elif pose_bone.rotation_mode == "AXIS_ANGLE":
        rotation = pose_bone.matrix_basis.to_euler("XYZ")
    head_world = armature.matrix_world @ pose_bone.head
    tail_world = armature.matrix_world @ pose_bone.tail
    return {
        "parent": pose_bone.parent.name if pose_bone.parent else None,
        "deform": bool(pose_bone.bone.use_deform),
        "rotation_mode": pose_bone.rotation_mode,
        "location": _as_list(pose_bone.location),
        "rotation_degrees": _as_list(math.degrees(value) for value in rotation),
        "scale": _as_list(pose_bone.scale),
        "head_world": _as_list(head_world),
        "tail_world": _as_list(tail_world),
        "matrix_basis": [_as_list(row) for row in pose_bone.matrix_basis],
        "constraints": [_constraint_snapshot(constraint) for constraint in pose_bone.constraints],
    }


def _action_fcurves(action) -> list[Any]:
    """Return curves from legacy or Blender 4.4+/5.x layered Actions."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return list(legacy)
    curves = []
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                curves.extend(channelbag.fcurves)
    return curves


def _mesh_animation_paths(bpy) -> list[str]:
    offenders: list[str] = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.animation_data or not obj.animation_data.action:
            continue
        for curve in _action_fcurves(obj.animation_data.action):
            offenders.append(f"{obj.name}:{curve.data_path}[{curve.array_index}]")
    return sorted(offenders)


def inspect_scene(armature_name: str | None = None) -> dict[str, Any]:
    """Inspect all armatures and return exact selected-rig pose data."""
    bpy, _Vector = _require_blender()
    candidates = _armature_candidates(bpy)
    summaries = []
    for armature in candidates:
        names = [bone.name for bone in armature.data.bones]
        summaries.append(
            {
                "name": armature.name,
                "rig_type": detect_rig_type(names),
                "bones": names,
                "action": armature.animation_data.action.name
                if armature.animation_data and armature.animation_data.action
                else None,
            }
        )
    if not candidates:
        return _error("No armature exists in the current scene", metrics={"armatures": []})
    try:
        armature = _select_armature(bpy, armature_name)
    except ValueError as exc:
        return _error(str(exc), metrics={"armatures": summaries})

    snapshots = {pose_bone.name: _bone_snapshot(armature, pose_bone) for pose_bone in armature.pose.bones}
    names = list(snapshots)
    actions = sorted(action.name for action in bpy.data.actions)
    return {
        "ok": True,
        "rig_type": detect_rig_type(names),
        "armature": armature.name,
        "bones": snapshots,
        "metrics": {
            "armatures": summaries,
            "actions": actions,
            "active_action": armature.animation_data.action.name
            if armature.animation_data and armature.animation_data.action
            else None,
            "frame": int(bpy.context.scene.frame_current),
            "fps": int(bpy.context.scene.render.fps),
            "mesh_animation_curves": _mesh_animation_paths(bpy),
            "mode": armature.mode,
            "authenticity": inspect_authenticity(armature),
        },
        "artifacts": {},
        "warnings": [],
        "errors": [],
    }


def _ensure_action(bpy, armature, action_name: str | None):
    if armature.animation_data is None:
        armature.animation_data_create()
    action = armature.animation_data.action
    if action_name:
        action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
        armature.animation_data.action = action
    elif action is None:
        action = bpy.data.actions.new("RobloxAnimation")
        armature.animation_data.action = action
    return action


def _set_frame_interpolation(action, frame: float, interpolation: str) -> int:
    changed = 0
    for curve in _action_fcurves(action):
        if not curve.data_path.startswith('pose.bones["'):
            continue
        for point in curve.keyframe_points:
            if abs(float(point.co.x) - float(frame)) < 1e-5:
                point.interpolation = interpolation
                changed += 1
    return changed


def apply_pose(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply and key one pose batch, then inspect and optionally render it."""
    bpy, _Vector = _require_blender()
    try:
        armature = _select_armature(bpy, payload.get("armature"))
        frame = int(payload["frame"])
        bone_changes = payload["bones"]
    except (KeyError, TypeError, ValueError) as exc:
        return _error(f"Invalid pose payload: {exc}")
    if not isinstance(bone_changes, dict) or not bone_changes:
        return _error("Pose payload must contain a non-empty bones mapping")

    authenticity = inspect_authenticity(armature)
    if not authenticity["authentic_ready"]:
        return _error(
            "Refusing to animate an unverified rig. Use the pinned premade R6 V2.22 asset or an authentic "
            "Roblox Studio-derived R6/R15 target.",
            armature=armature.name,
            metrics={"authenticity": authenticity},
        )

    missing = sorted(name for name in bone_changes if name not in armature.pose.bones)
    if missing:
        return _error(f"Unknown pose bones: {', '.join(missing)}", armature=armature.name)

    _activate_pose_mode(bpy, armature)
    scene = bpy.context.scene
    scene.frame_set(frame)
    action = _ensure_action(bpy, armature, payload.get("action"))
    keyed_channels = []

    for bone_name, changes in bone_changes.items():
        pose_bone = armature.pose.bones[bone_name]
        if "location" in changes:
            pose_bone.location = changes["location"]
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=bone_name)
            keyed_channels.append(f"{bone_name}.location")
        if "rotation_degrees" in changes:
            rotation_mode = changes.get("rotation_mode", "XYZ")
            pose_bone.rotation_mode = rotation_mode
            pose_bone.rotation_euler = [math.radians(float(value)) for value in changes["rotation_degrees"]]
            pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone_name)
            keyed_channels.append(f"{bone_name}.rotation_euler")
        if "scale" in changes:
            pose_bone.scale = changes["scale"]
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)
            keyed_channels.append(f"{bone_name}.scale")
        if not ({"location", "rotation_degrees", "scale"} & set(changes)):
            return _error(f"No supported transform supplied for {bone_name}", armature=armature.name)

    interpolation = str(payload.get("interpolation", "CONSTANT")).upper()
    if interpolation not in {"CONSTANT", "BEZIER"}:
        return _error("Interpolation must be CONSTANT or BEZIER", armature=armature.name)
    changed_points = _set_frame_interpolation(action, frame, interpolation)
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    snapshots = {name: _bone_snapshot(armature, armature.pose.bones[name]) for name in bone_changes}

    artifacts: dict[str, Any] = {}
    warnings: list[str] = []
    render_directory = payload.get("render_directory")
    if render_directory:
        review = render_pose_views(
            armature_name=armature.name,
            output_directory=render_directory,
            pose_label=str(payload.get("pose_label", f"frame-{frame}")),
            frame=frame,
        )
        if review["ok"]:
            artifacts.update(review["artifacts"])
        else:
            warnings.extend(review["errors"])
    else:
        warnings.append("Front/side review was not rendered because render_directory was omitted")

    return {
        "ok": not warnings,
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": snapshots,
        "metrics": {
            "frame": frame,
            "keyed_channels": keyed_channels,
            "keyframe_points_updated": changed_points,
            "interpolation": interpolation,
            "action": action.name,
            "authenticity": authenticity,
        },
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": [],
    }


def _driven_meshes(bpy, armature):
    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        driven = obj.parent == armature or any(
            modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers
        )
        if driven:
            meshes.append(obj)
    return meshes


def _bounds_for_rig(bpy, armature, Vector):
    points = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in _driven_meshes(bpy, armature):
        evaluated = obj.evaluated_get(depsgraph)
        points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not points:
        for pose_bone in armature.pose.bones:
            if pose_bone.bone.use_deform:
                points.extend((armature.matrix_world @ pose_bone.head, armature.matrix_world @ pose_bone.tail))
    if not points:
        raise ValueError("Unable to calculate rig bounds")
    minimum = Vector((min(point[i] for point in points) for i in range(3)))
    maximum = Vector((max(point[i] for point in points) for i in range(3)))
    return minimum, maximum


def _review_collection(bpy):
    collection = bpy.data.collections.get("Review")
    if collection is None:
        collection = bpy.data.collections.new("Review")
        bpy.context.scene.collection.children.link(collection)
    return collection


def _look_at(obj, target) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _ensure_camera(bpy, name: str, collection):
    camera = bpy.data.objects.get(name)
    if camera is not None and camera.type != "CAMERA":
        raise ValueError(f"Review object {name} exists but is not a camera")
    if camera is None:
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        collection.objects.link(camera)
    camera.data.type = "ORTHO"
    return camera


def _ensure_review_lighting(bpy, collection, center) -> None:
    if any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        return
    for name, offset, energy in (
        ("Review_Key", (4, -6, 7), 900),
        ("Review_Fill", (-4, -2, 3), 500),
    ):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = 4.0
        light = bpy.data.objects.new(name, data)
        collection.objects.link(light)
        light.location = center + type(center)(offset)
        _look_at(light, center)


def render_pose_views(
    armature_name: str | None,
    output_directory: str | Path,
    pose_label: str,
    frame: int | None = None,
) -> dict[str, Any]:
    """Render deterministic front and side review images for the current pose."""
    bpy, Vector = _require_blender()
    try:
        armature = _select_armature(bpy, armature_name)
        output_dir = Path(output_directory).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        if frame is not None:
            bpy.context.scene.frame_set(int(frame))
        minimum, maximum = _bounds_for_rig(bpy, armature, Vector)
    except (OSError, ValueError) as exc:
        return _error(f"Unable to prepare review renders: {exc}", armature=armature_name)

    center = (minimum + maximum) * 0.5
    dimensions = maximum - minimum
    ortho_scale = max(float(dimensions.z) * 1.18, float(dimensions.x) * 1.45, float(dimensions.y) * 1.45, 4.0)
    distance = max(10.0, ortho_scale * 1.8)
    collection = _review_collection(bpy)
    front = _ensure_camera(bpy, "Review_Front", collection)
    side = _ensure_camera(bpy, "Review_Side", collection)
    authenticity = inspect_authenticity(armature)
    front_y = distance if authenticity["source"] == "community-r6-ik-fk-control-rig" else -distance
    front.location = center + Vector((0, front_y, 0))
    side.location = center + Vector((distance, 0, 0))
    front.data.ortho_scale = ortho_scale
    side.data.ortho_scale = ortho_scale
    _look_at(front, center)
    _look_at(side, center)
    _ensure_review_lighting(bpy, collection, center)

    scene = bpy.context.scene
    previous = {
        "camera": scene.camera,
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "engine": scene.render.engine,
    }

    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "-", pose_label).strip("-") or "pose"
    frame_number = int(scene.frame_current)
    artifacts = {}
    errors = []
    try:
        _set_available_render_engine(scene)
        scene.render.resolution_x = 512
        scene.render.resolution_y = 512
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        for view_name, camera in (("front", front), ("side", side)):
            path = output_dir / f"{safe_label}-f{frame_number:04d}-{view_name}.png"
            scene.camera = camera
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"Render did not produce {view_name} image")
            else:
                artifacts[view_name] = str(path)
    except Exception as exc:  # Blender operators raise implementation-specific errors
        errors.append(f"Review render failed: {exc}")
    finally:
        scene.camera = previous["camera"]
        scene.render.filepath = previous["filepath"]
        scene.render.resolution_x = previous["resolution_x"]
        scene.render.resolution_y = previous["resolution_y"]
        scene.render.resolution_percentage = previous["resolution_percentage"]
        scene.render.engine = previous["engine"]

    return {
        "ok": not errors and set(artifacts) == {"front", "side"},
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": {},
        "metrics": {"frame": frame_number, "ortho_scale": round(ortho_scale, 6)},
        "artifacts": artifacts,
        "warnings": [],
        "errors": errors,
    }


def _ensure_area_light(bpy, collection, name: str, location, target, energy: float, size: float, color):
    light = bpy.data.objects.get(name)
    if light is not None and light.type != "LIGHT":
        raise ValueError(f"Review object {name} exists but is not a light")
    if light is None:
        data = bpy.data.lights.new(name, type="AREA")
        light = bpy.data.objects.new(name, data)
        collection.objects.link(light)
    light.data.type = "AREA"
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.data.color = color
    light.location = location
    _look_at(light, target)
    return light


def render_animation_preview_frames(
    armature_name: str | None,
    output_directory: str | Path,
    frame_start: int,
    frame_end: int,
    filename_prefix: str = "animation",
    exclude_duplicated_closing_frame: bool = False,
    camera_location: Iterable[float] | None = None,
    look_target: Iterable[float] | None = None,
    ortho_scale: float | None = None,
    resolution: int = 512,
) -> dict[str, Any]:
    """Render sequential RGB PNGs for a final GIF after animation export."""
    bpy, Vector = _require_blender()
    try:
        armature = _select_armature(bpy, armature_name)
        authenticity = inspect_authenticity(armature)
        if not authenticity["authentic_ready"]:
            raise ValueError("Preview rendering requires a verified authentic Roblox rig")
        output_dir = Path(output_directory).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        start = int(frame_start)
        end = int(frame_end)
        if end < start:
            raise ValueError("frame_end must be greater than or equal to frame_start")
        frames = list(range(start, end + 1))
        if exclude_duplicated_closing_frame:
            if len(frames) < 2:
                raise ValueError("Cannot exclude a closing frame from a one-frame preview")
            frames = frames[:-1]
        safe_prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", filename_prefix).strip("-") or "animation"
    except (OSError, TypeError, ValueError) as exc:
        return _error(f"Unable to prepare animation preview frames: {exc}", armature=armature_name)

    is_r6_v222 = authenticity["source"] == "community-r6-ik-fk-control-rig"
    if camera_location is None or look_target is None:
        if not is_r6_v222:
            return _error(
                "Non-R6-V2.22 preview requires camera_location and look_target chosen after visual forward-axis inspection",
                armature=armature.name,
            )
        # R6 V2.22 faces Blender +Y. This is the proven three-quarter-front view.
        camera_position = Vector((6.8, 8.8, 4.8))
        target = Vector((0.0, 0.0, 2.55))
        scale = 6.4 if ortho_scale is None else float(ortho_scale)
    else:
        camera_position = Vector(tuple(float(value) for value in camera_location))
        target = Vector(tuple(float(value) for value in look_target))
        if len(camera_position) != 3 or len(target) != 3:
            return _error("Preview camera and target must contain three coordinates", armature=armature.name)
        if ortho_scale is None:
            return _error("Non-default preview cameras require an explicit ortho_scale", armature=armature.name)
        scale = float(ortho_scale)
    if resolution < 64 or resolution > 4096 or scale <= 0:
        return _error("Preview resolution or orthographic scale is invalid", armature=armature.name)

    collection = _review_collection(bpy)
    camera = _ensure_camera(bpy, "Review_GIF_Camera", collection)
    camera.location = camera_position
    camera.data.ortho_scale = scale
    _look_at(camera, target)
    review_lights = [
        _ensure_area_light(bpy, collection, "Review_GIF_Key", target + Vector((4.5, 5.5, 6.5)), target, 1000, 4.0, (1.0, 0.88, 0.78)),
        _ensure_area_light(bpy, collection, "Review_GIF_Fill", target + Vector((-4.0, 3.0, 3.5)), target, 450, 5.0, (0.68, 0.78, 1.0)),
        _ensure_area_light(bpy, collection, "Review_GIF_Rim", target + Vector((-2.5, -5.0, 6.0)), target, 800, 3.0, (0.75, 0.85, 1.0)),
    ]

    scene = bpy.context.scene
    previous = {
        "camera": scene.camera,
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "engine": scene.render.engine,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "frame": int(scene.frame_current),
        "world_color": tuple(scene.world.color) if scene.world else None,
    }
    non_review_light_states = [
        (obj, obj.hide_render)
        for obj in bpy.context.scene.objects
        if obj.type == "LIGHT" and obj not in review_lights
    ]
    rendered = []
    errors = []
    try:
        for light, _hidden in non_review_light_states:
            light.hide_render = True
        _set_available_render_engine(scene)
        scene.camera = camera
        scene.render.resolution_x = int(resolution)
        scene.render.resolution_y = int(resolution)
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        if scene.world:
            scene.world.color = (0.035, 0.035, 0.05)
        for frame in frames:
            scene.frame_set(frame)
            path = output_dir / f"{safe_prefix}_{frame:04d}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"Preview render failed to create frame {frame}")
                break
            rendered.append(str(path))
    except Exception as exc:
        errors.append(f"Animation preview rendering failed: {exc}")
    finally:
        for light, hidden in non_review_light_states:
            light.hide_render = hidden
        scene.camera = previous["camera"]
        scene.render.filepath = previous["filepath"]
        scene.render.resolution_x = previous["resolution_x"]
        scene.render.resolution_y = previous["resolution_y"]
        scene.render.resolution_percentage = previous["resolution_percentage"]
        scene.render.engine = previous["engine"]
        scene.render.image_settings.file_format = previous["file_format"]
        scene.render.image_settings.color_mode = previous["color_mode"]
        scene.frame_set(previous["frame"])
        if scene.world and previous["world_color"] is not None:
            scene.world.color = previous["world_color"]

    return {
        "ok": not errors and len(rendered) == len(frames),
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": {},
        "metrics": {
            "frames": frames,
            "frame_count": len(rendered),
            "resolution": [resolution, resolution],
            "camera_location": _as_list(camera.location),
            "look_target": _as_list(target),
            "ortho_scale": scale,
            "r6_v222_plus_y_default": is_r6_v222 and camera_location is None,
            "review_collection": collection.name,
            "authenticity": authenticity,
        },
        "artifacts": {"frames": rendered, "directory": str(output_dir)},
        "warnings": [],
        "errors": errors,
    }
def polish_curves(armature_name: str | None = None, action_name: str | None = None) -> dict[str, Any]:
    """Convert all pose-bone keys in the active action to polished Bezier curves."""
    bpy, _Vector = _require_blender()
    try:
        armature = _select_armature(bpy, armature_name)
    except ValueError as exc:
        return _error(str(exc), armature=armature_name)
    action = bpy.data.actions.get(action_name) if action_name else None
    if action is None and armature.animation_data:
        action = armature.animation_data.action
    if action is None:
        return _error("No action is available to polish", armature=armature.name)

    curves = 0
    points = 0
    skipped = []
    curves_for_action = _action_fcurves(action)
    for curve in curves_for_action:
        if not curve.data_path.startswith('pose.bones["'):
            skipped.append(f"{curve.data_path}[{curve.array_index}]")
            continue
        curves += 1
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"
            points += 1
        curve.update()
    linear_remaining = sum(
        1
        for curve in curves_for_action
        if curve.data_path.startswith('pose.bones["')
        for point in curve.keyframe_points
        if point.interpolation == "LINEAR"
    )
    return {
        "ok": curves > 0 and linear_remaining == 0 and not skipped,
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": {},
        "metrics": {
            "action": action.name,
            "curves_polished": curves,
            "keyframes_polished": points,
            "linear_remaining": linear_remaining,
            "non_pose_curves": skipped,
        },
        "artifacts": {},
        "warnings": [],
        "errors": [] if curves > 0 and not skipped else ["Action is empty or contains non-pose curves"],
    }


def _endpoint_metrics(bpy, armature, start: int, end: int):
    current = int(bpy.context.scene.frame_current)
    snapshots = {}
    for frame in (start, end):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        snapshots[frame] = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in armature.pose.bones
            if pose_bone.bone.use_deform
        }
    bpy.context.scene.frame_set(current)
    max_location = 0.0
    max_rotation = 0.0
    worst_location = None
    worst_rotation = None
    for bone_name in snapshots[start]:
        start_location, start_rotation, _start_scale = snapshots[start][bone_name].decompose()
        end_location, end_rotation, _end_scale = snapshots[end][bone_name].decompose()
        location_difference = (end_location - start_location).length
        rotation_difference = math.degrees(start_rotation.rotation_difference(end_rotation).angle)
        if location_difference > max_location:
            max_location = location_difference
            worst_location = bone_name
        if rotation_difference > max_rotation:
            max_rotation = rotation_difference
            worst_rotation = bone_name
    return {
        "location_difference": round(max_location, 8),
        "rotation_difference_degrees": round(max_rotation, 8),
        "worst_location_bone": worst_location,
        "worst_rotation_bone": worst_rotation,
    }


def _contact_drift(bpy, armature, contact_intervals: dict[str, Any]):
    current = int(bpy.context.scene.frame_current)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    results = {}
    errors = []
    for bone_name, intervals in contact_intervals.items():
        if bone_name not in armature.pose.bones:
            errors.append(f"Unknown contact bone: {bone_name}")
            continue
        bone_results = []
        for interval in intervals:
            if len(interval) != 2:
                errors.append(f"Invalid contact interval for {bone_name}: {interval}")
                continue
            start, end = int(interval[0]), int(interval[1])
            positions = []
            for frame in range(start, end + 1):
                bpy.context.scene.frame_set(frame)
                evaluated = armature.evaluated_get(depsgraph)
                pose_bone = evaluated.pose.bones[bone_name]
                positions.append(evaluated.matrix_world @ pose_bone.tail)
            origin = positions[0]
            max_drift = max((position - origin).length for position in positions)
            bone_results.append({"start": start, "end": end, "max_drift": round(float(max_drift), 8)})
        results[bone_name] = bone_results
    bpy.context.scene.frame_set(current)
    return results, errors


def audit_action(
    armature_name: str | None = None,
    action_name: str | None = None,
    loop_start: int | None = None,
    loop_end: int | None = None,
    contact_intervals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit hierarchy-safe curves, interpolation, loop seam, and foot drift."""
    bpy, _Vector = _require_blender()
    try:
        armature = _select_armature(bpy, armature_name)
    except ValueError as exc:
        return _error(str(exc), armature=armature_name)
    action = bpy.data.actions.get(action_name) if action_name else None
    if action is None and armature.animation_data:
        action = armature.animation_data.action
    if action is None:
        return _error("No action is available to audit", armature=armature.name)

    curves_for_action = _action_fcurves(action)
    non_pose_curves = [
        f"{curve.data_path}[{curve.array_index}]"
        for curve in curves_for_action
        if not curve.data_path.startswith('pose.bones["')
    ]
    interpolation = {"BEZIER": 0, "LINEAR": 0, "CONSTANT": 0, "OTHER": 0}
    for curve in curves_for_action:
        for point in curve.keyframe_points:
            key = point.interpolation if point.interpolation in interpolation else "OTHER"
            interpolation[key] += 1

    mesh_curves = _mesh_animation_paths(bpy)
    metrics: dict[str, Any] = {
        "action": action.name,
        "curve_count": len(curves_for_action),
        "interpolation": interpolation,
        "non_pose_curves": non_pose_curves,
        "mesh_animation_curves": mesh_curves,
    }
    errors = []
    warnings = []
    if non_pose_curves:
        errors.append("The armature action contains non-pose-bone curves")
    if mesh_curves:
        errors.append("One or more mesh objects contain animation curves")
    if interpolation["LINEAR"]:
        errors.append("Final action contains LINEAR keyframes")
    if interpolation["CONSTANT"]:
        errors.append("Final action still contains CONSTANT blocking keyframes")
    if not curves_for_action:
        errors.append("The action contains no curves")

    if loop_start is not None or loop_end is not None:
        if loop_start is None or loop_end is None or int(loop_end) <= int(loop_start):
            errors.append("Loop audit requires loop_start < loop_end")
        else:
            seam = _endpoint_metrics(bpy, armature, int(loop_start), int(loop_end))
            metrics["loop_seam"] = seam
            if seam["location_difference"] > 0.0001:
                errors.append("Loop endpoint location difference exceeds 0.0001")
            if seam["rotation_difference_degrees"] > 0.1:
                errors.append("Loop endpoint rotation difference exceeds 0.1 degrees")
    else:
        warnings.append("Loop seam was not checked because no loop range was supplied")

    if contact_intervals:
        drift, drift_errors = _contact_drift(bpy, armature, contact_intervals)
        metrics["contact_drift"] = drift
        errors.extend(drift_errors)
        for bone_name, intervals in drift.items():
            for interval in intervals:
                if interval["max_drift"] > 0.02:
                    errors.append(
                        f"{bone_name} drift exceeds 0.02 during frames {interval['start']}-{interval['end']}"
                    )
    else:
        warnings.append("Foot/contact drift was not checked because no contact intervals were supplied")

    return {
        "ok": not errors,
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": {},
        "metrics": metrics,
        "artifacts": {},
        "warnings": warnings,
        "errors": errors,
    }


def _evaluated_local_delta(source_armature, evaluated_armature, bone_name: str):
    source_bone = source_armature.data.bones[bone_name]
    pose_bone = evaluated_armature.pose.bones[bone_name]
    if source_bone.parent and pose_bone.parent:
        rest_local = source_bone.parent.matrix_local.inverted() @ source_bone.matrix_local
        posed_local = pose_bone.parent.matrix.inverted() @ pose_bone.matrix
    else:
        rest_local = source_bone.matrix_local
        posed_local = pose_bone.matrix
    return rest_local.inverted() @ posed_local


def transfer_action_by_bone_name(
    source_armature_name: str,
    target_armature_name: str,
    source_action_name: str | None = None,
    target_action_name: str | None = None,
    frame_start: int | None = None,
    frame_end: int | None = None,
) -> dict[str, Any]:
    """Bake an action between two authentic Roblox armatures with matching bone names."""
    bpy, _Vector = _require_blender()
    try:
        source = _select_armature(bpy, source_armature_name)
        target = _select_armature(bpy, target_armature_name)
    except ValueError as exc:
        return _error(str(exc))
    if source == target:
        return _error("Source and target armatures must be different")

    source_authenticity = inspect_authenticity(source)
    target_authenticity = inspect_authenticity(target)
    if not source_authenticity["authentic_ready"]:
        return _error(
            "Source armature is not an authentic Roblox rig",
            armature=source.name,
            metrics={"source_authenticity": source_authenticity},
        )
    if not target_authenticity["authentic_ready"]:
        return _error(
            "Target armature is not an authentic Roblox export target",
            armature=target.name,
            metrics={"target_authenticity": target_authenticity},
        )

    source_action = bpy.data.actions.get(source_action_name) if source_action_name else None
    if source_action is None and source.animation_data:
        source_action = source.animation_data.action
    if source_action is None:
        return _error("Source armature has no action to transfer", armature=source.name)
    if frame_start is None:
        frame_start = int(round(source_action.frame_range[0]))
    if frame_end is None:
        frame_end = int(round(source_action.frame_range[1]))
    if frame_end < frame_start:
        return _error("Transfer requires frame_start <= frame_end", armature=source.name)

    target_action = _ensure_action(
        bpy,
        target,
        target_action_name or f"{source_action.name}_RobloxTarget",
    )
    if source.animation_data is None:
        source.animation_data_create()
    previous_source_action = source.animation_data.action
    previous_frame = int(bpy.context.scene.frame_current)
    source.animation_data.action = source_action
    target.animation_data.action = target_action

    common_bones = sorted(
        name
        for name in set(source.pose.bones.keys()) & set(target.pose.bones.keys())
        if target.data.bones[name].use_deform or "is_transformable" in target.data.bones[name]
    )
    if not common_bones:
        source.animation_data.action = previous_source_action
        return _error("Source and target have no matching transformable bones", armature=target.name)

    constrained = sorted(
        name for name in common_bones if any(not constraint.mute for constraint in target.pose.bones[name].constraints)
    )
    keyed = 0
    try:
        _activate_pose_mode(bpy, target)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for frame in range(int(frame_start), int(frame_end) + 1):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            evaluated_source = source.evaluated_get(depsgraph)
            for bone_name in common_bones:
                delta = _evaluated_local_delta(source, evaluated_source, bone_name)
                location, rotation, scale = delta.decompose()
                pose_bone = target.pose.bones[bone_name]
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.location = location
                pose_bone.rotation_quaternion = rotation
                pose_bone.scale = scale
                pose_bone.keyframe_insert(data_path="location", frame=frame, group=bone_name)
                pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone_name)
                pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)
                keyed += 9
        bpy.context.scene.frame_set(previous_frame)
        bpy.context.view_layer.update()
    except Exception as exc:
        return _error(f"Action transfer failed: {exc}", armature=target.name)
    finally:
        source.animation_data.action = previous_source_action

    return {
        "ok": not constrained,
        "rig_type": detect_rig_type(target.data.bones.keys()),
        "armature": target.name,
        "bones": {},
        "metrics": {
            "source_armature": source.name,
            "source_action": source_action.name,
            "target_action": target_action.name,
            "frame_start": int(frame_start),
            "frame_end": int(frame_end),
            "matching_bones": common_bones,
            "keyed_values": keyed,
            "source_authenticity": source_authenticity,
            "target_authenticity": target_authenticity,
        },
        "artifacts": {},
        "warnings": [],
        "errors": [f"Target transformable bones have active constraints: {', '.join(constrained)}"] if constrained else [],
    }


def export_fbx(
    output_path: str | Path,
    armature_name: str | None = None,
    action_name: str | None = None,
) -> dict[str, Any]:
    """Export one skinned action to FBX; Motor6D rigs must use .rbxanim."""
    bpy, _Vector = _require_blender()
    try:
        armature = _select_armature(bpy, armature_name)
        output = Path(output_path).expanduser().resolve()
        output = output.with_suffix(".fbx")
        output.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        return _error(f"Unable to prepare FBX export: {exc}", armature=armature_name)
    authenticity = inspect_authenticity(armature)
    if not authenticity["authentic_ready"]:
        return _error(
            "Refusing to export anything except a verified premade or Studio-derived Roblox rig",
            armature=armature.name,
            metrics={"authenticity": authenticity},
        )
    if authenticity["workflow"] == "motor6d-rbxanim":
        return _error(
            "This is a Motor6D control rig. Export it with export_rbxanim(), not generic FBX.",
            armature=armature.name,
            metrics={"authenticity": authenticity},
        )
    action = bpy.data.actions.get(action_name) if action_name else None
    if action is None and armature.animation_data:
        action = armature.animation_data.action
    if action is None:
        return _error("No active action is available to export", armature=armature.name)

    if armature.animation_data is None:
        armature.animation_data_create()
    previous_action = armature.animation_data.action
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    previous_mode = armature.mode
    nla_states = []
    if armature.animation_data:
        for track in armature.animation_data.nla_tracks:
            nla_states.append((track, track.mute))
            track.mute = True

    errors = []
    warnings = []
    try:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        armature.select_set(True)
        for mesh in _driven_meshes(bpy, armature):
            mesh.select_set(True)
        bpy.context.view_layer.objects.active = armature
        armature.animation_data.action = action

        requested = {
            "filepath": str(output),
            "check_existing": False,
            "use_selection": True,
            "object_types": {"ARMATURE", "MESH"},
            "apply_unit_scale": True,
            "apply_scale_options": "FBX_SCALE_UNITS",
            "axis_forward": "Z",
            "axis_up": "Y",
            "add_leaf_bones": False,
            "use_armature_deform_only": True,
            "bake_anim": True,
            "bake_anim_use_all_bones": True,
            "bake_anim_use_nla_strips": False,
            "bake_anim_use_all_actions": False,
            "bake_anim_force_startend_keying": True,
            "bake_anim_step": 1.0,
            "bake_anim_simplify_factor": 0.0,
            "path_mode": "AUTO",
        }
        supported = set(bpy.ops.export_scene.fbx.get_rna_type().properties.keys())
        required = {"use_armature_deform_only", "bake_anim_use_all_actions", "bake_anim_use_nla_strips"}
        missing_required = sorted(required - supported)
        if missing_required:
            raise RuntimeError(f"FBX exporter lacks required options: {', '.join(missing_required)}")
        kwargs = {key: value for key, value in requested.items() if key in supported}
        result = bpy.ops.export_scene.fbx(**kwargs)
        if "FINISHED" not in result:
            raise RuntimeError(f"FBX exporter returned {sorted(result)}")
    except Exception as exc:
        errors.append(f"FBX export failed: {exc}")
    finally:
        armature.animation_data.action = previous_action
        for track, mute in nla_states:
            track.mute = mute
        bpy.ops.object.select_all(action="DESELECT")
        for obj in previous_selected:
            if obj.name in bpy.context.scene.objects:
                obj.select_set(True)
        if previous_active and previous_active.name in bpy.context.scene.objects:
            bpy.context.view_layer.objects.active = previous_active
        if previous_mode == "POSE" and armature.name in bpy.context.scene.objects:
            _activate_pose_mode(bpy, armature)

    if not errors and (not output.is_file() or output.stat().st_size == 0):
        errors.append("FBX exporter finished without creating a non-empty file")
    return {
        "ok": not errors,
        "rig_type": detect_rig_type(armature.data.bones.keys()),
        "armature": armature.name,
        "bones": {},
        "metrics": {
            "action": action.name,
            "frame_start": int(bpy.context.scene.frame_start),
            "frame_end": int(bpy.context.scene.frame_end),
            "deform_only": True,
            "bake_step": 1.0,
            "authenticity": authenticity,
        },
        "artifacts": {"fbx": str(output)} if not errors else {},
        "warnings": warnings,
        "errors": errors,
    }


OPERATIONS = {
    "inspect": lambda payload: inspect_scene(payload.get("armature")),
    "apply-pose": apply_pose,
    "render": lambda payload: render_pose_views(
        payload.get("armature"),
        payload["output_directory"],
        payload.get("pose_label", "pose"),
        payload.get("frame"),
    ),
    "render-preview": lambda payload: render_animation_preview_frames(
        payload.get("armature"),
        payload["output_directory"],
        payload["frame_start"],
        payload["frame_end"],
        payload.get("filename_prefix", "animation"),
        bool(payload.get("exclude_duplicated_closing_frame", False)),
        payload.get("camera_location"),
        payload.get("look_target"),
        payload.get("ortho_scale"),
        int(payload.get("resolution", 512)),
    ),
    "polish": lambda payload: polish_curves(payload.get("armature"), payload.get("action")),
    "audit": lambda payload: audit_action(
        payload.get("armature"),
        payload.get("action"),
        payload.get("loop_start"),
        payload.get("loop_end"),
        payload.get("contact_intervals"),
    ),
    "transfer": lambda payload: transfer_action_by_bone_name(
        payload["source_armature"],
        payload["target_armature"],
        payload.get("source_action"),
        payload.get("target_action"),
        payload.get("frame_start"),
        payload.get("frame_end"),
    ),
    "export": lambda payload: export_fbx(
        payload["output_path"],
        payload.get("armature"),
        payload.get("action"),
    ),
    "export-rbxanim": lambda payload: export_rbxanim(payload["output_path"], payload["armature"]),
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--payload", default="{}", help="JSON operation payload")
    parser.add_argument("--payload-file", help="Path to a JSON operation payload")
    return parser.parse_args(argv)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = _parse_args(argv)
    if args.payload_file:
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    else:
        payload = json.loads(args.payload)
    result = OPERATIONS[args.operation](payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
