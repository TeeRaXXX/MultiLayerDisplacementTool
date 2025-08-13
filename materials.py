# materials.py — HeightLerp-like preview shader for Multi Layer Displacement Tool
# This ONLY affects viewport preview material; displacement logic is untouched.

from __future__ import annotations
import bpy
from typing import Optional, Tuple
from .sampling import (
    find_basecolor_image_and_uv,
    find_image_and_uv_from_displacement,
    active_uv_layer_name,
)

# Mask >= STRICT_THR → full override of lower stack (like "hard" paint = 1.0)
STRICT_THR = 0.999


# ----------------------------------------------------------------------------- #
# helpers
# ----------------------------------------------------------------------------- #

def _get_preview_params(s) -> Tuple[float, float]:
    """Read preview influence/contrast from settings with sane defaults."""
    influence = getattr(s, "preview_mask_influence", 1.0)
    contrast  = getattr(s, "preview_contrast", 1.0)
    try:
        influence = float(influence)
    except Exception:
        influence = 1.0
    try:
        contrast = float(contrast)
    except Exception:
        contrast = 1.0
    return influence, contrast


def _img_node(nodes, links, img: Optional[bpy.types.Image],
              uv_node: bpy.types.Node, tiling: float,
              loc=(0, 0), non_color: bool = False):
    """UVMap → Mapping(scale by tiling) → Image (or RGB fallback).
       Returns a node that has .outputs['Color']."""
    map_node = nodes.new("ShaderNodeMapping"); map_node.location = (loc[0] - 220, loc[1])
    sx = max(1e-6, float(tiling))
    map_node.inputs["Scale"].default_value = (sx, sx, 1.0)
    links.new(uv_node.outputs["UV"], map_node.inputs["Vector"])

    if img:
        tex = nodes.new("ShaderNodeTexImage"); tex.location = (loc[0], loc[1])
        tex.image = img
        tex.interpolation = 'Cubic'
        tex.extension = 'REPEAT'
        if non_color:
            try:
                tex.image.colorspace_settings.name = "Non-Color"
            except Exception:
                pass
        links.new(map_node.outputs["Vector"], tex.inputs["Vector"])
        return tex
    else:
        rgb = nodes.new("ShaderNodeRGB"); rgb.location = (loc[0], loc[1])
        rgb.outputs["Color"].default_value = (0.5, 0.5, 0.5, 1.0)
        return rgb


def _height_scalar(nodes, links, color_socket, mult: float, bias: float, loc=(0, 0)):
    """RGB → BW → *mult → +bias → clamp[0..1]; returns Value socket."""
    tobw = nodes.new("ShaderNodeRGBToBW"); tobw.location = (loc[0] + 160, loc[1])
    links.new(color_socket, tobw.inputs["Color"])

    mul = nodes.new("ShaderNodeMath"); mul.location = (loc[0] + 300, loc[1]); mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = float(mult)
    links.new(tobw.outputs["Val"], mul.inputs[0])

    add = nodes.new("ShaderNodeMath"); add.location = (loc[0] + 440, loc[1]); add.operation = 'ADD'
    add.inputs[1].default_value = float(bias)
    links.new(mul.outputs["Value"], add.inputs[0])

    clp = nodes.new("ShaderNodeClamp"); clp.location = (loc[0] + 580, loc[1])
    clp.inputs["Min"].default_value = 0.0
    clp.inputs["Max"].default_value = 1.0
    links.new(add.outputs["Value"], clp.inputs["Value"])
    return clp.outputs["Result"]


def _mask_factor(nodes, links, mask_name: str, influence: float, y=0):
    """Read mask (vertex color Red), apply influence and STRICT_THR. Returns Value 0..1."""
    if not mask_name or mask_name.strip() == "":
        # Если маска не указана, возвращаем fallback значение (0.5 для видимости слоя)
        fallback = nodes.new("ShaderNodeValue"); fallback.location = (-300, y)
        fallback.outputs["Value"].default_value = 0.5
        return fallback.outputs["Value"]
    
    attr = nodes.new("ShaderNodeAttribute"); attr.location = (-300, y)
    attr.attribute_name = mask_name or ""
    sep = nodes.new("ShaderNodeSeparateRGB"); sep.location = (-160, y)
    inp = sep.inputs.get("Image") or sep.inputs.get("Color") or sep.inputs[0]
    links.new(attr.outputs.get("Color", attr.outputs[0]), inp)

    clp = nodes.new("ShaderNodeClamp"); clp.location = (-20, y)
    clp.inputs["Min"].default_value = 0.0
    clp.inputs["Max"].default_value = 1.0
    links.new(sep.outputs.get("R") or sep.outputs[0], clp.inputs["Value"])

    mulI = nodes.new("ShaderNodeMath"); mulI.location = (120, y); mulI.operation = 'MULTIPLY'
    mulI.inputs[1].default_value = float(influence)
    links.new(clp.outputs["Result"], mulI.inputs[0])

    # hard override: max(fac, step(mask-STRICT_THR))
    gt = nodes.new("ShaderNodeMath"); gt.location = (260, y); gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = STRICT_THR
    links.new(clp.outputs["Result"], gt.inputs[0])

    mx = nodes.new("ShaderNodeMath"); mx.location = (400, y); mx.operation = 'MAXIMUM'
    links.new(mulI.outputs.get("Result") or mulI.outputs.get("Value") or mulI.outputs[0], mx.inputs[0])
    links.new(gt.outputs["Value"],  mx.inputs[1])

    clp2 = nodes.new("ShaderNodeClamp"); clp2.location = (540, y)
    links.new(mx.outputs["Value"], clp2.inputs["Value"])
    return clp2.outputs.get("Result") or clp2.outputs.get("Value") or clp2.outputs[0]


def _material_get_or_create(obj: bpy.types.Object) -> bpy.types.Material:
    name = f"MLD_Preview::{obj.name}"
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    return mat


def _layer_images(L) -> Tuple[Optional[bpy.types.Image], Optional[bpy.types.Image]]:
    """Resolve BaseColor img and Height img for a layer.
       If no height found, fallback to basecolor (preview only)."""
    base_img, _ = find_basecolor_image_and_uv(L.material) if L.material else (None, None)
    h_img, _ = find_image_and_uv_from_displacement(L.material) if L.material else (None, None)
    if h_img is None:
        h_img = base_img
    return base_img, h_img


def _assign_preview_slot0(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    """Force preview mat into slot 0 and ensure all faces use it."""
    ms = obj.data.materials
    if not ms:
        ms.append(mat)
    elif ms[0] is not mat:
        ms[0] = mat
    try:
        for p in obj.data.polygons:
            p.material_index = 0
        obj.data.update()
    except Exception:
        pass


def remove_preview_material(obj: bpy.types.Object) -> None:
    """(Optional) implement restore if you saved original slots somewhere."""
    # Keep as no-op unless you maintain original slots elsewhere.
    pass


# ----------------------------------------------------------------------------- #
# public api
# ----------------------------------------------------------------------------- #

def build_heightlerp_preview_shader(obj: bpy.types.Object, s,
                                    preview_influence: Optional[float] = None,
                                    preview_contrast: Optional[float] = None) -> Optional[bpy.types.Material]:
    """
    UE-like HeightLerp preview:
      for each layer B above accumulated A:
        Fac = saturate( Mask * Influence + (H_B - H_A) * Contrast )
        Color = lerp(A_Color, B_Color, Fac)
        H_accum = lerp(H_A, H_B, Fac)
        
    Alternative simple blend mode available via preview_blend setting.
    """
    if not obj or obj.type != 'MESH':
        return None

    me = obj.data
    uv_name = active_uv_layer_name(me)
    if not uv_name:
        mat = _material_get_or_create(obj)
        _assign_preview_slot0(obj, mat)
        return mat

    infl, contr = _get_preview_params(s)
    if preview_influence is not None:
        infl = float(preview_influence)
    if preview_contrast is not None:
        contr = float(preview_contrast)

    # Collect enabled layers with materials
    layers = [L for L in getattr(s, "layers", []) if getattr(L, "enabled", True) and getattr(L, "material", None)]
    if not layers:
        mat = _material_get_or_create(obj)
        _assign_preview_slot0(obj, mat)
        return mat

    # Check if we should use simple blend mode
    use_simple_blend = getattr(s, "preview_blend", False)

    # Create/clear preview material
    mat = _material_get_or_create(obj)
    nt = mat.node_tree; nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (680, 0)
    bsdf.inputs["Roughness"].default_value = 0.5
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    uv = nodes.new("ShaderNodeUVMap"); uv.location = (-520, 0)
    uv.uv_map = uv_name

    layered_col = None  # current blended color
    layered_h   = None  # current blended scalar height
    y = 0

    if use_simple_blend:
        # Simple additive blend mode - all layers visible
        for idx, L in enumerate(layers):
            base_img, h_img = _layer_images(L)

            # Color source for this layer
            color_node = _img_node(nodes, links, base_img, uv, getattr(L, "tiling", 1.0),
                                   loc=(-260, y), non_color=False)
            color_socket = color_node.outputs["Color"]

            # Height source (Non-Color)
            h_node = _img_node(nodes, links, h_img, uv, getattr(L, "tiling", 1.0),
                               loc=(-260, y - 180), non_color=True)
            h_scalar = _height_scalar(nodes, links, h_node.outputs["Color"],
                                      getattr(L, "multiplier", 1.0), getattr(L, "bias", 0.0),
                                      loc=(-260, y - 180))

            if layered_col is None:
                # initialize with the first layer
                layered_col = color_socket
                layered_h   = h_scalar
            else:
                # Simple additive blend with mask influence
                fac_mask = _mask_factor(nodes, links, getattr(L, "mask_name", "") or "", infl, y=y - 40)
                
                # Blend color: lerp(prev_color, this_color, Fac)
                mix = nodes.new("ShaderNodeMixRGB"); mix.location = (480, y)
                mix.blend_type = 'MIX'
                links.new(fac_mask, mix.inputs["Fac"])
                links.new(layered_col,            mix.inputs["Color1"])
                links.new(color_socket,           mix.inputs["Color2"])
                layered_col = mix.outputs["Color"]

                # Blend height: lerp(prev_height, this_height, Fac)
                hmix = nodes.new("ShaderNodeMixRGB"); hmix.location = (480, y - 180)
                hmix.blend_type = 'MIX'
                links.new(fac_mask, hmix.inputs["Fac"])
                links.new(layered_h, hmix.inputs["Color1"])
                links.new(h_scalar, hmix.inputs["Color2"])
                layered_h = hmix.outputs["Color"]

            y -= 260
    else:
        # Original HeightLerp blend mode
        for idx, L in enumerate(layers):
            base_img, h_img = _layer_images(L)

            # Color source for this layer
            color_node = _img_node(nodes, links, base_img, uv, getattr(L, "tiling", 1.0),
                                   loc=(-260, y), non_color=False)
            color_socket = color_node.outputs["Color"]

            # Height source (Non-Color)
            h_node = _img_node(nodes, links, h_img, uv, getattr(L, "tiling", 1.0),
                               loc=(-260, y - 180), non_color=True)
            h_scalar = _height_scalar(nodes, links, h_node.outputs["Color"],
                                      getattr(L, "multiplier", 1.0), getattr(L, "bias", 0.0),
                                      loc=(-260, y - 180))

            if layered_col is None:
                # initialize with the bottom layer
                layered_col = color_socket
                layered_h   = h_scalar
            else:
                # Mask term (0..1), with hard override at STRICT_THR
                fac_mask = _mask_factor(nodes, links, getattr(L, "mask_name", "") or "", infl, y=y - 40)

                # Height delta term: (H_B - H_A) * Contrast
                sub = nodes.new("ShaderNodeMath"); sub.location = (160, y - 180); sub.operation = 'SUBTRACT'
                links.new(h_scalar, sub.inputs[0])      # H_B
                links.new(layered_h, sub.inputs[1])     # H_A

                mulC = nodes.new("ShaderNodeMath"); mulC.location = (300, y - 180); mulC.operation = 'MULTIPLY'
                mulC.inputs[1].default_value = float(contr)
                links.new(sub.outputs["Value"], mulC.inputs[0])

                # Combine mask and height influence with minimum visibility
                addm = nodes.new("ShaderNodeMath"); addm.location = (440, y - 120); addm.operation = 'ADD'
                links.new(fac_mask, addm.inputs[0])
                links.new(mulC.outputs["Value"], addm.inputs[1])

                # Ensure minimum visibility for each layer (0.1 minimum factor)
                max_node = nodes.new("ShaderNodeMath"); max_node.location = (520, y - 120); max_node.operation = 'MAXIMUM'
                max_node.inputs[1].default_value = 0.1
                links.new(addm.outputs["Value"], max_node.inputs[0])

                fac = nodes.new("ShaderNodeClamp"); fac.location = (660, y - 120)
                links.new(max_node.outputs["Value"], fac.inputs["Value"])

                # Blend color: lerp(prev_color, this_color, Fac)
                mix = nodes.new("ShaderNodeMixRGB"); mix.location = (560, y)
                mix.blend_type = 'MIX'
                links.new(fac.outputs["Result"], mix.inputs["Fac"])
                links.new(layered_col,            mix.inputs["Color1"])
                links.new(color_socket,           mix.inputs["Color2"])
                layered_col = mix.outputs["Color"]

                # Propagate height for next iteration: H = lerp(H_A, H_B, Fac)
                inv = nodes.new("ShaderNodeMath"); inv.location = (520, y - 220); inv.operation = 'SUBTRACT'
                inv.inputs[0].default_value = 1.0
                links.new(fac.outputs["Result"], inv.inputs[1])

                aterm = nodes.new("ShaderNodeMath"); aterm.location = (680, y - 210); aterm.operation = 'MULTIPLY'
                links.new(layered_h, aterm.inputs[0])
                links.new(inv.outputs["Value"], aterm.inputs[1])

                bterm = nodes.new("ShaderNodeMath"); bterm.location = (820, y - 210); bterm.operation = 'MULTIPLY'
                links.new(h_scalar, bterm.inputs[0])
                links.new(fac.outputs["Result"], bterm.inputs[1])

                hmix = nodes.new("ShaderNodeMath"); hmix.location = (960, y - 210); hmix.operation = 'ADD'
                links.new(aterm.outputs["Value"], hmix.inputs[0])
                links.new(bterm.outputs["Value"], hmix.inputs[1])

                layered_h = hmix.outputs.get("Result") or mix.outputs.get("Value") or mix.outputs[0]

            y -= 260

    # Drive BaseColor
    links.new(layered_col, bsdf.inputs["Base Color"])

    _assign_preview_slot0(obj, mat)
    return mat


# convenience wrapper if elsewhere referenced
def ensure_preview_material(obj: bpy.types.Object, s) -> None:
    """Build the HeightLerp-style preview material for the object."""
    build_heightlerp_preview_shader(obj, s)


def build_packed_vc_preview_shader(obj: bpy.types.Object, s) -> bpy.types.Material:
    """
    Create a shader that reads from packed vertex colors and blends materials.
    Simplified version: create attribute node with name "Color", output separate XYZ, use XYZ as masks.
    """
    try:
        if not obj or obj.type != 'MESH':
            return None
            
        me = obj.data
        vc_name = getattr(s, 'vc_attribute_name', 'Color')
        
        print(f"[MLD] Starting build_packed_vc_preview_shader for object: {obj.name}")
        print(f"[MLD] Using vertex color attribute: {vc_name}")
        
        # Get UV layer name
        uv_name = "UVMap"
        if me.uv_layers:
            uv_name = me.uv_layers[0].name
        print(f"[MLD] UV layer name: {uv_name}")
        
        # Get layers with VC channel assignments
        layers = []
        channel_assignments = {}
        
        for i, L in enumerate(s.layers):
            enabled = getattr(L, "enabled", False)
            material = getattr(L, "material", None)
            vc_channel = getattr(L, "vc_channel", 'NONE')
            
            print(f"[MLD] Layer {i}: enabled={enabled}, material={material.name if material else 'None'}, vc_channel={vc_channel}")
            
            if enabled and material:
                if vc_channel in {'R', 'G', 'B', 'A'}:
                    layers.append(L)
                    channel_assignments[vc_channel] = i
                    print(f"[MLD] Added layer {i} with channel {vc_channel}")

        print(f"[MLD] Valid layers with VC channels: {len(layers)}")
        print(f"[MLD] Channel assignments: {channel_assignments}")
        
        if not layers:
            print("[MLD] No layers with VC channel assignments found")
            return None

        # Create/clear preview material
        mat_name = f"MLD_PackedVC::{obj.name}"
        print(f"[MLD] Creating material: {mat_name}")
        
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            print(f"[MLD] Created new material: {mat.name}")
        else:
            print(f"[MLD] Using existing material: {mat.name}")
        
        nt = mat.node_tree
        nodes, links = nt.nodes, nt.links
        nodes.clear()
        print(f"[MLD] Cleared material nodes")

        # Output and BSDF
        print(f"[MLD] Creating output and BSDF nodes")
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (900, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (680, 0)
        bsdf.inputs["Roughness"].default_value = 0.5
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        # UV Map
        print(f"[MLD] Creating UV Map node")
        uv = nodes.new("ShaderNodeUVMap")
        uv.location = (-520, 0)
        uv.uv_map = uv_name

        # Create attribute node with name "Color" (as per user instruction)
        print(f"[MLD] Creating attribute node with name: {vc_name}")
        vc_attr = nodes.new("ShaderNodeAttribute")
        vc_attr.location = (-520, -200)
        vc_attr.attribute_name = vc_name
        print(f"[MLD] Created attribute node: {vc_attr.type} with name: {vc_name}")

        # Separate XYZ from the attribute (as per user instruction)
        print(f"[MLD] Creating separate XYZ node")
        sep_rgb = nodes.new("ShaderNodeSeparateRGB")
        sep_rgb.location = (-300, -200)
        links.new(vc_attr.outputs["Color"], sep_rgb.inputs["Color"])
        print(f"[MLD] Connected attribute to separate XYZ")

        # Get preview parameters
        infl, contr = _get_preview_params(s)
        use_simple_blend = getattr(s, "preview_blend", False)

        layered_col = None
        y = 0

        if use_simple_blend:
            # Simple additive blend mode
            for idx, L in enumerate(layers):
                base_img, h_img = _layer_images(L)
                vc_channel = getattr(L, "vc_channel", 'NONE')
                
                if vc_channel not in channel_assignments:
                    continue

                # Color source for this layer
                color_node = _img_node(nodes, links, base_img, uv, getattr(L, "tiling", 1.0),
                                       loc=(-260, y), non_color=False)
                color_socket = color_node.outputs["Color"]

                # Get mask value from packed vertex color channel (use XYZ outputs as masks)
                if vc_channel == 'R':
                    mask_socket = sep_rgb.outputs["R"]
                elif vc_channel == 'G':
                    mask_socket = sep_rgb.outputs["G"]
                elif vc_channel == 'B':
                    mask_socket = sep_rgb.outputs["B"]
                elif vc_channel == 'A':
                    mask_socket = sep_rgb.outputs["A"]
                else:
                    continue

                # Apply mask influence
                mul_infl = nodes.new("ShaderNodeMath")
                mul_infl.location = (120, y)
                mul_infl.operation = 'MULTIPLY'
                mul_infl.inputs[1].default_value = float(infl)
                links.new(mask_socket, mul_infl.inputs[0])

                # Clamp to 0-1
                clamp = nodes.new("ShaderNodeClamp")
                clamp.location = (260, y)
                links.new(mul_infl.outputs["Value"], clamp.inputs["Value"])

                if layered_col is None:
                    layered_col = color_socket
                else:
                    # Blend with previous layer
                    mix = nodes.new("ShaderNodeMixRGB")
                    mix.location = (480, y)
                    mix.blend_type = 'MIX'
                    links.new(clamp.outputs["Result"], mix.inputs["Fac"])
                    links.new(layered_col, mix.inputs["Color1"])
                    links.new(color_socket, mix.inputs["Color2"])
                    layered_col = mix.outputs["Color"]

                y -= 260
        else:
            # HeightLerp blend mode
            layered_h = None
            
            for idx, L in enumerate(layers):
                base_img, h_img = _layer_images(L)
                vc_channel = getattr(L, "vc_channel", 'NONE')
                
                if vc_channel not in channel_assignments:
                    continue

                # Color source for this layer
                color_node = _img_node(nodes, links, base_img, uv, getattr(L, "tiling", 1.0),
                                       loc=(-260, y), non_color=False)
                color_socket = color_node.outputs["Color"]

                # Height source (Non-Color)
                h_node = _img_node(nodes, links, h_img, uv, getattr(L, "tiling", 1.0),
                                   loc=(-260, y - 180), non_color=True)
                h_scalar = _height_scalar(nodes, links, h_node.outputs["Color"],
                                          getattr(L, "multiplier", 1.0), getattr(L, "bias", 0.0),
                                          loc=(-260, y - 180))

                # Get mask value from packed vertex color channel (use XYZ outputs as masks)
                if vc_channel == 'R':
                    mask_socket = sep_rgb.outputs["R"]
                elif vc_channel == 'G':
                    mask_socket = sep_rgb.outputs["G"]
                elif vc_channel == 'B':
                    mask_socket = sep_rgb.outputs["B"]
                elif vc_channel == 'A':
                    mask_socket = sep_rgb.outputs["A"]
                else:
                    continue

                # Apply mask influence
                mul_infl = nodes.new("ShaderNodeMath")
                mul_infl.location = (120, y)
                mul_infl.operation = 'MULTIPLY'
                mul_infl.inputs[1].default_value = float(infl)
                links.new(mask_socket, mul_infl.inputs[0])

                # Clamp to 0-1
                clamp = nodes.new("ShaderNodeClamp")
                clamp.location = (260, y)
                links.new(mul_infl.outputs["Value"], clamp.inputs["Value"])

                if layered_col is None:
                    layered_col = color_socket
                    layered_h = h_scalar
                else:
                    # Height delta term: (H_B - H_A) * Contrast
                    sub = nodes.new("ShaderNodeMath")
                    sub.location = (160, y - 180)
                    sub.operation = 'SUBTRACT'
                    links.new(h_scalar, sub.inputs[0])      # H_B
                    links.new(layered_h, sub.inputs[1])     # H_A

                    mulC = nodes.new("ShaderNodeMath")
                    mulC.location = (300, y - 180)
                    mulC.operation = 'MULTIPLY'
                    mulC.inputs[1].default_value = float(contr)
                    links.new(sub.outputs["Value"], mulC.inputs[0])

                    # Combine mask and height influence
                    addm = nodes.new("ShaderNodeMath")
                    addm.location = (440, y - 120)
                    addm.operation = 'ADD'
                    links.new(clamp.outputs["Result"], addm.inputs[0])
                    links.new(mulC.outputs["Value"], addm.inputs[1])

                    # Ensure minimum visibility
                    max_node = nodes.new("ShaderNodeMath")
                    max_node.location = (520, y - 120)
                    max_node.operation = 'MAXIMUM'
                    max_node.inputs[1].default_value = 0.1
                    links.new(addm.outputs["Value"], max_node.inputs[0])

                    fac = nodes.new("ShaderNodeClamp")
                    fac.location = (660, y - 120)
                    links.new(max_node.outputs["Value"], fac.inputs["Value"])

                    # Blend color
                    mix = nodes.new("ShaderNodeMixRGB")
                    mix.location = (560, y)
                    mix.blend_type = 'MIX'
                    links.new(fac.outputs["Result"], mix.inputs["Fac"])
                    links.new(layered_col, mix.inputs["Color1"])
                    links.new(color_socket, mix.inputs["Color2"])
                    layered_col = mix.outputs["Color"]

                    # Propagate height for next iteration
                    inv = nodes.new("ShaderNodeMath")
                    inv.location = (520, y - 220)
                    inv.operation = 'SUBTRACT'
                    inv.inputs[0].default_value = 1.0
                    links.new(fac.outputs["Result"], inv.inputs[1])

                    aterm = nodes.new("ShaderNodeMath")
                    aterm.location = (680, y - 210)
                    aterm.operation = 'MULTIPLY'
                    links.new(layered_h, aterm.inputs[0])
                    links.new(inv.outputs["Value"], aterm.inputs[1])

                    bterm = nodes.new("ShaderNodeMath")
                    bterm.location = (820, y - 210)
                    bterm.operation = 'MULTIPLY'
                    links.new(h_scalar, bterm.inputs[0])
                    links.new(fac.outputs["Result"], bterm.inputs[1])

                    hmix = nodes.new("ShaderNodeMath")
                    hmix.location = (960, y - 210)
                    hmix.operation = 'ADD'
                    links.new(aterm.outputs["Value"], hmix.inputs[0])
                    links.new(bterm.outputs["Value"], hmix.inputs[1])

                    layered_h = hmix.outputs.get("Result") or hmix.outputs.get("Value") or hmix.outputs[0]

                y -= 260

        # Drive BaseColor
        if layered_col:
            links.new(layered_col, bsdf.inputs["Base Color"])

        # Assign material to slot 0
        print(f"[MLD] Assigning material to object")
        _assign_preview_slot0(obj, mat)
        
        print(f"[MLD] Created packed VC preview shader using '{vc_name}' attribute")
        print(f"[MLD] Material '{mat.name}' assigned to object '{obj.name}'")
        print(f"[MLD] build_packed_vc_preview_shader completed successfully")
        return mat
        
    except Exception as e:
        print(f"[MLD] Error in build_packed_vc_preview_shader: {e}")
        import traceback
        traceback.print_exc()
        return None
