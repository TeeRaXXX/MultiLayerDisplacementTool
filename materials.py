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
    
    # Проверяем, существует ли атрибут (для случая, когда атрибуты уже удалены)
    try:
        attr = nodes.new("ShaderNodeAttribute"); attr.location = (-300, y)
        attr.attribute_name = mask_name or ""
        
        # Если атрибут не найден, возвращаем fallback
        if not attr.attribute_name or attr.attribute_name.strip() == "":
            fallback = nodes.new("ShaderNodeValue"); fallback.location = (-300, y)
            fallback.outputs["Value"].default_value = 0.5
            return fallback.outputs["Value"]
        
        sep = nodes.new("ShaderNodeSeparateRGB"); sep.location = (-160, y)
        inp = sep.inputs.get("Image") or sep.inputs.get("Color") or sep.inputs[0]
        links.new(attr.outputs.get("Color", attr.outputs[0]), inp)
    except Exception:
        # Если произошла ошибка при создании атрибута, возвращаем fallback
        fallback = nodes.new("ShaderNodeValue"); fallback.location = (-300, y)
        fallback.outputs["Value"].default_value = 0.5
        return fallback.outputs["Value"]

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
    Uses proper mix nodes for material blending based on vertex color channels.
    """
    try:
        if not obj or obj.type != 'MESH':
            return None
            
        me = obj.data
        vc_name = getattr(s, 'vc_attribute_name', 'Color')  # This should be the bake_vc_attribute_name when called from bake
        
        print(f"[MLD] Starting build_packed_vc_preview_shader for object: {obj.name}")
        print(f"[MLD] Using vertex color attribute: {vc_name}")
        
        # Get UV layer name
        uv_name = active_uv_layer_name(me)
        if not uv_name:
            print("[MLD] No UV layer found")
            return None
        
        # Get layers with VC channel assignments
        layers_data = []
        for i, L in enumerate(s.layers):
            if not L.enabled or not L.material:
                continue
            vc_channel = getattr(L, "vc_channel", 'NONE')
            if vc_channel in {'R', 'G', 'B'}:
                base_img, h_img = _layer_images(L)
                layers_data.append({
                    'index': i,
                    'layer': L,
                    'channel': vc_channel,
                    'base_img': base_img,
                    'height_img': h_img
                })
                print(f"[MLD] Added layer {i} with channel {vc_channel}")
        
        if not layers_data:
            print("[MLD] No layers with VC channel assignments found")
            return None

        # Create/clear preview material
        mat_name = f"MLD_PackedVC::{obj.name}"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
        
        nt = mat.node_tree
        nodes, links = nt.nodes, nt.links
        nodes.clear()

        # Create output and BSDF
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (2000, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (1800, 0)
        bsdf.inputs["Roughness"].default_value = 0.5
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        # UV Map node
        uv = nodes.new("ShaderNodeUVMap")
        uv.location = (-1000, 0)
        uv.uv_map = uv_name

        # Vertex Color attribute node
        vc_attr = nodes.new("ShaderNodeAttribute")
        vc_attr.location = (-1000, -300)
        vc_attr.attribute_name = vc_name
        
        # Check if the attribute exists
        if not vc_name or vc_name.strip() == "":
            print(f"[MLD] Error: No VC attribute name specified")
            return None
            
        # Debug: Check if the attribute actually exists on the mesh
        attr_exists = False
        if hasattr(me, "color_attributes"):
            attr_exists = attr_exists or me.color_attributes.get(vc_name) is not None
        if hasattr(me, "vertex_colors"):
            attr_exists = attr_exists or me.vertex_colors.get(vc_name) is not None
        if not attr_exists:
            print(f"[MLD] Error: VC attribute '{vc_name}' not found on mesh")
            print(f"[MLD] Available color_attributes: {[a.name for a in me.color_attributes] if hasattr(me, 'color_attributes') else 'N/A'}")
            print(f"[MLD] Available vertex_colors: {[a.name for a in me.vertex_colors] if hasattr(me, 'vertex_colors') else 'N/A'}")
            return None

        # Separate RGB to get individual channels
        sep_rgb = nodes.new("ShaderNodeSeparateRGB")
        sep_rgb.location = (-800, -300)
        
        # Get the correct output from the attribute node
        vc_output = None
        print(f"[MLD] Available outputs on attribute node: {[o.name for o in vc_attr.outputs]}")
        if "Color" in vc_attr.outputs:
            vc_output = vc_attr.outputs["Color"]
            print(f"[MLD] Using 'Color' output")
        elif "Fac" in vc_attr.outputs:
            vc_output = vc_attr.outputs["Fac"]
            print(f"[MLD] Using 'Fac' output")
        elif len(vc_attr.outputs) > 0:
            vc_output = vc_attr.outputs[0]  # Use first available output
            print(f"[MLD] Using first available output: {vc_attr.outputs[0].name}")
        else:
            print(f"[MLD] Error: No valid output found for attribute node")
            return None
        
        # Get the correct input for SeparateRGB node
        print(f"[MLD] Available inputs on SeparateRGB node: {[i.name for i in sep_rgb.inputs]}")
        sep_input = None
        if "Image" in sep_rgb.inputs:
            sep_input = sep_rgb.inputs["Image"]
            print(f"[MLD] Using 'Image' input")
        elif "Color" in sep_rgb.inputs:
            sep_input = sep_rgb.inputs["Color"]
            print(f"[MLD] Using 'Color' input")
        elif len(sep_rgb.inputs) > 0:
            sep_input = sep_rgb.inputs[0]  # Use first available input
            print(f"[MLD] Using first available input: {sep_rgb.inputs[0].name}")
        else:
            print(f"[MLD] Error: No valid input found for SeparateRGB node")
            return None
            
        links.new(vc_output, sep_input)

        # Get preview parameters
        infl, contr = _get_preview_params(s)
        use_simple_blend = getattr(s, "preview_blend", False)

        # Create texture nodes for each layer
        x_offset = -600
        y_offset = 200
        layer_outputs = []
        
        for data in layers_data:
            L = data['layer']
            channel = data['channel']
            base_img = data['base_img']
            
            # Create mapping node for tiling
            mapping = nodes.new("ShaderNodeMapping")
            mapping.location = (x_offset, y_offset)
            tiling = getattr(L, "tiling", 1.0)
            mapping.inputs["Scale"].default_value = (tiling, tiling, 1.0)
            links.new(uv.outputs["UV"], mapping.inputs["Vector"])
            
            # Create texture node or RGB fallback
            if base_img:
                tex = nodes.new("ShaderNodeTexImage")
                tex.location = (x_offset + 200, y_offset)
                tex.image = base_img
                tex.interpolation = 'Cubic'
                tex.extension = 'REPEAT'
                links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
                color_output = tex.outputs["Color"]
            else:
                rgb = nodes.new("ShaderNodeRGB")
                rgb.location = (x_offset + 200, y_offset)
                rgb.outputs["Color"].default_value = (0.5, 0.5, 0.5, 1.0)
                color_output = rgb.outputs["Color"]
            
            # Get mask value from appropriate channel
            if channel == 'R':
                mask_output = sep_rgb.outputs["R"]
            elif channel == 'G':
                mask_output = sep_rgb.outputs["G"]
            elif channel == 'B':
                mask_output = sep_rgb.outputs["B"]
            else:
                print(f"[MLD] Error: Invalid channel '{channel}'")
                return None
            
            layer_outputs.append({
                'color': color_output,
                'mask': mask_output,
                'layer': L
            })
            
            y_offset -= 300

        # Now blend layers together using Mix RGB nodes
        if len(layer_outputs) == 1:
            # Single layer - direct connection
            final_color = layer_outputs[0]['color']
        else:
            # Multiple layers - create blend chain
            x_pos = 400
            y_pos = 0
            
            # Start with first layer as base
            current_color = layer_outputs[0]['color']
            
            for i in range(1, len(layer_outputs)):
                # Create Mix RGB node for blending
                mix = nodes.new("ShaderNodeMixRGB")
                mix.location = (x_pos, y_pos)
                mix.blend_type = 'MIX'
                mix.use_clamp = True
                
                # Apply influence to mask
                if infl != 1.0:
                    mult = nodes.new("ShaderNodeMath")
                    mult.location = (x_pos - 200, y_pos - 100)
                    mult.operation = 'MULTIPLY'
                    mult.inputs[1].default_value = infl
                    links.new(layer_outputs[i]['mask'], mult.inputs[0])
                    
                    # Clamp the result
                    clamp = nodes.new("ShaderNodeClamp")
                    clamp.location = (x_pos - 100, y_pos - 100)
                    links.new(mult.outputs["Value"], clamp.inputs["Value"])
                    mask_input = clamp.outputs["Result"]
                else:
                    mask_input = layer_outputs[i]['mask']
                
                # Connect to mix node
                links.new(mask_input, mix.inputs["Fac"])
                links.new(current_color, mix.inputs["Color1"])
                links.new(layer_outputs[i]['color'], mix.inputs["Color2"])
                
                current_color = mix.outputs["Color"]
                x_pos += 300
                y_pos -= 150
            
            final_color = current_color

        # Connect final color to BSDF
        links.new(final_color, bsdf.inputs["Base Color"])

        # Optional: Add normal/bump mapping if height images exist
        if any(d.get('height_img') for d in layers_data):
            # Create a simple bump node setup
            bump = nodes.new("ShaderNodeBump")
            bump.location = (1600, -200)
            bump.inputs["Strength"].default_value = 0.5
            
            # For simplicity, use the first height map found
            for data in layers_data:
                if data.get('height_img'):
                    h_img = data['height_img']
                    
                    # Height texture
                    h_tex = nodes.new("ShaderNodeTexImage")
                    h_tex.location = (1200, -200)
                    h_tex.image = h_img
                    h_tex.interpolation = 'Cubic'
                    h_tex.extension = 'REPEAT'
                    
                    try:
                        h_tex.image.colorspace_settings.name = "Non-Color"
                    except:
                        pass
                    
                    # Height mapping
                    h_mapping = nodes.new("ShaderNodeMapping")
                    h_mapping.location = (1000, -200)
                    h_mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
                    
                    links.new(uv.outputs["UV"], h_mapping.inputs["Vector"])
                    links.new(h_mapping.outputs["Vector"], h_tex.inputs["Vector"])
                    links.new(h_tex.outputs["Color"], bump.inputs["Height"])
                    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
                    break

        # Don't assign material here - let the caller handle assignment
        # _assign_preview_slot0(obj, mat)
        
        print(f"[MLD] Successfully created packed VC shader with {len(layers_data)} layers")
        return mat
        
    except Exception as e:
        print(f"[MLD] Error in build_packed_vc_preview_shader: {e}")
        import traceback
        traceback.print_exc()
        return None
