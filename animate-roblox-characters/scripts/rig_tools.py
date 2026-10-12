#!/usr/bin/env python3
"""Inspect installed rigs and import/export through manually installed Blender plugins."""
from __future__ import annotations
import tempfile
from pathlib import Path
from typing import Any, Iterable

R6_PARTS = {"Head", "Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg"}
R15_PARTS = {
    "Head",
    "UpperTorso",
    "LowerTorso",
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
IMPORTER_BONE_PROPERTIES = {"is_transformable", "transform", "transform1", "nicetransform"}
CONTROL_ALIASES = {
    "master": ("MasterControl", "MasterController", "RootControl", "CTRL_Root"),
    "lower_torso_fk": ("LowerTorso-FK", "LowerTorso_FK", "Torso-FK", "Torso"),
    "upper_torso_fk": ("UpperTorso-FK", "UpperTorso_FK", "UpperTorso"),
    "left_leg_ik": ("LeftLeg-IK", "LeftLeg_IK", "CTRL_LeftFoot_IK", "LeftFoot-IK"),
    "right_leg_ik": ("RightLeg-IK", "RightLeg_IK", "CTRL_RightFoot_IK", "RightFoot-IK"),
    "left_arm_fk": ("LeftUpperArm-FK", "LeftUpperArm_FK", "LeftUpperArm", "Left Arm"),
    "right_arm_fk": ("RightUpperArm-FK", "RightUpperArm_FK", "RightUpperArm", "Right Arm"),
    "head_fk": ("Head-FK", "Head_FK", "Head"),
}


def build_control_map(bone_names: Iterable[str]) -> dict[str, str]:
    names = list(bone_names)
    lower = {name.lower(): name for name in names}
    result = {}
    for role, aliases in CONTROL_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower:
                result[role] = lower[alias.lower()]
                break
    return result

def classify_snapshot(*, armature_name: str, bone_names: Iterable[str],
                      bone_property_names: Iterable[str] = (), object_names: Iterable[str] = (),
                      has_rig_meta: bool = False, has_armature_deformed_mesh: bool = False,
                      importer_available: bool = False, exporter_available: bool = False) -> dict[str, Any]:
    """Inspect structure and export capabilities of a manually installed rig."""
    bones = set(bone_names)
    parts = bones | set(object_names)
    metadata = sorted(IMPORTER_BONE_PROPERTIES & set(bone_property_names))
    controls = build_control_map(bones)
    control_rig = armature_name == "__PrimaryArmature" and "MasterControl" in bones
    if control_rig:
        source, workflow = "community-r6-ik-fk-control-rig", "motor6d-rbxanim"
        ready = bool(bones)
        reason = "Detected installed R6 controls; verify their behavior in Pose Mode before animation."
    elif IMPORTER_BONE_PROPERTIES.issubset(metadata):
        source, workflow = "studio-motor6d-import", "motor6d-rbxanim"
        ready = has_rig_meta
        reason = "Detected joint mapping." if ready else "Missing unambiguous associated rig metadata."
    elif has_armature_deformed_mesh:
        source, workflow = "skinned-rig", "skinned-fbx"
        ready = bool(bones)
        reason = "Detected a mesh driven by the installed armature."
    else:
        source, workflow = "custom-armature", "verify-before-export"
        ready = bool(bones)
        reason = "Inspect installed controls and establish the export mapping before delivery."
    return {
        "source": source, "workflow": workflow, "rig_ready": ready,
        "authoring_ready": ready, "reason": reason, "control_map": controls,
        "matched_r6_parts": sorted(R6_PARTS & parts), "matched_r15_parts": sorted(R15_PARTS & parts),
        "importer_metadata": metadata,
        "addon": {"import_operator": importer_available, "rbxanim_export_operator": exporter_available},
    }


def _require_blender():
    try:
        import bpy  # type: ignore
    except ImportError as exc:  # pragma: no cover - Blender-only path
        raise RuntimeError("Run rig_tools.py inside Blender") from exc
    return bpy

def _operator_available(operator) -> bool:
    try:
        operator.get_rna_type()
        return True
    except (AttributeError, KeyError, RuntimeError, TypeError):
        return False

def _mesh_uses_armature(mesh, armature) -> bool:
    if mesh.type != "MESH":
        return False
    if mesh.parent == armature:
        return True
    if any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in mesh.modifiers):
        return True
    return any(
        constraint.type == "CHILD_OF" and constraint.target == armature for constraint in mesh.constraints
    )

def _associated_rig_meta_objects(bpy, armature) -> list[Any]:
    """Find unambiguous Cautioned metadata associated with this armature."""
    armature_collections = {collection.name for collection in armature.users_collection}
    candidates = []
    for obj in bpy.data.objects:
        if obj.type != "EMPTY" or "RigMeta" not in obj:
            continue
        conventional_name = obj.name.startswith("__") and "Meta" in obj.name
        explicit = getattr(obj, "parent", None) == armature or str(obj.get("armature", "")) == armature.name
        shared_master = any(
            collection.name in armature_collections and collection.name.startswith("RIG:")
            for collection in obj.users_collection
        )
        if (conventional_name and shared_master) or explicit:
            candidates.append(obj)
    return candidates

def inspect_rig(armature) -> dict[str, Any]:
    bpy = _require_blender()
    bone_names = [bone.name for bone in armature.data.bones]
    property_names = set()
    metadata_bone_count = 0
    for bone in armature.data.bones:
        bone_properties = {str(key) for key in bone.keys()}
        property_names.update(bone_properties)
        if IMPORTER_BONE_PROPERTIES & bone_properties:
            metadata_bone_count += 1
    driven_meshes = [obj for obj in bpy.context.scene.objects if _mesh_uses_armature(obj, armature)]
    object_names = [obj.name for obj in driven_meshes]
    has_deformed_mesh = any(
        obj.vertex_groups
        or any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers)
        for obj in driven_meshes
    )
    rig_meta_candidates = _associated_rig_meta_objects(bpy, armature)
    has_associated_rig_meta = len(rig_meta_candidates) == 1
    # Bone properties identify the importer convention, but only an associated
    # One associated rig-named __*Meta object carrying RigMeta proves the
    # reconstructed rig/export mapping is complete.
    has_rig_meta = has_associated_rig_meta
    importer_available = _operator_available(getattr(bpy.ops.object, "rbxanims_importmodel", None))
    exporter_available = _operator_available(getattr(bpy.ops.object, "rbxanims_bake_file", None))
    result = classify_snapshot(
        armature_name=armature.name,
        bone_names=bone_names,
        bone_property_names=property_names,
        object_names=object_names,
        has_rig_meta=has_rig_meta,
        has_armature_deformed_mesh=has_deformed_mesh,
        importer_available=importer_available,
        exporter_available=exporter_available,
    )
    result["armature"] = armature.name
    result["driven_meshes"] = sorted(object_names)
    result["images"] = sorted(image.name for image in bpy.data.images if image.source == "FILE")
    result["metadata_bone_count"] = metadata_bone_count
    result["associated_rig_meta"] = has_associated_rig_meta
    result["rig_meta_candidates"] = sorted(obj.name for obj in rig_meta_candidates)
    result["rig_meta_ambiguous"] = len(rig_meta_candidates) > 1
    return result


def import_motor6d_obj(filepath: str | Path, rigging_type: str = "LOCAL_YAXIS_EXTEND") -> dict[str, Any]:
    """Import a Studio-plugin OBJ and reconstruct its metadata-backed armature."""
    bpy = _require_blender()
    source = Path(filepath).expanduser().resolve()
    if source.suffix.lower() != ".obj" or not source.is_file():
        return {"ok": False, "errors": ["A readable Studio-exported .obj file is required"], "warnings": []}
    if not _operator_available(getattr(bpy.ops.object, "rbxanims_importmodel", None)):
        return {
            "ok": False,
            "errors": ["The Roblox Animations Importer/Exporter add-on is unavailable"],
            "warnings": [],
        }
    try:
        imported = bpy.ops.object.rbxanims_importmodel(filepath=str(source))
    except Exception as exc:
        return {"ok": False, "errors": [f"Rig import operator failed: {exc}"], "warnings": []}
    if "FINISHED" not in imported:
        return {"ok": False, "errors": [f"Rig import returned {sorted(imported)}"], "warnings": []}
    if not _operator_available(getattr(bpy.ops.object, "rbxanims_genrig", None)):
        return {"ok": False, "errors": ["The imported rig cannot be rebuilt because the add-on operator is missing"], "warnings": []}
    try:
        rebuilt = bpy.ops.object.rbxanims_genrig(pr_rigging_type=rigging_type)
    except Exception as exc:
        return {"ok": False, "errors": [f"Rig rebuild operator failed: {exc}"], "warnings": []}
    if "FINISHED" not in rebuilt:
        return {"ok": False, "errors": [f"Rig rebuild returned {sorted(rebuilt)}"], "warnings": []}
    settings = getattr(bpy.context.scene, "rbx_anim_settings", None)
    armature_name = getattr(settings, "rbx_anim_armature", "") if settings is not None else ""
    armature = bpy.data.objects.get(armature_name) if armature_name else bpy.context.view_layer.objects.active
    if armature is None or armature.type != "ARMATURE":
        return {"ok": False, "errors": ["The add-on did not create a selectable armature"], "warnings": []}
    rig_info = inspect_rig(armature)
    if not (
        rig_info["rig_ready"]
        and rig_info["workflow"] == "motor6d-rbxanim"
        and rig_info["associated_rig_meta"]
        and IMPORTER_BONE_PROPERTIES.issubset(rig_info["importer_metadata"])
        and rig_info["metadata_bone_count"] > 0
        and rig_info["addon"]["rbxanim_export_operator"]
    ):
        return {
            "ok": False,
            "armature": armature.name,
            "rig_info": rig_info,
            "artifacts": {"source_obj": str(source)},
            "warnings": [],
            "errors": [
                "Imported Motor6D rig is incomplete: require one associated rig-named __*Meta object carrying "
                "RigMeta, mapped joints, and the export operator"
            ],
        }
    return {
        "ok": True,
        "armature": armature.name,
        "rig_info": rig_info,
        "artifacts": {"source_obj": str(source)},
        "warnings": [],
        "errors": [],
    }

def export_rbxanim(
    output_path: str | Path,
    armature_name: str,
    action_name: str | None = None,
    frame_start: int | None = None,
    frame_end: int | None = None,
) -> dict[str, Any]:
    """Export a metadata-backed Motor6D action through the companion add-on."""
    bpy = _require_blender()
    armature = bpy.data.objects.get(armature_name)
    if armature is None or armature.type != "ARMATURE":
        return {"ok": False, "errors": [f"Armature not found: {armature_name}"], "warnings": []}
    rig_info = inspect_rig(armature)
    if rig_info["workflow"] != "motor6d-rbxanim" or not rig_info["rig_ready"]:
        return {
            "ok": False,
            "errors": ["The selected rig is not a metadata-backed Motor6D/.rbxanim workflow"],
            "warnings": [],
        }
    if not _operator_available(getattr(bpy.ops.object, "rbxanims_bake_file", None)):
        return {
            "ok": False,
            "errors": ["The Roblox Animations .rbxanim export operator is unavailable"],
            "warnings": [],
        }
    settings = getattr(bpy.context.scene, "rbx_anim_settings", None)
    if settings is None or not hasattr(settings, "rbx_anim_armature"):
        return {
            "ok": False,
            "errors": ["The manually installed add-on did not register its armature-selection settings"],
            "warnings": [],
        }
    action = bpy.data.actions.get(action_name) if action_name is not None else None
    if action_name is not None and action is None:
        return {"ok": False, "errors": [f"Action not found: {action_name}"], "warnings": []}
    if action_name is None and action is None and armature.animation_data:
        action = armature.animation_data.action
    if action is None:
        return {"ok": False, "errors": ["No active action is available to export"], "warnings": []}
    export_start = int(round(action.frame_range[0])) if frame_start is None else int(frame_start)
    export_end = int(round(action.frame_range[1])) if frame_end is None else int(frame_end)
    if export_end < export_start:
        return {"ok": False, "errors": [".rbxanim export requires frame_start <= frame_end"], "warnings": []}

    try:
        output = Path(output_path).expanduser().resolve().with_suffix(".rbxanim")
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "errors": [f"Unable to prepare .rbxanim export: {exc}"], "warnings": []}
    created_animation_data = armature.animation_data is None
    if created_animation_data:
        armature.animation_data_create()
    previous_action = armature.animation_data.action
    previous_active = bpy.context.view_layer.objects.active
    previous_active_mode = previous_active.mode if previous_active is not None else None
    previous_selected = list(bpy.context.selected_objects)
    previous_frame = int(bpy.context.scene.frame_current)
    previous_frame_start = int(bpy.context.scene.frame_start)
    previous_frame_end = int(bpy.context.scene.frame_end)
    previous_rbx_armature = settings.rbx_anim_armature
    nla_states = [(track, track.mute) for track in armature.animation_data.nla_tracks]
    try:
        temporary_handle = tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-",
            suffix=".rbxanim",
            dir=output.parent,
            delete=False,
        )
    except OSError as exc:
        if created_animation_data:
            armature.animation_data_clear()
        return {"ok": False, "errors": [f"Unable to create temporary .rbxanim export: {exc}"], "warnings": []}
    temporary_handle.close()
    temporary_output = Path(temporary_handle.name)
    errors = []
    try:
        for track, _mute in nla_states:
            track.mute = True
        armature.animation_data.action = action
        bpy.context.scene.frame_start = export_start
        bpy.context.scene.frame_end = export_end
        settings.rbx_anim_armature = armature.name
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        result = bpy.ops.object.rbxanims_bake_file(filepath=str(temporary_output))
        if "FINISHED" not in result:
            raise RuntimeError(f".rbxanim exporter returned {sorted(result)}")
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise RuntimeError(".rbxanim exporter did not create a non-empty file")
        temporary_output.replace(output)
    except Exception as exc:
        errors.append(f".rbxanim export failed: {exc}")
    finally:
        temporary_output.unlink(missing_ok=True)
        armature.animation_data.action = previous_action
        for track, mute in nla_states:
            track.mute = mute
        if created_animation_data:
            armature.animation_data_clear()
        bpy.context.scene.frame_start = previous_frame_start
        bpy.context.scene.frame_end = previous_frame_end
        bpy.context.scene.frame_set(previous_frame)
        settings.rbx_anim_armature = previous_rbx_armature
        bpy.ops.object.select_all(action="DESELECT")
        for obj in previous_selected:
            if obj.name in bpy.context.scene.objects:
                obj.select_set(True)
        if previous_active and previous_active.name in bpy.context.scene.objects:
            bpy.context.view_layer.objects.active = previous_active
            if previous_active_mode and previous_active_mode != "OBJECT":
                previous_active.select_set(True)
                try:
                    bpy.ops.object.mode_set(mode=previous_active_mode)
                except RuntimeError:
                    errors.append(f"Could not restore prior object mode: {previous_active_mode}")
    return {
        "ok": not errors,
        "armature": armature.name,
        "rig_info": rig_info,
        "action": action.name,
        "frame_start": export_start,
        "frame_end": export_end,
        "artifacts": {"rbxanim": str(output)} if not errors else {},
        "warnings": [],
        "errors": errors,
    }

