# Animate Roblox Characters Skill

`animate-roblox-characters` is an open-source Codex and Claude Code skill for creating complete stylized Roblox R6 and R15 character animations in Blender. It operates on an authentic Studio-derived Roblox rig, handles bone/control inspection, pose planning, keyframing, Graph Editor polish, foot-lock and loop checks, source-appropriate export, a rendered animated GIF preview, and optional Roblox Studio validation.

The skill's canonical protocol is based on a strict professional-animation workflow: every pose is created on armature pose bones, checked from front and side views, critiqued, corrected, and polished before completion.

![Stylized R6 walk generated with the skill](docs/stylized-r6-walk-preview.gif)

_Example 24-frame, 30 FPS stylized R6 walk produced end-to-end with the skill. The preview is rendered from Blender frames and encoded with one shared palette._

## Requirements

- Codex or Claude Code with Agent Skills support.
- Blender 4.5 LTS (recommended) or a compatible newer release.
- A Blender MCP server that can execute arbitrary Python in the open Blender process.
- Pillow `>=10,<13` for verified shared-palette GIF encoding.
- Optional: the [Roblox Studio built-in MCP server](https://create.roblox.com/docs/studio/mcp) for Studio-side playback checks.

The repository includes an offline dependency manifest/checker, the current Cautioned Blender extension, and a pinned installer for the authentic premade R6 control rig. It does not bundle Blender or a remote-control server. Blender MCP 1.6.4 is supported only as a localhost, telemetry-disabled external service because arbitrary Python execution is its intended capability.

For classic Motor6D R6/R15 rigs, use Cautioned's [Blender Animations (ultimate edition)](https://create.roblox.com/store/asset/16708835782/Blender-Animations-ultimate-edition) Studio plugin and the bundled v2.6.3 Blender extension. This preserves joint mapping and exports `.rbxanim`. For verified skinned Roblox rigs, use FBX.

The colored, labeled R6 control-rig interface seen in the referenced tutorials is [R6 IK + FK Blender Rig V2.22](https://devforum.roblox.com/t/r6-ik-fk-blender-rig-v222/3586405). It is mandatory for generic R6 authoring. The skill downloads the actual `.blend` and matching `.rbxm` directly from the author's attachments and verifies pinned hashes. Because the author did not state a redistribution license, Git does not mirror those binaries; the automated source-pinned install keeps the public repository legally clean.

Compatible Blender MCPs commonly expose tools named `execute_blender_code` or `blender_python_exec`. The skill discovers capabilities and is not tied to one private server path.

## Install for Codex

Copy the `animate-roblox-characters` directory into:

```text
${CODEX_HOME:-$HOME/.codex}/skills/
```

Restart Codex, then invoke it directly:

```text
Use $animate-roblox-characters to make a fast, aggressive R15 sword attack.
```

## Install for Claude Code

Copy the same canonical skill directory into the user-level Claude skills directory:

```text
$HOME/.claude/skills/animate-roblox-characters/
```

For one project only, copy it to:

```text
<project-directory>/.claude/skills/animate-roblox-characters/
```

Then invoke it by name:

```text
Use the animate-roblox-characters skill to make a fast, aggressive R15 sword attack.
```

The skill uses the portable `SKILL.md` Agent Skills format. Blender MCP operation names are discovered at runtime, so the same skill folder is shared by Codex and Claude instead of maintaining divergent copies.

## One-time R6 asset setup

Install the mandatory premade R6 pair once:

```sh
python3 animate-roblox-characters/scripts/fetch_assets.py --component r6-ik-fk-v222
```

The user supplies the creative request. The AI installs or transfers the authentic premade rig and performs all animation work. Every completed animation includes the final `.blend`, Roblox animation export, audits/notes, and an animated GIF encoded from sequential RGB renders rather than a screen recording. A network download, plugin install, local file dialog, or Roblox publish permission may require user authorization; the AI never delegates rigging, posing, keyframing, or polish.

## Crash-safe Blender workflow

The skill requires one already-open, interactive Blender GUI connected through Blender MCP for the entire task. It refuses command-line/background Blender sessions, never starts one Blender process per frame, and never tells Blender to quit when the animation is finished.

This guard was added after an observed automation crash ended in native image-thread code during Blender process shutdown. That signature indicates a native Blender/image-library teardown failure rather than a catchable Python exception. Reusing the GUI process avoids the repeated render-and-exit pattern that provoked the fault.

If Blender still closes unexpectedly:

1. Reopen the most recent saved working `.blend` in Blender 4.5 LTS.
2. Start Blender MCP in that same GUI process.
3. Ask the agent to continue from Phase 0; it must inspect the file before resuming.
4. Do not let an agent launch `blender --background`, spawn Blender with a subprocess, or auto-relaunch it after a disconnect.

The original crash report is intentionally not included because diagnostic reports can contain device identifiers, local account data, OS metadata, and filesystem paths.

## Premade authentic rigs only

- R6 always uses the actual V2.22 premade rig (or an actual Studio-exported R6 target). It includes `__PrimaryArmature`, `MasterControl`, IK/FK, the labeled/colored body controls, body variants, Rig Settings, Utilities, and Rig Texture workflow.
- R15 always uses a premade Roblox Studio R15 or the user's actual Studio character transferred through Cautioned's tools.
- The repository contains no generated Roblox player model, neutral imitation, or block-proxy fallback.

Tutorial mirrors such as `R6IKFIX.blend`, copied textures, and Lazy Viewport are not used. The skill obtains the rig from its original author and the tool from its current GitHub/Creator Store sources.

## Privacy

- No personal names, emails, usernames, local home paths, credentials, or MCP configuration files belong in this repository.
- External assets are hash-pinned, stored in a Git-ignored cache, and scanned for embedded home-directory data before publication.
- Third-party Blender MCP servers may have their own telemetry settings. Disable prompt, code, and screenshot telemetry when working privately.
- Run the repository privacy check before publishing:

```sh
python3 animate-roblox-characters/scripts/privacy_check.py .
```

The scan covers source and binary strings, filenames, local Git author configuration, commit history, common home-directory patterns, personal email addresses, and common secret formats. Generated animations, crash reports, MCP configuration, logs, and external asset caches are Git-ignored.

## Development

Run checks:

```sh
python3 -m unittest discover -s tests -v
python3 animate-roblox-characters/scripts/toolchain.py
python3 animate-roblox-characters/scripts/privacy_check.py .
```

Contributions should keep the canonical phase order and verification rules intact. New rig or MCP adapters must fail clearly when a required capability or premade authentic rig is unavailable and must never generate/substitute a player model or skip pose review.

## License

Repository-authored code is MIT. The bundled Cautioned extension remains GPL-3.0-or-later. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
