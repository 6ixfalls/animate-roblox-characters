#!/usr/bin/env python3
"""Detect and operate authentic Roblox Studio-exported Blender rigs.

This adapter supports Cautioned's current metadata-based importer workflow,
the pinned R6 IK/FK V2.22 control rig, and conventional skinned FBX rigs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import importlib.util
import sys
import tempfile
import types
import zipfile
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
BUNDLED_ADDON_SHA256 = "218b5e43e414fe3fa5d8a42cc5fd162b70e66f4cb82efd73ac5006b63895769a"
R6_V222_BLEND_SHA256 = "ff75c44b572d32328b62095141c6ce6255c4e9b772ee63d46d92280de1edcdc8"
R6_V222_TEXT_SHA256 = {
    "RigBootstrap.py": "2e87eae515b129b0eac2db0138cd2ec215f101e45c975fe7b1eeaabfe38033e7",
    "RigEvents.py": "01731b7ad8c77ac4160f76a513e740c965aa78a7aa5e4072101024a4783e0211",
    "RigSelector.py": "7deaa1d7c3480896b90b148cde7fc24fa974865de5cff691208d537187194e9f",
    "RigSettings.py": "e9b334ee31ebc87af15b3e75242fea8249b7ff841a7487f1e4c2221cce590edd",
    "RigUtilities.py": "dc96f3453e5cdb0bea7a3af3f4c8823a06492c81d90ae5f34190e7ef5332760a",
}

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


def classify_snapshot(
    *,
    armature_name: str,
    bone_names: Iterable[str],
    bone_property_names: Iterable[str] = (),
    object_names: Iterable[str] = (),
    generated_by: str | None = None,
    has_rig_meta: bool = False,
    has_armature_deformed_mesh: bool = False,
    importer_available: bool = False,
    exporter_available: bool = False,
) -> dict[str, Any]:
    """Classify a rig from a pure-Python snapshot for testing and Blender use."""
    bones = set(bone_names)
    objects = set(object_names)
    properties = set(bone_property_names)
    controls = build_control_map(bones)
    matched_r6_parts = sorted(R6_PARTS & (bones | objects))
    matched_r15_parts = sorted(R15_PARTS & (bones | objects))
    metadata_matches = sorted(IMPORTER_BONE_PROPERTIES & properties)

    if generated_by:
        source = "generated-or-repository-proxy"
        workflow = "diagnostic-only"
        authentic_ready = False
        authoring_ready = False
        reason = "Repository-generated or proxy rigs are forbidden; use the pinned premade Roblox rig or a Studio-derived target."
    elif armature_name.startswith("__PrimaryArmature") and (
        "MasterControl" in bones or any(name.endswith(("-IK", "-FK")) for name in bones)
    ):
        source = "community-r6-ik-fk-control-rig"
        workflow = "motor6d-rbxanim"
        authentic_ready = True
        authoring_ready = True
        reason = "Detected the external __PrimaryArmature control-rig convention shown by the R6 IK/FK workflow."
    elif has_rig_meta or len(metadata_matches) >= 3:
        source = "studio-motor6d-import"
        workflow = "motor6d-rbxanim"
        authentic_ready = True
        authoring_ready = True
        reason = "Detected Roblox joint metadata produced by the Den_S/Cautioned Studio-to-Blender importer."
    elif has_armature_deformed_mesh and len(matched_r15_parts) >= 10:
        source = "studio-or-fbx-skinned-r15"
        workflow = "skinned-fbx"
        authentic_ready = True
        authoring_ready = True
        reason = "Detected a segmented, armature-deformed R15 character suitable for the FBX animation pipeline."
    elif has_armature_deformed_mesh and len(matched_r6_parts) >= 5:
        source = "fbx-r6-like-rig"
        workflow = "verify-before-export"
        authentic_ready = False
        authoring_ready = False
        reason = "The scene looks R6-like but lacks Motor6D importer metadata; verify the Studio export path before animation."
    else:
        source = "unknown"
        workflow = "unverified"
        authentic_ready = False
        authoring_ready = False
        reason = "No trusted Studio-export metadata or recognized authentic control-rig convention was found."

    return {
        "source": source,
        "workflow": workflow,
        "authentic_ready": authentic_ready,
        "authoring_ready": authoring_ready,
        "reason": reason,
        "control_map": controls,
        "matched_r6_parts": matched_r6_parts,
        "matched_r15_parts": matched_r15_parts,
        "importer_metadata": metadata_matches,
        "addon": {
            "import_operator": importer_available,
            "rbxanim_export_operator": exporter_available,
        },
    }


def _require_blender():
    try:
        import bpy  # type: ignore
    except ImportError as exc:  # pragma: no cover - Blender-only path
        raise RuntimeError("Run authentic_rig.py inside Blender") from exc
    return bpy


def _operator_available(operator) -> bool:
    try:
        operator.get_rna_type()
        return True
    except (AttributeError, KeyError, RuntimeError):
        return False


def _extract_verified_addon(addon_path: Path, digest: str) -> Path:
    root = Path(tempfile.gettempdir()) / f"animate-roblox-cautioned-{digest[:16]}"
    marker = root / ".verified-sha256"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest:
        return root
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(addon_path) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if root.resolve() not in target.parents and target != root.resolve():
                raise RuntimeError(f"Unsafe path in bundled add-on: {member.filename}")
        archive.extractall(root)
    marker.write_text(digest + "\n", encoding="utf-8")
    return root


def enable_bundled_addon() -> dict[str, Any]:
    """Register the pinned Cautioned 2.6.3 extension for this Blender session.

    Registration does not start its optional localhost sync server or OAuth flow.
    """
    bpy = _require_blender()
    if _operator_available(bpy.ops.object.rbxanims_importmodel) and _operator_available(
        bpy.ops.object.rbxanims_bake_file
    ):
        return {"ok": True, "already_available": True, "warnings": [], "errors": []}
    addon_path = Path(__file__).resolve().parents[1] / "assets" / "blender-addons" / "rbx_anims_v2.6.3.zip"
    if not addon_path.is_file():
        return {"ok": False, "warnings": [], "errors": ["Bundled Cautioned 2.6.3 add-on is missing"]}
    digest = hashlib.sha256(addon_path.read_bytes()).hexdigest()
    if digest != BUNDLED_ADDON_SHA256:
        return {
            "ok": False,
            "warnings": [],
            "errors": ["Bundled Cautioned 2.6.3 add-on failed its SHA-256 integrity check"],
        }
    try:
        extracted = _extract_verified_addon(addon_path, digest)
        module_name = "animate_roblox_cautioned_v263"
        module = sys.modules.get(module_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                module_name,
                extracted / "__init__.py",
                submodule_search_locations=[str(extracted)],
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not create a module spec for the bundled extension")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        module.register()
    except Exception as exc:
        return {"ok": False, "warnings": [], "errors": [f"Bundled add-on registration failed: {exc}"]}
    available = _operator_available(bpy.ops.object.rbxanims_importmodel) and _operator_available(
        bpy.ops.object.rbxanims_bake_file
    )
    return {
        "ok": available,
        "already_available": False,
        "sha256": digest,
        "warnings": [],
        "errors": [] if available else ["Bundled add-on registered without the required operators"],
    }


def activate_verified_r6_v222() -> dict[str, Any]:
    """Activate the audited embedded UI/control scripts in the exact R6 V2.22 file."""
    bpy = _require_blender()
    filepath = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if filepath is None or not filepath.is_file():
        return {"ok": False, "errors": ["No saved .blend is open"], "warnings": []}
    blend_digest = hashlib.sha256(filepath.read_bytes()).hexdigest()
    if blend_digest != R6_V222_BLEND_SHA256:
        return {"ok": False, "errors": ["Open file is not the pinned R6 IK/FK V2.22 asset"], "warnings": []}
    text_hashes = {}
    for name, expected in R6_V222_TEXT_SHA256.items():
        text = bpy.data.texts.get(name)
        if text is None:
            return {"ok": False, "errors": [f"Pinned R6 rig is missing embedded text: {name}"], "warnings": []}
        digest = hashlib.sha256(text.as_string().encode("utf-8")).hexdigest()
        text_hashes[name] = digest
        if digest != expected:
            return {"ok": False, "errors": [f"Embedded R6 script failed SHA-256 verification: {name}"], "warnings": []}
    armature = bpy.data.objects.get("__PrimaryArmature")
    if armature is None or armature.type != "ARMATURE" or not armature.get("_Rbx_R6_Rig_", False):
        return {"ok": False, "errors": ["Pinned R6 control armature marker is missing"], "warnings": []}
    namespace_key = "ANIMATE_ROBLOX_R6_V222_BOOTSTRAP"
    if namespace_key not in bpy.app.driver_namespace:
        loaded_modules = []
        try:
            for text_name in ("RigSelector.py", "RigSettings.py", "RigUtilities.py", "RigEvents.py"):
                module_name = "animate_roblox_r6_v222_" + text_name.removesuffix(".py").lower()
                module = types.ModuleType(module_name)
                module.__file__ = text_name
                sys.modules[module_name] = module
                source = bpy.data.texts[text_name].as_string()
                exec(compile(source, text_name, "exec"), module.__dict__, module.__dict__)
                register = getattr(module, "register", None)
                if callable(register):
                    register()
                loaded_modules.append(module)
        except Exception:
            for module in reversed(loaded_modules):
                unregister = getattr(module, "unregister", None)
                if callable(unregister):
                    try:
                        unregister()
                    except Exception:
                        pass
            raise
        bpy.app.driver_namespace[namespace_key] = loaded_modules
    return {
        "ok": True,
        "blend_sha256": blend_digest,
        "text_sha256": text_hashes,
        "armature": armature.name,
        "warnings": [],
        "errors": [],
    }


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


def inspect_authenticity(armature) -> dict[str, Any]:
    bpy = _require_blender()
    bone_names = [bone.name for bone in armature.data.bones]
    property_names = set()
    for bone in armature.data.bones:
        property_names.update(str(key) for key in bone.keys())
    driven_meshes = [obj for obj in bpy.context.scene.objects if _mesh_uses_armature(obj, armature)]
    object_names = [obj.name for obj in driven_meshes]
    has_deformed_mesh = any(
        obj.vertex_groups
        or any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers)
        for obj in driven_meshes
    )
    rig_meta = bpy.data.objects.get("__RigMeta")
    has_rig_meta = bool(rig_meta and "RigMeta" in rig_meta)
    importer_available = _operator_available(bpy.ops.object.rbxanims_importmodel)
    exporter_available = _operator_available(bpy.ops.object.rbxanims_bake_file)
    result = classify_snapshot(
        armature_name=armature.name,
        bone_names=bone_names,
        bone_property_names=property_names,
        object_names=object_names,
        generated_by=armature.get("generated_by"),
        has_rig_meta=has_rig_meta,
        has_armature_deformed_mesh=has_deformed_mesh,
        importer_available=importer_available,
        exporter_available=exporter_available,
    )
    result["armature"] = armature.name
    result["driven_meshes"] = sorted(object_names)
    result["images"] = sorted(image.name for image in bpy.data.images if image.source == "FILE")
    return result


def import_motor6d_obj(filepath: str | Path, rigging_type: str = "LOCAL_YAXIS_EXTEND") -> dict[str, Any]:
    """Import a Studio-plugin OBJ and reconstruct its metadata-backed armature."""
    bpy = _require_blender()
    source = Path(filepath).expanduser().resolve()
    if source.suffix.lower() != ".obj" or not source.is_file():
        return {"ok": False, "errors": ["A readable Studio-exported .obj file is required"], "warnings": []}
    addon = enable_bundled_addon()
    if not addon["ok"] or not _operator_available(bpy.ops.object.rbxanims_importmodel):
        return {
            "ok": False,
            "errors": addon["errors"] or ["The Roblox Animations Importer/Exporter add-on is unavailable"],
            "warnings": [],
        }
    imported = bpy.ops.object.rbxanims_importmodel(filepath=str(source))
    if "FINISHED" not in imported:
        return {"ok": False, "errors": [f"Rig import returned {sorted(imported)}"], "warnings": []}
    if not _operator_available(bpy.ops.object.rbxanims_genrig):
        return {"ok": False, "errors": ["The imported rig cannot be rebuilt because the add-on operator is missing"], "warnings": []}
    rebuilt = bpy.ops.object.rbxanims_genrig(pr_rigging_type=rigging_type)
    if "FINISHED" not in rebuilt:
        return {"ok": False, "errors": [f"Rig rebuild returned {sorted(rebuilt)}"], "warnings": []}
    armature_name = getattr(bpy.context.scene, "rbx_anim_armature", "")
    armature = bpy.data.objects.get(armature_name) if armature_name else bpy.context.view_layer.objects.active
    if armature is None or armature.type != "ARMATURE":
        return {"ok": False, "errors": ["The add-on did not create a selectable armature"], "warnings": []}
    return {
        "ok": True,
        "armature": armature.name,
        "authenticity": inspect_authenticity(armature),
        "artifacts": {"source_obj": str(source)},
        "warnings": [],
        "errors": [],
    }


def export_rbxanim(output_path: str | Path, armature_name: str) -> dict[str, Any]:
    """Export a metadata-backed Motor6D action through the companion add-on."""
    bpy = _require_blender()
    armature = bpy.data.objects.get(armature_name)
    if armature is None or armature.type != "ARMATURE":
        return {"ok": False, "errors": [f"Armature not found: {armature_name}"], "warnings": []}
    authenticity = inspect_authenticity(armature)
    if authenticity["workflow"] != "motor6d-rbxanim":
        return {
            "ok": False,
            "errors": ["The selected rig is not a metadata-backed Motor6D/.rbxanim workflow"],
            "warnings": [],
        }
    addon = enable_bundled_addon()
    if not addon["ok"] or not _operator_available(bpy.ops.object.rbxanims_bake_file):
        return {
            "ok": False,
            "errors": addon["errors"] or ["The Roblox Animations .rbxanim export operator is unavailable"],
            "warnings": [],
        }
    output = Path(output_path).expanduser().resolve().with_suffix(".rbxanim")
    output.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(bpy.context.scene, "rbx_anim_armature"):
        bpy.context.scene.rbx_anim_armature = armature.name
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    result = bpy.ops.object.rbxanims_bake_file(filepath=str(output))
    errors = []
    if "FINISHED" not in result:
        errors.append(f".rbxanim exporter returned {sorted(result)}")
    if not output.is_file() or output.stat().st_size == 0:
        errors.append(".rbxanim exporter did not create a non-empty file")
    return {
        "ok": not errors,
        "armature": armature.name,
        "authenticity": authenticity,
        "artifacts": {"rbxanim": str(output)} if not errors else {},
        "warnings": [],
        "errors": errors,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--armature", required=True)
    import_parser = subparsers.add_parser("import-obj")
    import_parser.add_argument("--input", required=True)
    import_parser.add_argument("--rigging-type", default="LOCAL_YAXIS_EXTEND")
    export_parser = subparsers.add_parser("export-rbxanim")
    export_parser.add_argument("--armature", required=True)
    export_parser.add_argument("--output", required=True)
    subparsers.add_parser("enable-addon")
    subparsers.add_parser("activate-r6-v222")
    return parser.parse_args(argv)


def main() -> int:
    bpy = _require_blender()
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = _parse_args(argv)
    if args.operation == "inspect":
        armature = bpy.data.objects.get(args.armature)
        result = (
            {"ok": True, "authenticity": inspect_authenticity(armature), "errors": []}
            if armature and armature.type == "ARMATURE"
            else {"ok": False, "errors": [f"Armature not found: {args.armature}"]}
        )
    elif args.operation == "import-obj":
        result = import_motor6d_obj(args.input, args.rigging_type)
    elif args.operation == "export-rbxanim":
        result = export_rbxanim(args.output, args.armature)
    elif args.operation == "enable-addon":
        result = enable_bundled_addon()
    else:
        result = activate_verified_r6_v222()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
