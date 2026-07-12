from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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
        self.assertTrue((ROOT / "docs" / "stylized-r6-walk-preview.gif").is_file())

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
        self.assertTrue(result["authentic_ready"])
        self.assertEqual(result["control_map"]["master"], "MasterControl")

    def test_studio_import_metadata_uses_rbxanim(self):
        result = self.authentic_rig.classify_snapshot(
            armature_name="ImportedRig",
            bone_names=["Torso", "Left Arm"],
            bone_property_names=["is_transformable", "transform", "transform1", "nicetransform"],
            has_rig_meta=True,
            importer_available=True,
            exporter_available=True,
        )
        self.assertEqual(result["source"], "studio-motor6d-import")
        self.assertEqual(result["workflow"], "motor6d-rbxanim")
        self.assertTrue(result["addon"]["rbxanim_export_operator"])

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

    def test_addon_audit_flags_network_and_dynamic_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.py"
            path.write_text("import urllib.request\nexec('value = 1')\n", encoding="utf-8")
            result = self.toolchain.audit_python_source(path)
            self.assertTrue(result["review_required"])
            self.assertIn("urllib.request", result["network_modules"])
            self.assertIn("exec", result["dynamic_code_calls"])

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


if __name__ == "__main__":
    unittest.main()
