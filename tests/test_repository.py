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

    def test_canonical_protocol_and_premade_rule_are_explicit(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "Work only in Pose Mode",
            "Discover and report the exact armature and bone names",
            "Linear interpolation is forbidden",
            "Foot sliding",
            "Phase 0 — Inspection and automatic setup",
            "Phase 1 — Animation planning",
            "Phase 2 — Key-pose planning",
            "Phase 3 — Blocking",
            "Phase 4 — Graph Editor polish",
            "Phase 5 — Polish and secondary motion",
            "Phase 6 — Loop test and final review",
            "Phase 7 — Preview media",
            "R6 IK + FK Blender Rig V2.22",
            "Blender Animations (ultimate edition)",
            "This skill has no generated-model fallback",
            "visible labeled/colored body controls",
            "Always deliver a verified animated GIF",
            ".rbxanim",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_single_confirmation_follows_plan_and_key_pose_concept(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        phase_1 = text.split("### Phase 1 — Animation planning", 1)[1].split(
            "### Phase 2 — Key-pose planning", 1
        )[0]
        phase_2 = text.split("### Phase 2 — Key-pose planning", 1)[1].split("### Phase 3 — Blocking", 1)[0]
        self.assertIn("continue directly to Phase 2 without asking for confirmation", phase_1)
        self.assertNotIn("obtain one confirmation", phase_1)
        self.assertIn("single confirmation before inserting any keyframes", phase_2)

    def test_r15_bootstrap_and_scale_calibration_are_documented(self):
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        rig_text = (SKILL / "references" / "roblox-rigs-export.md").read_text(encoding="utf-8")
        toolchain_text = (SKILL / "references" / "toolchain.md").read_text(encoding="utf-8")
        self.assertIn('required_workflow="r15-bootstrap"', skill_text)
        self.assertNotIn("toolchain.py --workflow", skill_text)
        for phrase in (
            "temporary live-sync transfer",
            "authentic_rig.import_motor6d_obj(path)",
            "mark_verified_skinned_rig(armature_name, source)",
            "Never delegate animation work to the user",
            "scene_units_per_stud = blender_scene_distance / studio_distance_studs",
            "scene_units_per_stud=scene_units_per_stud",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rig_text)
        self.assertIn("the sole runtime-readiness procedure", toolchain_text)
        self.assertIn("blender_mcp_available=True", toolchain_text)
        self.assertIn("pillow_available=True", toolchain_text)
        self.assertLess(
            skill_text.index("authentic_rig.enable_bundled_addon()"),
            skill_text.index('toolchain.full_audit(required_workflow="r15-bootstrap"'),
        )
        self.assertLess(
            rig_text.index("Hash-verify and register the bundled Cautioned"),
            rig_text.index("workflow-aware toolchain audit for `r15-bootstrap`"),
        )

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

    def test_installable_skill_contains_license_and_notices(self):
        self.assertEqual((SKILL / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
        notices = (SKILL / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("R6 IK + FK Blender Rig V2.22", notices)
        self.assertIn("218b5e43e414fe3fa5d8a42cc5fd162b70e66f4cb82efd73ac5006b63895769a", notices)

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

    def test_rbxanim_export_targets_the_bundled_addon_setting(self):
        source = (SCRIPTS / "authentic_rig.py").read_text(encoding="utf-8")
        self.assertIn('settings.rbx_anim_armature = armature.name', source)
        self.assertNotIn('bpy.context.scene.rbx_anim_armature = armature.name', source)

    def test_bundled_current_addon_and_license(self):
        addon = SKILL / "assets" / "blender-addons" / "rbx_anims_v2.6.3.zip"
        license_file = SKILL / "assets" / "blender-addons" / "Cautioned-Blender-Animations-Plugin-LICENSE.txt"
        self.assertEqual(sha256(addon), "218b5e43e414fe3fa5d8a42cc5fd162b70e66f4cb82efd73ac5006b63895769a")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_file.read_text(encoding="utf-8"))


class PurePythonScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.animation_tools = load_module("animation_tools_test", SCRIPTS / "animation_tools.py")
        cls.preview = load_module("animation_preview_test", SCRIPTS / "build_animation_preview.py")
        cls.authentic_rig = load_module("authentic_rig_test", SCRIPTS / "authentic_rig.py")
        cls.fetch_assets = load_module("fetch_assets_test", SCRIPTS / "fetch_assets.py")
        cls.toolchain = load_module("toolchain_test", SCRIPTS / "toolchain.py")
        cls.privacy = load_module("privacy_check_test", SCRIPTS / "privacy_check.py")
        cls.session_guard = load_module("session_guard_test", SCRIPTS / "session_guard.py")
        cls.blend_security = load_module("inspect_blend_security_test", SCRIPTS / "inspect_blend_security.py")

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

    def test_generated_rig_is_always_rejected(self):
        result = self.authentic_rig.classify_snapshot(
            armature_name="GeneratedRig",
            bone_names=self.animation_tools.R15_REQUIRED,
            generated_by="any-generator",
            has_armature_deformed_mesh=True,
        )
        self.assertEqual(result["source"], "generated-or-repository-proxy")
        self.assertEqual(result["workflow"], "diagnostic-only")
        self.assertFalse(result["authentic_ready"])
        self.assertFalse(result["authoring_ready"])

    def test_video_style_control_rig_uses_motor6d_workflow(self):
        result = self.authentic_rig.classify_snapshot(
            armature_name="__PrimaryArmature",
            bone_names=["MasterControl", "LowerTorso-FK", "LeftLeg-IK", "RightLeg-IK"],
        )
        self.assertEqual(result["source"], "community-r6-ik-fk-control-rig")
        self.assertEqual(result["workflow"], "motor6d-rbxanim")
        self.assertFalse(result["authentic_ready"])
        verified = self.authentic_rig.classify_snapshot(
            armature_name="__PrimaryArmature",
            bone_names=["MasterControl", "LowerTorso-FK", "LeftLeg-IK", "RightLeg-IK"],
            verified_control_rig=True,
        )
        self.assertTrue(verified["authentic_ready"])
        self.assertEqual(result["control_map"]["master"], "MasterControl")

    def test_r6_lineage_hmac_is_stable_across_blender_versions_and_filenames(self):
        with tempfile.TemporaryDirectory() as directory:
            bpy_45 = SimpleNamespace(utils=SimpleNamespace(user_resource=lambda _kind: "blender-4.5"))
            bpy_51 = SimpleNamespace(utils=SimpleNamespace(user_resource=lambda _kind: "blender-5.1"))
            lineage_id = "a" * 32
            key_directory = Path(directory) / "stable-user-config"
            with mock.patch.object(
                self.authentic_rig,
                "_r6_lineage_directory",
                return_value=key_directory,
            ):
                signature = self.authentic_rig._r6_lineage_signature(
                    bpy_51,
                    lineage_id,
                    create_key=True,
                )
                signature_from_45 = self.authentic_rig._r6_lineage_signature(
                    bpy_45,
                    lineage_id,
                    create_key=False,
                )
                armature = {
                    self.authentic_rig.R6_PROVENANCE_PROPERTY: self.authentic_rig.R6_V222_BLEND_SHA256,
                    self.authentic_rig.R6_LINEAGE_ID_PROPERTY: lineage_id,
                    self.authentic_rig.R6_LINEAGE_PROPERTY: signature,
                }
                verified_from_45 = self.authentic_rig._r6_lineage_verified(bpy_45, armature)
                marker_only_verified = self.authentic_rig._r6_lineage_verified(
                    bpy_45,
                    {self.authentic_rig.R6_PROVENANCE_PROPERTY: self.authentic_rig.R6_V222_BLEND_SHA256},
                )
            self.assertIsNotNone(signature)
            self.assertEqual(len(signature), 64)
            self.assertEqual(signature_from_45, signature)
            self.assertNotIn(lineage_id, signature)
            key = key_directory / "r6-lineage.key"
            self.assertEqual(len(key.read_bytes()), 32)
            self.assertTrue(verified_from_45)
            self.assertFalse(marker_only_verified)

    def test_studio_import_metadata_uses_rbxanim(self):
        result = self.authentic_rig.classify_snapshot(
            armature_name="ImportedRig",
            bone_names=self.authentic_rig.R6_PARTS,
            bone_property_names=["is_transformable", "transform", "transform1", "nicetransform"],
            has_rig_meta=True,
            importer_available=True,
            exporter_available=True,
        )
        self.assertEqual(result["source"], "studio-motor6d-import")
        self.assertEqual(result["workflow"], "motor6d-rbxanim")
        self.assertTrue(result["addon"]["rbxanim_export_operator"])
        unassociated = self.authentic_rig.classify_snapshot(
            armature_name="ImportedRig",
            bone_names=self.authentic_rig.R6_PARTS,
            bone_property_names=["is_transformable", "transform", "transform1", "nicetransform"],
            has_rig_meta=False,
            importer_available=True,
            exporter_available=True,
        )
        self.assertFalse(unassociated["authentic_ready"])
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
            self.authentic_rig._associated_rig_meta_objects(bpy, armature),
            [matching],
        )
        duplicate = FakeObject("__HeroMeta.001", "EMPTY", [master], {"RigMeta": "payload"})
        bpy.data.objects.append(duplicate)
        self.assertEqual(
            len(self.authentic_rig._associated_rig_meta_objects(bpy, armature)),
            2,
        )

    def test_r15_names_and_mesh_require_explicit_studio_provenance(self):
        unverified = self.authentic_rig.classify_snapshot(
            armature_name="R15Like",
            bone_names=self.authentic_rig.R15_PARTS,
            has_armature_deformed_mesh=True,
        )
        self.assertEqual(unverified["source"], "studio-or-fbx-skinned-r15")
        self.assertFalse(unverified["authentic_ready"])
        verified = self.authentic_rig.classify_snapshot(
            armature_name="StudioR15",
            bone_names=self.authentic_rig.R15_PARTS,
            has_armature_deformed_mesh=True,
            skinned_source="studio-rig-builder",
        )
        self.assertTrue(verified["authentic_ready"])

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

    def test_toolchain_manifest_pins_real_rig_and_current_addon(self):
        manifest = self.toolchain.load_manifest()
        components = {item["id"]: item for item in manifest["components"]}
        self.assertEqual(components["cautioned-blender-addon"]["version"], "2.6.3")
        self.assertEqual(components["pillow"]["current_version"], "12.3.0")
        self.assertTrue(components["cautioned-blender-addon"]["bundled"])
        self.assertFalse(components["r6-ik-fk-v222"]["bundled"])
        self.assertEqual(len(components["r6-ik-fk-v222"]["downloads"]), 2)
        self.assertIn("redistribution license not stated", components["r6-ik-fk-v222"]["license"])
        self.assertIn("r15-authoring", components["studio-premade-r15"]["required_for"])

    def test_fetcher_rejects_unapproved_hosts_and_unsafe_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(ValueError):
                self.fetch_assets._safe_target(root, "../escape")
            with self.assertRaises(ValueError):
                self.fetch_assets._download(
                    "https://example.invalid/model.blend",
                    root / "model.blend",
                    "0" * 64,
                    1,
                )

    def test_addon_archive_audit_finds_expected_network_but_no_processes(self):
        path = SKILL / "assets" / "blender-addons" / "rbx_anims_v2.6.3.zip"
        result = self.toolchain.audit_python_archive(path)
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["python_files"], 20)
        self.assertTrue(result["network_files"])
        self.assertEqual(result["process_files"], [])

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

    def test_r15_bootstrap_requires_all_bundled_addon_operators(self):
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
        operator_errors = [error for error in result["errors"] if "bundled add-on operator" in error]
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
