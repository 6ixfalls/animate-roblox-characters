# Roblox–Blender Toolchain

Read this during Phase 0. The machine-readable source and hash inventory is `assets/toolchain-manifest.json`.

## Manual prerequisites

Install Blender 4.5+, a Blender MCP connection, Pillow `>=10,<13` in the external GIF encoder environment, and the chosen character rig manually. Motor6D import/export also requires manually installed Cautioned Blender and Studio plugins. Roblox Studio MCP is needed for Studio transfer and optional playback validation.

Open the installed rig in Blender and enable its required plugins before starting. The skill uses installed tools; it does not download rigs, register add-ons, activate embedded rig scripts, or require a particular rig version or lineage signature. Inspect control behavior, driven meshes, and export mapping before keyframing.

Keep online access, auto-connect, and live sync disabled during ordinary authoring. If an explicit Studio transfer needs live sync, start it only for that operation and stop it afterward.

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
python3 animate-roblox-characters/scripts/toolchain.py --repository-only
python3 animate-roblox-characters/scripts/toolchain.py --audit-pillow
python3 animate-roblox-characters/scripts/toolchain.py --audit-archive <addon.zip>
python3 animate-roblox-characters/scripts/toolchain.py --audit-addon <candidate.py>
```

Run the first audit for offline repository readiness. Run `--audit-pillow` with the external Python environment that will execute `build_animation_preview.py`; require `ok: true` and record its exact `pillow_version`. Pillow is deliberately verified outside Blender because GIF encoding is external and Blender's bundled Python need not contain Pillow. After discovering external capabilities and inspecting the rig, run the full audit through the persistent Blender MCP Python session. Pass `blender_mcp_available=True` only after an actual Blender MCP arbitrary-Python call succeeds; importing `bpy` by itself does not prove MCP connectivity. Runtime readiness requires both this external MCP attestation and an in-process persistent-GUI Blender check.

Do not run the workflow-aware readiness audit as an ordinary shell command: a shell process is outside Blender and must fail the in-process check. The CLI keeps workflow and capability switches for controlled embedding and test harnesses, but the in-process call below is the sole runtime-readiness procedure.

`r15-bootstrap` is the only named workflow gate in this version. It additionally requires Studio MCP, the Creator Store animation plugin, and all three installed add-on operators (`rbxanim_import`, `rbxanim_rebuild`, and `rbxanim_export`); an unavailable operator is an error. Pass each availability boolean as true only after that capability has actually been verified. A missing attestation is a failed workflow requirement, not an optional warning. The audit verifies availability claims—it does not replace object and metadata inspection after transfer. For R6 or skinned-FBX paths, omit `required_workflow`, retain the verified Blender MCP and Pillow attestations, and explicitly verify the relevant source and export path: the installed `rbxanim_export` operator and joint mapping for Motor6D, or an armature-deformed mesh and `bpy.ops.export_scene.fbx` for skinned FBX.

The in-process equivalent for the default R15 path is:

```python
toolchain.full_audit(
    required_workflow="r15-bootstrap",
    blender_mcp_available=True,
    pillow_available=True,
    pillow_version="12.3.0",  # Use the exact version reported by --audit-pillow.
    studio_mcp_available=True,
    creator_plugin_available=True,
)
```

Pass `blender_mcp_available=True` only from code already executing through the discovered Blender MCP connection. Pass the Pillow values only after the separate external audit succeeds; the in-Blender audit consumes that attestation and does not import Pillow. For a non-R15 path, call `toolchain.full_audit(blender_mcp_available=True, pillow_available=True, pillow_version="12.3.0")` through that connection using the exact reported version, then perform the explicit rig and exporter checks described above.

For an untrusted `.blend`, disable Blender's script auto-execution, open the file in the persistent GUI, and call `inspect_blend_security.inspect_current_file()` through MCP. Static review reduces risk but does not prove arbitrary third-party code safe.
