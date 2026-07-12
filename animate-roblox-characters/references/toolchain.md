# Roblox–Blender Toolchain

Read this during Phase 0. The machine-readable source and hash inventory is `assets/toolchain-manifest.json`.

## Required stack

| Component | Purpose | Policy |
|---|---|---|
| Blender 4.5+ | Pose Mode, Graph Editor, rendered review, export | Install from Blender.org. Blender 4.5 LTS is recommended because the R6 asset targets that line and a persistent LTS GUI avoids disposable-process teardown instability. |
| Blender MCP 1.6.4 | AI control through Blender Python | External MIT package. Localhost only; telemetry and remote asset integrations off. |
| Pillow `>=10,<13` | Shared-palette GIF encoding and verification | External HPND Python library. Read local PNG renders and write the preview GIF only. |
| R6 IK + FK Blender Rig V2.22 | Premade visible R6 model, colored/labeled controls, IK/FK, panels | Mandatory for generic R6 work. Fetch only from Aeresei's original DevForum attachments with `fetch_assets.py`. Do not mirror it in Git because no redistribution license is stated. |
| Premade Studio R15 | Actual visible R15 target | Mandatory for R15. Use Studio's rig builder or the user's existing character, then export it. Never replace it with generated geometry. |
| Cautioned Blender Animations 2.6.3 | Import/export, mapping, IK/control support, `.rbxanim` | Bundled unmodified signed-release zip under GPL-3.0-or-later; SHA-256 verified. |
| Blender Animations (ultimate edition) | Studio side of the Motor6D transfer | Install only from Cautioned's Creator Store listing. |
| Roblox Studio MCP | R15 bootstrap and optional playback validation | Use Roblox's built-in MCP. |

## Premade-model rule

There is no repository-generated Roblox model and no block-proxy fallback.

- R6 begins from the actual V2.22 author rig. It contains `__PrimaryArmature`, `InternalArmature`, `MasterControl`, IK/FK limb controls, custom control shapes, body variants, colored orientation faces, and the Active Rig/Rig Settings/Utilities/Rig Texture panels seen in the reference workflow.
- R15 begins from a premade Roblox Studio character. Cautioned's Studio and Blender tools reconstruct the actual target and preserve Motor6D mapping.
- A custom avatar begins from that avatar's Studio export. Preserve appearance, accessories, joint metadata, and texture mapping.
- Roblox's official R15 “rig and attachments” project is skeleton/reference material only. It is not a visible-player substitute.

If the requested premade rig cannot be obtained or verified, stop before keyframing.

## Pinned R6 installation

Run with network authorization:

```sh
python3 animate-roblox-characters/scripts/fetch_assets.py --component r6-ik-fk-v222
```

The downloader accepts only allowlisted HTTPS hosts, writes through a temporary file, checks byte size and SHA-256, and refuses to overwrite an unverified local file. It installs the asset into the ignored `assets/external/` cache. Always copy the cached master into the animation project before editing.

Open the working copy with Blender script auto-execution disabled. Then call `authentic_rig.activate_verified_r6_v222()`. It verifies the complete `.blend` plus every embedded text block before registering the UI and control scripts. Never click “Allow Execution” on an altered copy.

## Cautioned 2.6.3 security boundary

The bundled `rbx_anims_v2.6.3.zip` is the unmodified current GitHub release. Static review found:

- Roblox OAuth and asset-delivery networking.
- A live-sync HTTP server bound to `127.0.0.1`.
- Permissive CORS on that optional local server.
- No process-spawning imports in the release.

`authentic_rig.enable_bundled_addon()` verifies the zip and registers it without starting OAuth or the live-sync server. Keep online access, auto-connect, and live sync off during ordinary authoring. When Studio transfer requires live sync, start it only for that operation, do not browse untrusted sites while it is running, and stop it immediately afterward.

## Blender MCP boundary

Blender MCP intentionally allows arbitrary local Python execution:

1. Bind it to loopback only.
2. Verify the pinned package hash from the manifest.
3. Disable telemetry and third-party asset download integrations.
4. Open one interactive Blender GUI and keep that process alive throughout inspection, animation, rendering, export, and saving.
5. Run `session_guard.inspect_session()` through MCP and require `mode: persistent-gui` before mutation.
6. Never invoke Blender with `--background`, spawn it as a child process, or call Blender's quit operator.
7. Save an incremented working copy before mutation.
8. Execute repository modules or short reviewed pose blocks only.
9. Never expose Blender MCP or the Cautioned live-sync port to a LAN or the internet.

## Audits

```sh
python3 animate-roblox-characters/scripts/toolchain.py
python3 animate-roblox-characters/scripts/toolchain.py --audit-archive <addon.zip>
python3 animate-roblox-characters/scripts/toolchain.py --audit-addon <candidate.py>
```

For an untrusted `.blend`, disable Blender's script auto-execution, open the file in the persistent GUI, and call `inspect_blend_security.inspect_current_file()` through MCP. Static review reduces risk but does not prove arbitrary third-party code safe.
