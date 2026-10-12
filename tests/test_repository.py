from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "animate-roblox-characters"
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SkillStructureTests(unittest.TestCase):
    def test_frontmatter_contains_only_required_fields(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        keys = [line.split(":", 1)[0] for line in frontmatter.splitlines() if ":" in line]
        self.assertEqual(keys, ["name", "description"])
        self.assertIn("name: animate-roblox-characters", frontmatter)


    def test_single_confirmation_follows_plan_and_key_pose_concept(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        phase_1 = text.split("### Phase 1 — Animation planning", 1)[1].split(
            "### Phase 2 — Key-pose planning", 1
        )[0]
        phase_2 = text.split("### Phase 2 — Key-pose planning", 1)[1].split("### Phase 3 — Blocking", 1)[0]
        self.assertIn("continue directly to Phase 2 without asking for confirmation", phase_1)
        self.assertNotIn("obtain one confirmation", phase_1)
        self.assertIn("single confirmation before inserting any keyframes", phase_2)


    def test_agent_metadata_matches_skill(self):
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Animate Roblox Characters"', text)
        self.assertIn("$animate-roblox-characters", text)
        self.assertIn('short_description: "Animate premade Roblox rigs with GIF previews"', text)

    def test_readme_supports_codex_claude_and_demo(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Install for Codex", text)
        self.assertIn("Install for Claude Code", text)
        self.assertIn("docs/stylized-r6-walk-preview.gif", text)
        self.assertIn("interactive Blender GUI", text)
        self.assertIn("GPT-5.6 Sol using extra-high reasoning", text)
        self.assertIn('$HOME/.agents/skills', text)
        self.assertIn("img.shields.io/github/v/release/dillydog580/animate-roblox-characters", text)
        self.assertIn("img.shields.io/github/license/dillydog580/animate-roblox-characters", text)
        self.assertIn("skills.sh/dillydog580/animate-roblox-characters/animate-roblox-characters", text)
        self.assertIn("npx skills add dillydog580/animate-roblox-characters", text)
        self.assertNotIn("## Privacy", text)
        self.assertTrue((ROOT / "docs" / "stylized-r6-walk-preview.gif").is_file())


    def test_ci_installs_pinned_test_dependency(self):
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("name: CI", workflow)
        self.assertIn("pip install --requirement requirements-dev.txt", workflow)
        self.assertIn("cache-dependency-path: requirements-dev.txt", workflow)
        self.assertIn("Pillow==12.3.0", requirements)

    def test_generated_outputs_and_crash_reports_are_ignored(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("outputs/", "*.crash", "*.dmp", "blender_debug_*"):
            self.assertIn(pattern, text)

    def test_no_generated_model_assets_or_factories(self):
        forbidden = [
            SCRIPTS / "rig_factory.py",
            SCRIPTS / "authoring_rig_factory.py",
            SCRIPTS / "build_templates.py",
            SKILL / "assets" / "r6-authoring.blend",
            SKILL / "assets" / "r15-authoring.blend",
            SKILL / "assets" / "r6-starter.blend",
            SKILL / "assets" / "r15-starter.blend",
        ]
        self.assertTrue(all(not path.exists() for path in forbidden))

    def test_rbxanim_export_targets_the_installed_addon_setting(self):
        source = (SCRIPTS / "rig_tools.py").read_text(encoding="utf-8")
        self.assertIn('settings.rbx_anim_armature = armature.name', source)
        self.assertNotIn('bpy.context.scene.rbx_anim_armature = armature.name', source)



class PurePythonScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.animation_tools = load_module("animation_tools_test", SCRIPTS / "animation_tools.py")
        cls.preview = load_module("animation_preview_test", SCRIPTS / "build_animation_preview.py")
        cls.rig_tools = load_module("rig_tools_test", SCRIPTS / "rig_tools.py")
        cls.toolchain = load_module("toolchain_test", SCRIPTS / "toolchain.py")
        cls.privacy = load_module("privacy_check_test", SCRIPTS / "privacy_check.py")
        cls.session_guard = load_module("session_guard_test", SCRIPTS / "session_guard.py")
        cls.blend_security = load_module("inspect_blend_security_test", SCRIPTS / "inspect_blend_security.py")

    def test_installed_rigs_do_not_require_provenance_or_activation(self):
        control = self.rig_tools.classify_snapshot(
            armature_name="__PrimaryArmature", bone_names=["MasterControl", "LeftLeg-IK"]
        )
        self.assertTrue(control["rig_ready"])
        self.assertEqual(control["workflow"], "motor6d-rbxanim")
        skinned = self.rig_tools.classify_snapshot(
            armature_name="CustomAvatar", bone_names=["Root", "Spine"],
            has_armature_deformed_mesh=True,
        )
        self.assertTrue(skinned["rig_ready"])
        self.assertEqual(skinned["workflow"], "skinned-fbx")
        self.assertFalse(self.rig_tools._operator_available(None))

    def test_missing_manual_import_plugin_returns_prerequisite(self):
        fake_bpy = SimpleNamespace(ops=SimpleNamespace(object=SimpleNamespace()))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.obj"
            source.write_text("# supplied model\n")
            with mock.patch.dict(sys.modules, {"bpy": fake_bpy}):
                result = self.rig_tools.import_motor6d_obj(source)
        self.assertFalse(result["ok"])
        self.assertIn("add-on is unavailable", result["errors"][0])

    def test_partial_importer_properties_preserve_skinned_workflow(self):
        properties = sorted(self.rig_tools.IMPORTER_BONE_PROPERTIES)
        for omitted in properties:
            with self.subTest(omitted=omitted):
                result = self.rig_tools.classify_snapshot(
                    armature_name="CustomAvatar",
                    bone_names=["Root", "Spine"],
                    bone_property_names=[name for name in properties if name != omitted],
                    has_armature_deformed_mesh=True,
                )
                self.assertTrue(result["rig_ready"])
                self.assertEqual(result["workflow"], "skinned-fbx")

    def test_finished_import_requires_complete_motor6d_mapping(self):
        armature = SimpleNamespace(name="ImportedRig", type="ARMATURE")
        operator = mock.Mock(return_value={"FINISHED"})
        fake_bpy = SimpleNamespace(
            ops=SimpleNamespace(object=SimpleNamespace(
                rbxanims_importmodel=operator,
                rbxanims_genrig=operator,
            )),
            context=SimpleNamespace(
                scene=SimpleNamespace(),
                view_layer=SimpleNamespace(objects=SimpleNamespace(active=armature)),
            ),
        )
        valid = self.rig_tools.classify_snapshot(
            armature_name=armature.name,
            bone_names=self.rig_tools.R6_PARTS,
            bone_property_names=self.rig_tools.IMPORTER_BONE_PROPERTIES,
            has_rig_meta=True,
            exporter_available=True,
        )
        valid.update(associated_rig_meta=True, metadata_bone_count=6)
        cases = [
            ("valid", {}, True),
            ("custom", {"workflow": "verify-before-export"}, False),
            ("skinned", {"workflow": "skinned-fbx"}, False),
            ("missing meta", {"associated_rig_meta": False}, False),
            ("partial mapping", {"importer_metadata": ["transform"]}, False),
            ("no mapped bones", {"metadata_bone_count": 0}, False),
            ("missing exporter", {"addon": {"rbxanim_export_operator": False}}, False),
            ("unready", {"rig_ready": False}, False),
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.obj"
            source.write_text("# supplied model\n")
            for label, changes, expected in cases:
                with self.subTest(case=label), mock.patch.dict(sys.modules, {"bpy": fake_bpy}), \
                        mock.patch.object(self.rig_tools, "inspect_rig", return_value=valid | changes):
                    result = self.rig_tools.import_motor6d_obj(source)
                self.assertEqual(result["ok"], expected, result)
                if not expected:
                    self.assertIn("Imported Motor6D rig is incomplete", result["errors"][0])

    def test_rig_type_detection(self):
        self.assertEqual(self.animation_tools.detect_rig_type(self.animation_tools.R15_REQUIRED), "R15")
        r6 = self.animation_tools.R6_REQUIRED | {"HumanoidRootPart"}
        self.assertEqual(self.animation_tools.detect_rig_type(r6), "R6")

    def test_30fps_gif_duration_pattern_is_exact(self):
        durations = self.preview.gif_durations(24, 30.0)
        self.assertEqual(durations, [30, 30, 40] * 8)
        self.assertEqual(sum(durations), 800)

    def test_demo_gif_has_verified_delivery_metadata(self):
        from PIL import Image, ImageSequence

        with Image.open(ROOT / "docs" / "stylized-r6-walk-preview.gif") as gif:
            total_ms = sum(frame.info.get("duration", 0) for frame in ImageSequence.Iterator(gif))
            self.assertEqual(gif.n_frames, 24)
            self.assertEqual(gif.size, (512, 512))
            self.assertEqual(gif.info.get("loop"), 0)
            self.assertEqual(total_ms, 800)

    def test_session_guard_rejects_background_blender(self):
        result = self.session_guard.classify_session((5, 1, 2), True, "Darwin", "arm64")
        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "background")
        self.assertTrue(result["errors"])
        self.assertTrue(result["warnings"])

    def test_session_guard_accepts_persistent_gui(self):
        result = self.session_guard.classify_session((4, 5, 7), False, "Darwin", "arm64")
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "persistent-gui")
        self.assertEqual(result["errors"], [])

    def test_shared_palette_gif_is_encoded_and_verified(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index in range(24):
                path = root / f"frame_{index + 1:04d}.png"
                Image.new("RGB", (64, 64), ((index * 37) % 256, (80 + index * 11) % 256, (200 - index * 7) % 256)).save(path)
                paths.append(path)
            result = self.preview.build_gif(paths, root / "preview.gif", fps=30, expected_frames=24)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["frames"], 24)
            self.assertEqual(result["duration_ms"], 800)
            self.assertEqual(result["loop"], 0)
            self.assertEqual(set(result["disposal_modes"]), {2})

    def test_gif_boundary_markers_preserve_each_frame_corner_color(self):
        from PIL import Image, ImageSequence

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            colors = [(255, 0, 0), (0, 0, 255)]
            paths = []
            for index, color in enumerate(colors):
                path = root / f"solid_{index}.png"
                Image.new("RGB", (16, 16), color).save(path)
                paths.append(path)
            result = self.preview.build_gif(paths, root / "solid.gif", fps=10, expected_frames=2)
            self.assertTrue(result["ok"], result["errors"])
            with Image.open(root / "solid.gif") as gif:
                decoded = [frame.convert("RGB").getpixel((0, 0)) for frame in ImageSequence.Iterator(gif)]
            self.assertEqual(decoded, colors)




    def test_studio_import_metadata_uses_rbxanim(self):
        result = self.rig_tools.classify_snapshot(
            armature_name="ImportedRig",
            bone_names=self.rig_tools.R6_PARTS,
            bone_property_names=["is_transformable", "transform", "transform1", "nicetransform"],
            has_rig_meta=True,
            importer_available=True,
            exporter_available=True,
        )
        self.assertEqual(result["source"], "studio-motor6d-import")
        self.assertEqual(result["workflow"], "motor6d-rbxanim")
        self.assertTrue(result["addon"]["rbxanim_export_operator"])
        unassociated = self.rig_tools.classify_snapshot(
            armature_name="ImportedRig",
            bone_names=self.rig_tools.R6_PARTS,
            bone_property_names=["is_transformable", "transform", "transform1", "nicetransform"],
            has_rig_meta=False,
            importer_available=True,
            exporter_available=True,
        )
        self.assertFalse(unassociated["rig_ready"])
        self.assertIn("associated rig metadata", unassociated["reason"].lower())

    def test_rig_meta_association_supports_named_rigs_and_rejects_ambiguity(self):
        class FakeObject(dict):
            def __init__(self, name, object_type, collections, properties=None, parent=None):
                super().__init__(properties or {})
                self.name = name
                self.type = object_type
                self.users_collection = collections
                self.parent = parent

        master = SimpleNamespace(name="RIG: Hero")
        other_master = SimpleNamespace(name="RIG: Other")
        armature = FakeObject("__Hero_Armature", "ARMATURE", [master])
        matching = FakeObject("__HeroMeta", "EMPTY", [master], {"RigMeta": "payload"})
        unrelated = FakeObject("__OtherMeta", "EMPTY", [other_master], {"RigMeta": "payload"})
        bpy = SimpleNamespace(data=SimpleNamespace(objects=[armature, matching, unrelated]))
        self.assertEqual(
            self.rig_tools._associated_rig_meta_objects(bpy, armature),
            [matching],
        )
        duplicate = FakeObject("__HeroMeta.001", "EMPTY", [master], {"RigMeta": "payload"})
        bpy.data.objects.append(duplicate)
        self.assertEqual(
            len(self.rig_tools._associated_rig_meta_objects(bpy, armature)),
            2,
        )


    def test_pose_payload_validation_is_atomic_and_strict(self):
        valid = self.animation_tools.validate_pose_payload(
            {
                "frame": 1,
                "interpolation": "constant",
                "bones": {"Torso": {"location": [0, 0, 0]}},
            },
            {"Torso"},
        )
        self.assertEqual(valid["frame"], 1)
        self.assertEqual(valid["interpolation"], "CONSTANT")
        with self.assertRaises(ValueError):
            self.animation_tools.validate_pose_payload(
                {
                    "frame": 1,
                    "interpolation": "LINEAR",
                    "bones": {"Torso": {"location": [0, 0, 0]}},
                },
                {"Torso"},
            )
        with self.assertRaises(ValueError):
            self.animation_tools.validate_pose_payload(
                {"frame": 1, "bones": {"Missing": {"location": [0, 0, 0]}}},
                {"Torso"},
            )

    def test_action_bone_path_parser_handles_escaped_names(self):
        action = SimpleNamespace(
            fcurves=[
                SimpleNamespace(data_path='pose.bones["Torso"].location'),
                SimpleNamespace(data_path='pose.bones["Quoted\\\"Bone"].rotation_euler'),
                SimpleNamespace(data_path="location"),
                SimpleNamespace(data_path='pose.bones["unterminated].scale'),
            ]
        )
        self.assertEqual(
            self.animation_tools._animated_pose_bone_names(action),
            {"Torso", 'Quoted"Bone'},
        )

    def test_audit_frame_validation_rejects_nonfinite_fractional_and_oversized_values(self):
        self.assertEqual(self.animation_tools._finite_integer(25, "frame"), 25)
        for value in (float("inf"), float("nan"), 1.5, 2_000_000, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.animation_tools._finite_integer(value, "frame")
        normalized = self.animation_tools._normalize_contact_intervals(
            {"LeftFoot": [[1, 6], [20, 24]]},
            {"LeftFoot"},
        )
        self.assertEqual(normalized, {"LeftFoot": [[1, 6], [20, 24]]})
        with self.assertRaises(ValueError):
            self.animation_tools._normalize_contact_intervals(
                {"LeftFoot": [[1, float("inf")]]},
                {"LeftFoot"},
            )

    def test_audit_operation_forwards_required_checks_and_scene_scale(self):
        captured = {}
        original = self.animation_tools.audit_action

        def recorder(*args):
            captured["args"] = args
            return {"ok": True}

        self.animation_tools.audit_action = recorder
        try:
            result = self.animation_tools.OPERATIONS["audit"](
                {
                    "armature": "Rig",
                    "action": "Walk",
                    "loop_start": 1,
                    "loop_end": 25,
                    "contact_intervals": {"LeftFoot": [[1, 6]]},
                    "contact_drift_threshold": 0.02,
                    "scene_units_per_stud": 0.01,
                    "loop_required": True,
                    "contacts_required": True,
                    "audit_stage": "BLOCKING",
                }
            )
        finally:
            self.animation_tools.audit_action = original
        self.assertTrue(result["ok"])
        self.assertEqual(captured["args"][-5:], (0.02, 0.01, True, True, "BLOCKING"))

    def test_blocking_loop_tangent_mismatch_is_deferred_until_bezier_polish(self):
        tangents = {
            "missing_endpoint_curves": [],
            "max_slope_difference": 0.25,
        }
        blocking_errors, blocking_warnings = self.animation_tools._loop_tangent_findings(
            tangents,
            "BLOCKING",
        )
        final_errors, final_warnings = self.animation_tools._loop_tangent_findings(
            tangents,
            "FINAL",
        )
        self.assertEqual(blocking_errors, [])
        self.assertTrue(blocking_warnings)
        self.assertTrue(final_errors)
        self.assertEqual(final_warnings, [])

    def test_mesh_keyframe_audit_ignores_rig_drivers_and_control_shapes(self):
        curve = SimpleNamespace(data_path="location", array_index=0)

        def animation_data(action=None, drivers=()):
            return SimpleNamespace(action=action, nla_tracks=[], drivers=list(drivers))

        control_shape = SimpleNamespace(
            type="MESH",
            name="ControlShape",
            animation_data=animation_data(SimpleNamespace(name="ShapeAction", fcurves=[curve])),
            data=SimpleNamespace(shape_keys=None),
        )
        driven_mesh = SimpleNamespace(
            type="MESH",
            name="Body",
            animation_data=animation_data(
                SimpleNamespace(name="EmptyAction", fcurves=[]),
                drivers=[curve],
            ),
            data=SimpleNamespace(shape_keys=None),
        )
        keyed_mesh = SimpleNamespace(
            type="MESH",
            name="AccidentallyKeyed",
            animation_data=animation_data(SimpleNamespace(name="BadAction", fcurves=[curve])),
            data=SimpleNamespace(shape_keys=None),
        )
        armature = SimpleNamespace(
            type="ARMATURE",
            pose=SimpleNamespace(bones=[SimpleNamespace(custom_shape=control_shape)]),
        )
        bpy = SimpleNamespace(
            context=SimpleNamespace(
                scene=SimpleNamespace(objects=[armature, control_shape, driven_mesh, keyed_mesh])
            )
        )
        self.assertEqual(
            self.animation_tools._mesh_animation_paths(bpy),
            ["AccidentallyKeyed:action:location[0]"],
        )




    def test_archive_preflight_rejection_preserves_full_result_schema(self):
        expected_keys = {
            "path",
            "sha256",
            "python_files",
            "network_files",
            "process_files",
            "dynamic_code_files",
            "reports",
            "errors",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape.py", "print('unsafe')\n")
            result = self.toolchain.audit_python_archive(path)
        self.assertEqual(set(result), expected_keys)
        self.assertEqual(result["python_files"], 0)
        self.assertEqual(result["network_files"], [])
        self.assertEqual(result["process_files"], [])
        self.assertEqual(result["dynamic_code_files"], [])
        self.assertEqual(result["reports"], [])
        self.assertTrue(any("Unsafe archive member" in error for error in result["errors"]))

    def test_repository_audit_handles_rejected_addon_archive_without_keyerror(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addon = root / "assets" / "blender-addons" / "unsafe.zip"
            addon.parent.mkdir(parents=True)
            with zipfile.ZipFile(addon, "w") as archive:
                archive.writestr("../escape.py", "print('unsafe')\n")
            manifest = {
                "schema_version": 1,
                "components": [
                    {
                        "id": "cautioned-blender-addon",
                        "bundled": True,
                        "files": ["assets/blender-addons/unsafe.zip"],
                    }
                ],
            }
            (root / "assets" / "toolchain-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            result = self.toolchain.audit_repository(root)
        self.assertFalse(result["ok"])
        archive_audit = result["components"][0]["archive_audit"]
        self.assertEqual(archive_audit["python_files"], 0)
        self.assertTrue(archive_audit["errors"])

    def test_r15_bootstrap_requires_externally_verified_capabilities(self):
        missing = self.toolchain.audit_runtime(required_workflow="r15-bootstrap")
        checks = missing["runtime"]["agent_checks"]
        self.assertEqual(checks["blender_mcp_python_execution"], "required-unverified")
        self.assertEqual(checks["pillow_gif_encoder"], "required-unverified")
        self.assertEqual(checks["roblox_studio_mcp"], "required-unverified")
        self.assertEqual(checks["creator_store_animation_plugin"], "required-unverified")
        self.assertTrue(any("requires Roblox Studio MCP" in error for error in missing["errors"]))
        self.assertTrue(any("requires the Creator Store" in error for error in missing["errors"]))

        verified = self.toolchain.audit_runtime(
            required_workflow="r15-bootstrap",
            blender_mcp_available=True,
            pillow_available=True,
            pillow_version="12.3.0",
            studio_mcp_available=True,
            creator_plugin_available=True,
        )
        verified_checks = verified["runtime"]["agent_checks"]
        self.assertEqual(verified_checks["roblox_studio_mcp"], "verified-by-external-discovery")
        self.assertEqual(
            verified_checks["creator_store_animation_plugin"], "verified-by-external-discovery"
        )
        self.assertFalse(any("r15-bootstrap workflow requires" in error for error in verified["errors"]))

        unavailable = self.toolchain.audit_runtime(
            required_workflow="r15-bootstrap",
            blender_mcp_available=True,
            pillow_available=True,
            pillow_version="12.3.0",
            studio_mcp_available=False,
            creator_plugin_available=True,
        )
        self.assertEqual(
            unavailable["runtime"]["agent_checks"]["roblox_studio_mcp"],
            "unavailable-by-external-discovery",
        )
        self.assertTrue(any("requires Roblox Studio MCP" in error for error in unavailable["errors"]))

    def test_runtime_requires_mcp_attestation_and_persistent_in_process_blender(self):
        operator = SimpleNamespace(get_rna_type=lambda: object())
        fake_bpy = SimpleNamespace(
            app=SimpleNamespace(version=(4, 5, 0), background=False),
            ops=SimpleNamespace(
                object=SimpleNamespace(
                    rbxanims_importmodel=operator,
                    rbxanims_genrig=operator,
                    rbxanims_bake_file=operator,
                )
            ),
        )
        pillow_attestation = {"pillow_available": True, "pillow_version": "12.3.0"}
        with mock.patch.dict(sys.modules, {"bpy": fake_bpy}):
            unattested = self.toolchain.audit_runtime(**pillow_attestation)
            attested = self.toolchain.audit_runtime(
                blender_mcp_available=True,
                **pillow_attestation,
            )
            fake_bpy.app.background = True
            background = self.toolchain.audit_runtime(
                blender_mcp_available=True,
                **pillow_attestation,
            )

        unattested_checks = unattested["runtime"]["agent_checks"]
        self.assertTrue(unattested["runtime"]["inside_blender"])
        self.assertEqual(unattested["runtime"]["session_mode"], "persistent-gui")
        self.assertEqual(unattested_checks["blender_python_in_process"], "verified-by-bpy-import")
        self.assertEqual(unattested_checks["blender_mcp_python_execution"], "required-unverified")
        self.assertFalse(unattested["ok"])
        self.assertTrue(any("arbitrary-Python Blender MCP" in error for error in unattested["errors"]))

        self.assertTrue(attested["ok"], attested["errors"])
        self.assertEqual(
            attested["runtime"]["agent_checks"]["blender_mcp_python_execution"],
            "verified-by-external-discovery",
        )
        self.assertFalse(background["ok"])
        self.assertEqual(background["runtime"]["session_mode"], "background")

    def test_r15_bootstrap_requires_all_installed_addon_operators(self):
        fake_bpy = SimpleNamespace(
            app=SimpleNamespace(version=(4, 5, 0), background=False),
            ops=SimpleNamespace(object=SimpleNamespace()),
        )
        with mock.patch.dict(sys.modules, {"bpy": fake_bpy}):
            result = self.toolchain.audit_runtime(
                required_workflow="r15-bootstrap",
                blender_mcp_available=True,
                pillow_available=True,
                pillow_version="12.3.0",
                studio_mcp_available=True,
                creator_plugin_available=True,
            )
        self.assertEqual(
            result["runtime"]["operators"],
            {"rbxanim_import": False, "rbxanim_rebuild": False, "rbxanim_export": False},
        )
        operator_errors = [error for error in result["errors"] if "installed add-on operator" in error]
        self.assertEqual(len(operator_errors), 3)
        self.assertTrue(any("rbxanim_import" in error for error in operator_errors))
        self.assertTrue(any("rbxanim_rebuild" in error for error in operator_errors))
        self.assertTrue(any("rbxanim_export" in error for error in operator_errors))

    def test_pillow_is_verified_in_external_encoder_environment(self):
        discovery = self.toolchain.audit_pillow_encoder()
        self.assertTrue(discovery["ok"], discovery["errors"])
        self.assertTrue(discovery["pillow_available"])
        self.assertIsInstance(discovery["pillow_version"], str)

        missing_version = self.toolchain.audit_runtime(
            blender_mcp_available=True,
            pillow_available=True,
        )
        self.assertEqual(
            missing_version["runtime"]["agent_checks"]["pillow_gif_encoder"],
            "available-version-unverified",
        )
        self.assertTrue(any("exact externally verified Pillow version" in error for error in missing_version["errors"]))

        unsupported = self.toolchain.audit_runtime(
            blender_mcp_available=True,
            pillow_available=True,
            pillow_version="13.0.0",
        )
        self.assertEqual(
            unsupported["runtime"]["agent_checks"]["pillow_gif_encoder"],
            "available-unsupported-version",
        )
        self.assertTrue(any("Unsupported externally attested Pillow" in error for error in unsupported["errors"]))

        enabled = self.toolchain._parse_args(
            ["--blender-mcp-available", "--pillow-available", "--pillow-version", "12.3.0"]
        )
        disabled = self.toolchain._parse_args(["--no-blender-mcp-available", "--no-pillow-available"])
        self.assertTrue(enabled.blender_mcp_available)
        self.assertTrue(enabled.pillow_available)
        self.assertEqual(enabled.pillow_version, "12.3.0")
        self.assertFalse(disabled.blender_mcp_available)
        self.assertFalse(disabled.pillow_available)

    def test_full_audit_forwards_workflow_capability_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "toolchain-manifest.json").write_text(
                json.dumps({"schema_version": 1, "components": []}), encoding="utf-8"
            )
            result = self.toolchain.full_audit(
                root,
                required_workflow="r15-bootstrap",
                blender_mcp_available=True,
                pillow_available=True,
                pillow_version="12.3.0",
                studio_mcp_available=True,
                creator_plugin_available=True,
            )
        runtime = result["runtime"]["runtime"]
        self.assertEqual(runtime["required_workflow"], "r15-bootstrap")
        self.assertEqual(
            runtime["agent_checks"]["creator_store_animation_plugin"],
            "verified-by-external-discovery",
        )
        self.assertEqual(
            runtime["agent_checks"]["blender_mcp_python_execution"],
            "verified-by-external-discovery",
        )
        self.assertEqual(runtime["agent_checks"]["pillow_gif_encoder"], "verified-by-external-discovery")
        self.assertEqual(runtime["pillow_version"], "12.3.0")

    def test_repository_only_cli_ignores_runtime_workflow_requirements(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "toolchain.py"),
                "--repository-only",
                "--workflow",
                "r15-bootstrap",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertNotIn("runtime", payload)

    def test_addon_audit_flags_network_and_dynamic_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.py"
            path.write_text("import urllib.request\nexec('value = 1')\n", encoding="utf-8")
            result = self.toolchain.audit_python_source(path)
            self.assertTrue(result["review_required"])
            self.assertIn("urllib.request", result["network_modules"])
            self.assertIn("exec", result["dynamic_code_calls"])

    def test_static_audits_detect_aliased_process_and_dynamic_calls(self):
        cases = [
            "import os as harmless\nharmless.system('id')\n",
            "from os import popen as read_cmd\nread_cmd('id')\n",
            "from builtins import eval as parse\nparse('1+1')\n",
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, source in enumerate(cases):
                path = Path(directory) / f"candidate_{index}.py"
                path.write_text(source, encoding="utf-8")
                self.assertTrue(self.toolchain.audit_python_source(path)["review_required"])
        flags = self.blend_security.inspect_source_capabilities(
            "from pathlib import Path as P\nP('x').write_text('value')\n"
        )
        self.assertTrue(flags["filesystem"])

    def test_privacy_scanner_detects_private_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = "/" + "Users" + "/privateperson/project/file.blend"
            (root / "bad.txt").write_text(private_path, encoding="utf-8")
            findings = self.privacy.scan_repository(root)
            self.assertTrue(any(item.rule == "macOS home-directory path" for item in findings))

    def test_privacy_scanner_allows_generic_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Use $HOME or <project-directory>.\n", encoding="utf-8")
            self.assertEqual(self.privacy.scan_repository(root), [])

    def test_privacy_scanner_rejects_escaping_symlink_and_remote_secret(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            secret = "AK" + "IA" + "0" * 16
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_text(secret, encoding="utf-8")
            (root / "escape.txt").symlink_to(outside_file)
            findings = self.privacy.scan_repository(root)
            self.assertTrue(any(item.rule == "symlink escapes repository" for item in findings))

            (root / "escape.txt").unlink()
            (root / "broken.txt").symlink_to(root / "missing.txt")
            findings = self.privacy.scan_repository(root)
            self.assertTrue(any(item.rule == "broken symlink" for item in findings))
            (root / "broken.txt").unlink()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Public Contributor"], cwd=root, check=True)
            contributor_email = "contributor" + "@" + "example.com"
            subprocess.run(["git", "config", "user.email", contributor_email], cwd=root, check=True)
            contributor_findings = self.privacy.scan_repository(root, enforce_git_identity=False)
            self.assertFalse(any(item.rule == "email address" for item in contributor_findings))
            token = "gh" + "p_" + "a" * 24
            subprocess.run(["git", "config", "user.name", token], cwd=root, check=True)
            identity_findings = self.privacy.scan_repository(root, enforce_git_identity=False)
            self.assertTrue(any(item.rule == "GitHub token" for item in identity_findings))
            subprocess.run(["git", "config", "user.name", "Public Contributor"], cwd=root, check=True)
            subprocess.run(
                ["git", "remote", "add", "origin", f"https://{token}@example.invalid/repo.git"],
                cwd=root,
                check=True,
            )
            findings = self.privacy.scan_repository(root, enforce_git_identity=False)
            self.assertTrue(any(item.rule == "GitHub token" for item in findings))

    def test_privacy_scanner_checks_forced_tracked_external_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            external = root / "animate-roblox-characters" / "assets" / "external"
            external.mkdir(parents=True)
            leak = external / "forced.txt"
            leak.write_text("/" + "Users" + "/privateperson/secret\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "-f", str(leak.relative_to(root))], cwd=root, check=True)
            findings = self.privacy.scan_repository(root, enforce_git_identity=False)
            self.assertTrue(any(item.path.endswith("assets/external/forced.txt") for item in findings))

    def test_privacy_scanner_checks_deleted_git_history_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Roblox Animation Skill Contributors"],
                cwd=root,
                check=True,
            )
            allowed_email = "contributors" + "@" + "users.noreply.github.com"
            subprocess.run(["git", "config", "user.email", allowed_email], cwd=root, check=True)
            leak = root / "temporary.txt"
            leak.write_text("/" + "Users" + "/privateperson/deleted-secret\n", encoding="utf-8")
            subprocess.run(["git", "add", "temporary.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "add temporary file"], cwd=root, check=True)
            leak.unlink()
            subprocess.run(["git", "add", "-u"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "remove temporary file"], cwd=root, check=True)

            findings = self.privacy.scan_repository(root, enforce_git_identity=True)
            self.assertTrue(
                any(
                    item.path.startswith(".git/history-blobs/temporary.txt@")
                    and item.rule == "macOS home-directory path"
                    for item in findings
                )
            )


if __name__ == "__main__":
    unittest.main()
