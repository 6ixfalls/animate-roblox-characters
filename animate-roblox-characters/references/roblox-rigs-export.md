# Installed Roblox Rigs and Export

Read this before importing, selecting, or exporting a character.

## Installed character rigs

Rigs and Blender/Studio plugins are manually installed before the animation task. Use the chosen R6, R15, or custom character. Discover exact bone names, IK/FK controls, poles, constraints, and driven meshes in the open scene. Preserve the original file and save a separate working copy.

`rig_tools.inspect_rig()` reports structural readiness and the likely export route without requiring source hashes, embedded-script activation, or provenance markers. Confirm control behavior visually before keyframing. Missing rigs or required plugins are manual setup prerequisites.

## Motor6D transfer

For Studio transfers, confirm that the manually installed Cautioned Blender extension provides import, rebuild, and export operators, then run the workflow-aware toolchain audit for `r15-bootstrap`. Verify Studio MCP and the installed Creator Store plugin are available.

Use the selected Studio character with the installed Blender Animations (ultimate edition) plugin. Prefer a temporary live-sync transfer and stop the server after transfer. For file-based transfer, pass the supplied OBJ to `rig_tools.import_motor6d_obj(path)` in the persistent Blender session.

Require an armature and one associated rig-named `__*Meta` empty carrying `RigMeta` in the same `RIG:` collection. Preserve names, textures, accessories, and mapping properties (`is_transformable`, `transform`, `transform1`, `nicetransform`). Verify the resulting scene rather than inferring success from an invocation.

Never delegate animation work to the user. Manual installation is the prerequisite; the agent performs control mapping, posing, keyframing, polishing, auditing, and export.

## Stud-to-scene-unit calibration

Contact drift is specified in Roblox studs, while Blender reports scene-space distances. Before auditing planted contacts on an imported rig, determine `scene_units_per_stud` from evidence tied to that exact import:

1. Measure a known distance on the selected character or a temporary reference in Studio and record it in studs.
2. Measure the corresponding distance in the imported Blender scene, or use an explicitly known uniform import scale.
3. Compute `scene_units_per_stud = blender_scene_distance / studio_distance_studs`. Require positive, finite values and repeat the measurement if the axes or import scaling are ambiguous.
4. Pass that value to `animation_tools.audit_action()` whenever contact intervals are audited. The audit converts the `0.02`-stud contact limit to scene units and should report both quantities.

For locomotion, make the required checks explicit rather than allowing omitted loop/contact inputs to pass:

```python
animation_tools.audit_action(
    armature_name=armature_name,
    action_name=action_name,
    loop_start=loop_start,
    loop_end=loop_end,
    contact_intervals=contact_intervals,
    contact_drift_threshold=0.02,  # studs
    scene_units_per_stud=scene_units_per_stud,
    loop_required=True,
    contacts_required=True,
)
```

For a grounded one-shot, pass `loop_required=False`, `contacts_required=True`, and every intended support-contact interval. Pass `contacts_required=False` only for an action with no planted interval at all. Every final audit must provide both booleans explicitly; omission fails.

Do not infer this conversion from the label “R15,” from character height, or from a visual guess. Recalibrate after any import-scale change.

## Motor6D part rigs: `.rbxanim`

Use `.rbxanim` for classic R6/R15 part rigs with compatible installed plugins:

1. Preserve the Cautioned/Roblox mapping metadata.
2. Animate only inspected pose controls.
3. Keep the internal/deform armature constrained to the external controls.
4. Export the explicitly named action and audited frame range with `rig_tools.export_rbxanim()` through `object.rbxanims_bake_file`.
5. Import/play the result through the matching Studio plugin.

Generic FBX export is not a substitute for Motor6D mapping.

## Skinned Roblox rigs: FBX

Use FBX only after inspection verifies an armature-deformed Roblox skinned character and its expected R15 hierarchy. Follow Roblox's [Blender guidance](https://create.roblox.com/docs/art/blender):

- Unit system `None`; rotation in degrees.
- `Z Forward`, `Y Up`.
- Select only the selected armature and driven meshes.
- Disable leaf bones.
- Bake at one sample per frame with no simplification.
- Export exactly one active action; disable NLA-strip/all-action export.
- Export deform bones only, with evaluated control motion baked onto them.

## Studio validation

When Studio MCP and the imported animation are available:

1. Confirm the target hierarchy and rig type.
2. Load the animation on the target `Animator`.
3. Play several repetitions for loops.
4. Capture the viewport and inspect console output.
5. Fix ownership, permission, hierarchy, mapping, or playback errors before completion.

A local file dialog or publish permission may require one user authorization. Never delegate posing, keyframing, rigging, or curve polish.
