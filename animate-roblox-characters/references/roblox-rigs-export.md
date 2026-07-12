# Authentic Roblox Rigs and Export

Read this before importing, selecting, or exporting a character.

## R6: the colored/labeled workflow

The intended premade rig is Aeresei's [R6 IK + FK Blender Rig V2.22](https://devforum.roblox.com/t/r6-ik-fk-blender-rig-v222/3586405), not a six-box approximation. Verified identifiers include:

- `__PrimaryArmature` with `_Rbx_R6_Rig_` marker.
- `InternalArmature` with Roblox parts `HumanoidRootPart`, `Torso`, `Head`, `Left Arm`, `Right Arm`, `Left Leg`, and `Right Leg`.
- `MasterControl`, `LowerTorso-FK`, limb `*-IK`/`*-FK` controls, pole targets, grab points, and head target.
- Custom viewport control shapes and body-type variants.
- Orientation-colored/labeled body surfaces and the Rig Texture utility.
- Active Rig, Rig Settings, Utilities, Accessories, and weapon-sync scripts.

Install it with `fetch_assets.py`, copy the cached master, open with script auto-execution disabled, and call `activate_verified_r6_v222()`. Animate `__PrimaryArmature` controls only. The matching Studio `.rbxm` is part of the pinned download and contains no Script/LocalScript/ModuleScript instances.

## R15 and custom avatars

For R15, use the actual premade Roblox Studio R15 or the requested player's existing character:

1. Use Studio's rig builder to insert a stock premade R15 if no target exists, or select the real target character.
2. Install Cautioned's [Blender Animations (ultimate edition)](https://create.roblox.com/store/asset/16708835782/Blender-Animations-ultimate-edition) from the Creator Store.
3. Register the bundled Cautioned 2.6.3 Blender extension after its hash passes.
4. Export/transfer the selected character and reconstruct its Blender armature.
5. Preserve `__RigMeta`, object names, textures, accessories, and bone properties such as `is_transformable`, `transform`, `transform1`, and `nicetransform`.
6. Inspect and classify the imported armature before the first keyframe.

Do not use Roblox's skeleton-only project template as the visible character. Do not generate replacement body geometry.

## Motor6D part rigs: `.rbxanim`

Use `.rbxanim` for classic R6/R15 part rigs and the R6 V2.22 workflow:

1. Preserve the Cautioned/Roblox mapping metadata.
2. Animate only verified pose controls.
3. Keep the internal/deform armature constrained to the external controls.
4. Export the active animation with `authentic_rig.export_rbxanim()` through `object.rbxanims_bake_file`.
5. Import/play the result through the matching Studio plugin.

Generic FBX export is not a substitute for Motor6D mapping.

## Skinned Roblox rigs: FBX

Use FBX only after inspection verifies an armature-deformed Roblox skinned character and its expected R15 hierarchy. Follow Roblox's [Blender guidance](https://create.roblox.com/docs/art/blender):

- Unit system `None`; rotation in degrees.
- `Z Forward`, `Y Up`.
- Select only the authentic armature and driven meshes.
- Disable leaf bones.
- Bake at one sample per frame with no simplification.
- Export exactly one active action; disable NLA-strip/all-action export.
- Export deform bones only, with evaluated control motion baked onto them.

## Authenticity results

`authentic_rig.inspect_authenticity()` recognizes:

- `community-r6-ik-fk-control-rig`: verified control convention; Motor6D/`.rbxanim`.
- `studio-motor6d-import`: Cautioned/Studio metadata; Motor6D/`.rbxanim`.
- `studio-or-fbx-skinned-r15`: verified skinned R15; FBX.
- `generated-or-repository-proxy`: forbidden.
- `unknown` or `verify-before-export`: stop and verify.

Exact bone names must still be discovered at runtime.

## Studio validation

When Studio MCP and the imported animation are available:

1. Confirm the target hierarchy and rig type.
2. Load the animation on the target `Animator`.
3. Play several repetitions for loops.
4. Capture the viewport and inspect console output.
5. Fix ownership, permission, hierarchy, mapping, or playback errors before completion.

A local file dialog or publish permission may require one user authorization. Never delegate posing, keyframing, rigging, or curve polish.
