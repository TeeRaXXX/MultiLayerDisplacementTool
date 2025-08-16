# materials.py — ОБНОВЛЕННАЯ ВЕРСИЯ с новыми режимами смешивания в preview

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
# helpers (без изменений)
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
    
    # Проверяем, существует ли атрибут
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
    """Remove preview material from object and data."""
    if not obj or obj.type != 'MESH':
        return
        
    preview_name = f"MLD_Preview::{obj.name}"
    
    # Find the material index in object slots
    material_index = None
    for i, mat in enumerate(obj.data.materials):
        if mat and mat.name == preview_name:
            material_index = i
            break
    
    if material_index is not None:
        # Remove material from object slots
        try:
            obj.data.materials.pop(index=material_index)
            
            # Update polygon material indices to avoid invalid references
            for poly in obj.data.polygons:
                if poly.material_index == material_index:
                    # Set to first available material or 0
                    poly.material_index = 0 if len(obj.data.materials) > 0 else 0
                elif poly.material_index > material_index:
                    # Adjust indices for materials that came after the removed one
                    poly.material_index -= 1
            
            # Update mesh data
            obj.data.update()
            
        except Exception as e:
            print(f"[MLD] Failed to remove preview material from object slots: {e}")
    
    # Remove from bpy.data.materials
    mat = bpy.data.materials.get(preview_name)
    if mat:
        try:
            bpy.data.materials.remove(mat, do_unlink=True)
        except Exception as e:
            print(f"[MLD] Failed to remove preview material from bpy.data.materials: {e}")

# ----------------------------------------------------------------------------- #
# НОВЫЕ функции смешивания для shader nodes
# ----------------------------------------------------------------------------- #

def _build_simple_blend_nodes(nodes, links, base_color, base_height, layer_color,
                            layer_height, layer_mask, loc):
    """Построить Simple blend shader nodes."""
    
    # Clamp маску на всякий случай
    clamp_mask = nodes.new("ShaderNodeClamp")
    clamp_mask.location = (loc[0], loc[1] - 50)
    links.new(layer_mask, clamp_mask.inputs["Value"])
    
    # Смешивание цвета
    mix_color = nodes.new("ShaderNodeMixRGB")
    mix_color.location = (loc[0] + 150, loc[1])
    mix_color.blend_type = 'MIX'
    links.new(clamp_mask.outputs["Result"], mix_color.inputs["Fac"])
    links.new(base_color, mix_color.inputs["Color1"])
    links.new(layer_color, mix_color.inputs["Color2"])
    
    # Смешивание высоты
    mix_height = nodes.new("ShaderNodeMixRGB")
    mix_height.location = (loc[0] + 150, loc[1] - 200)
    mix_height.blend_type = 'MIX'
    links.new(clamp_mask.outputs["Result"], mix_height.inputs["Fac"])
    links.new(base_height, mix_height.inputs["Color1"])
    links.new(layer_height, mix_height.inputs["Color2"])
    
    return mix_color.outputs["Color"], mix_height.outputs["Color"]

def _build_height_blend_nodes(nodes, links, base_color, base_height, layer_color, 
                            layer_height, layer_mask, height_offset, loc):
    """Построить Height Blend shader nodes (в стиле Substance Designer)."""
    
    # Разность высот
    sub = nodes.new("ShaderNodeMath")
    sub.location = (loc[0], loc[1] - 100)
    sub.operation = 'SUBTRACT'
    links.new(layer_height, sub.inputs[0])
    links.new(base_height, sub.inputs[1])
    
    # Нормализация разности высот
    add_norm = nodes.new("ShaderNodeMath")
    add_norm.location = (loc[0] + 150, loc[1] - 100)
    add_norm.operation = 'ADD'
    add_norm.inputs[1].default_value = 1.0
    links.new(sub.outputs["Value"], add_norm.inputs[0])
    
    mul_norm = nodes.new("ShaderNodeMath")
    mul_norm.location = (loc[0] + 300, loc[1] - 100)
    mul_norm.operation = 'MULTIPLY'
    mul_norm.inputs[1].default_value = 0.5
    links.new(add_norm.outputs["Value"], mul_norm.inputs[0])
    
    # Применяем height offset
    sub_offset = nodes.new("ShaderNodeMath")
    sub_offset.location = (loc[0] + 450, loc[1] - 100)
    sub_offset.operation = 'SUBTRACT'
    sub_offset.inputs[1].default_value = 1.0 - height_offset
    links.new(mul_norm.outputs["Value"], sub_offset.inputs[0])
    
    # Деление на height_offset для создания правильного scaling
    div_offset = nodes.new("ShaderNodeMath")
    div_offset.location = (loc[0] + 600, loc[1] - 100)
    div_offset.operation = 'DIVIDE'
    div_offset.inputs[1].default_value = max(0.001, height_offset)  # Избегаем деления на 0
    links.new(sub_offset.outputs["Value"], div_offset.inputs[0])
    
    # Clamp для получения blend_factor
    clamp_blend = nodes.new("ShaderNodeClamp")
    clamp_blend.location = (loc[0] + 750, loc[1] - 100)
    links.new(div_offset.outputs["Value"], clamp_blend.inputs["Value"])
    
    # Smoothstep для более естественного перехода
    # Используем формулу: t * t * (3 - 2 * t)
    mul_t = nodes.new("ShaderNodeMath")
    mul_t.location = (loc[0] + 900, loc[1] - 150)
    mul_t.operation = 'MULTIPLY'
    links.new(clamp_blend.outputs["Result"], mul_t.inputs[0])
    links.new(clamp_blend.outputs["Result"], mul_t.inputs[1])
    
    mul_2t = nodes.new("ShaderNodeMath")
    mul_2t.location = (loc[0] + 900, loc[1] - 200)
    mul_2t.operation = 'MULTIPLY'
    mul_2t.inputs[0].default_value = 2.0
    links.new(clamp_blend.outputs["Result"], mul_2t.inputs[1])
    
    sub_3_2t = nodes.new("ShaderNodeMath")
    sub_3_2t.location = (loc[0] + 1050, loc[1] - 200)
    sub_3_2t.operation = 'SUBTRACT'
    sub_3_2t.inputs[0].default_value = 3.0
    links.new(mul_2t.outputs["Value"], sub_3_2t.inputs[1])
    
    smoothstep = nodes.new("ShaderNodeMath")
    smoothstep.location = (loc[0] + 1200, loc[1] - 175)
    smoothstep.operation = 'MULTIPLY'
    links.new(mul_t.outputs["Value"], smoothstep.inputs[0])
    links.new(sub_3_2t.outputs["Value"], smoothstep.inputs[1])
    
    # Применяем маску к smoothstep результату
    mul_mask = nodes.new("ShaderNodeMath")
    mul_mask.location = (loc[0] + 1350, loc[1] - 50)
    mul_mask.operation = 'MULTIPLY'
    links.new(smoothstep.outputs["Value"], mul_mask.inputs[0])
    links.new(layer_mask, mul_mask.inputs[1])
    
    # Финальное смешивание цвета
    mix_color = nodes.new("ShaderNodeMixRGB")
    mix_color.location = (loc[0] + 1500, loc[1])
    mix_color.blend_type = 'MIX'
    links.new(mul_mask.outputs["Value"], mix_color.inputs["Fac"])
    links.new(base_color, mix_color.inputs["Color1"])
    links.new(layer_color, mix_color.inputs["Color2"])
    
    # Финальное смешивание высоты
    mix_height = nodes.new("ShaderNodeMixRGB")
    mix_height.location = (loc[0] + 1500, loc[1] - 200)
    mix_height.blend_type = 'MIX'
    links.new(mul_mask.outputs["Value"], mix_height.inputs["Fac"])
    links.new(base_height, mix_height.inputs["Color1"])
    links.new(layer_height, mix_height.inputs["Color2"])
    
    return mix_color.outputs["Color"], mix_height.outputs["Color"]

def _build_switch_blend_nodes(nodes, links, base_color, base_height, layer_color,
                            layer_height, layer_mask, switch_opacity, loc):
    """Построить Switch blend shader nodes."""
    
    # Комбинируем opacity с маской
    mul_switch = nodes.new("ShaderNodeMath")
    mul_switch.location = (loc[0], loc[1] - 50)
    mul_switch.operation = 'MULTIPLY'
    mul_switch.inputs[0].default_value = switch_opacity
    links.new(layer_mask, mul_switch.inputs[1])
    
    # Clamp результат
    clamp_switch = nodes.new("ShaderNodeClamp")
    clamp_switch.location = (loc[0] + 150, loc[1] - 50)
    links.new(mul_switch.outputs["Value"], clamp_switch.inputs["Value"])
    
    # Смешивание цвета
    mix_color = nodes.new("ShaderNodeMixRGB")
    mix_color.location = (loc[0] + 300, loc[1])
    mix_color.blend_type = 'MIX'
    links.new(clamp_switch.outputs["Result"], mix_color.inputs["Fac"])
    links.new(base_color, mix_color.inputs["Color1"])
    links.new(layer_color, mix_color.inputs["Color2"])
    
    # Смешивание высоты
    mix_height = nodes.new("ShaderNodeMixRGB")
    mix_height.location = (loc[0] + 300, loc[1] - 200)
    mix_height.blend_type = 'MIX'
    links.new(clamp_switch.outputs["Result"], mix_height.inputs["Fac"])
    links.new(base_height, mix_height.inputs["Color1"])
    links.new(layer_height, mix_height.inputs["Color2"])
    
    return mix_color.outputs["Color"], mix_height.outputs["Color"]

def _build_layer_blend_nodes_new(nodes, links, base_color, base_height, layer_color, layer_height, 
                                layer_mask, blend_mode, height_offset=0.5, switch_opacity=0.5, loc=(0,0)):
    """
    Построить shader nodes для ВСЕХ режимов смешивания включая Simple.
    """
    
    if blend_mode == 'SIMPLE':
        return _build_simple_blend_nodes(nodes, links, base_color, base_height,
                                       layer_color, layer_height, layer_mask, loc)
    elif blend_mode == 'HEIGHT_BLEND':
        return _build_height_blend_nodes(nodes, links, base_color, base_height, 
                                       layer_color, layer_height, layer_mask, 
                                       height_offset, loc)
    elif blend_mode == 'SWITCH':
        return _build_switch_blend_nodes(nodes, links, base_color, base_height,
                                       layer_color, layer_height, layer_mask,
                                       switch_opacity, loc)
    else:
        # Fallback к простому mix (как Simple)
        mix = nodes.new("ShaderNodeMixRGB")
        mix.location = loc
        mix.blend_type = 'MIX'
        links.new(layer_mask, mix.inputs["Fac"])
        links.new(base_color, mix.inputs["Color1"])
        links.new(layer_color, mix.inputs["Color2"])
        return mix.outputs["Color"], layer_height

# ----------------------------------------------------------------------------- #
# ОБНОВЛЕННАЯ основная функция preview shader
# ----------------------------------------------------------------------------- #

def build_heightlerp_preview_shader_new(obj: bpy.types.Object, s,
                                       preview_influence: Optional[float] = None,
                                       preview_contrast: Optional[float] = None) -> Optional[bpy.types.Material]:
    """
    ОБНОВЛЕННЫЙ preview shader с новыми режимами смешивания.
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

    # Create/clear preview material
    mat = _material_get_or_create(obj)
    nt = mat.node_tree; nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (3000, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (2800, 0)
    bsdf.inputs["Roughness"].default_value = 0.5
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    uv = nodes.new("ShaderNodeUVMap"); uv.location = (-520, 0)
    uv.uv_map = uv_name

    print(f"[MLD] Building preview with NEW blending system for {len(layers)} layers")

    # Построить layered blend с использованием новой системы
    current_color = None
    current_height = None
    y = 0

    for idx, L in enumerate(layers):
        base_img, h_img = _layer_images(L)

        # Color и height nodes для этого слоя
        color_node = _img_node(nodes, links, base_img, uv, getattr(L, "tiling", 1.0),
                              loc=(-260, y), non_color=False)
        color_socket = color_node.outputs["Color"]

        h_node = _img_node(nodes, links, h_img, uv, getattr(L, "tiling", 1.0),
                          loc=(-260, y - 180), non_color=True)
        
        # НОВОЕ: используем strength и bias из слоя
        h_scalar = _height_scalar(nodes, links, h_node.outputs["Color"],
                                 getattr(L, "strength", 1.0), getattr(L, "bias", 0.0),
                                 loc=(-260, y - 180))

        if idx == 0:
            # Первый слой - без смешивания
            current_color = color_socket
            current_height = h_scalar
            print(f"[MLD] Layer {idx}: Base layer (no blending)")
        else:
            # Применяем маску
            mask_socket = _mask_factor(nodes, links, getattr(L, "mask_name", "") or "", infl, y=y - 40)
            
            # НОВОЕ: применяем новое смешивание
            blend_mode = getattr(L, "blend_mode", 'HEIGHT_BLEND')
            height_offset = getattr(L, "height_offset", 0.5)
            switch_opacity = getattr(L, "switch_opacity", 0.5)
            
            print(f"[MLD] Layer {idx}: {blend_mode} mode", end="")
            if blend_mode == 'SIMPLE':
                print(" (direct mask)")
            elif blend_mode == 'HEIGHT_BLEND':
                print(f" (offset={height_offset})")
            elif blend_mode == 'SWITCH':
                print(f" (opacity={switch_opacity})")
            else:
                print()
            
            current_color, current_height = _build_layer_blend_nodes_new(
                nodes, links, current_color, current_height, color_socket, h_scalar,
                mask_socket, blend_mode, height_offset, switch_opacity, loc=(800 + idx * 400, y)
            )

        y -= 400

    # Подключаем финальный результат
    if current_color:
        links.new(current_color, bsdf.inputs["Base Color"])

    _assign_preview_slot0(obj, mat)
    print(f"[MLD] ✓ NEW preview material created with updated blending")
    return mat

# COMPATIBILITY: Алиас для старого названия функции
def build_heightlerp_preview_shader(obj: bpy.types.Object, s,
                                   preview_influence: Optional[float] = None,
                                   preview_contrast: Optional[float] = None) -> Optional[bpy.types.Material]:
    """Compatibility wrapper for the new blending system."""
    return build_heightlerp_preview_shader_new(obj, s, preview_influence, preview_contrast)

# ----------------------------------------------------------------------------- #
# Остальные функции остаются без изменений
# ----------------------------------------------------------------------------- #

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
            if vc_channel in {'R', 'G', 'B', 'A'}:
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
            elif channel == 'A':
                # For alpha channel, we need to use the alpha output from the vertex color attribute
                mask_output = vc_attr.outputs["Alpha"]
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
        print(f"[MLD] Failed to build packed VC preview shader: {e}")
        import traceback
        traceback.print_exc()
        return None

def build_packed_texture_mask_shader(obj: bpy.types.Object, s) -> bpy.types.Material:
    """
    Create a shader that reads from packed texture mask and blends materials.
    Uses proper mix nodes for material blending based on texture mask channels.
    """
    try:
        if not obj or obj.type != 'MESH':
            return None
            
        me = obj.data
        texture_name = getattr(s, 'texture_mask_name', 'MLD_Mask')
        uv_name = getattr(s, 'texture_mask_uv', 'UVMap')  # Используем UV из настроек
        
        print(f"[MLD] Starting build_packed_texture_mask_shader for object: {obj.name}")
        print(f"[MLD] Using texture mask: {texture_name}")
        print(f"[MLD] Using UV layer: {uv_name}")
        
        # Проверяем что UV слой существует
        uv_layer_exists = False
        if hasattr(me, "uv_layers"):
            for uv in me.uv_layers:
                if uv.name == uv_name:
                    uv_layer_exists = True
                    break
        
        if not uv_layer_exists:
            print(f"[MLD] Error: UV layer '{uv_name}' not found on mesh")
            available_uvs = [uv.name for uv in me.uv_layers] if hasattr(me, "uv_layers") else []
            print(f"[MLD] Available UV layers: {available_uvs}")
            return None
        
        # Get texture
        texture = bpy.data.images.get(texture_name)
        if not texture:
            print(f"[MLD] Error: Texture '{texture_name}' not found")
            return None
        
        # Get layers with channel assignments
        layers_data = []
        for i, L in enumerate(s.layers):
            if not L.enabled or not L.material:
                continue
            vc_channel = getattr(L, "vc_channel", 'NONE')
            if vc_channel in {'R', 'G', 'B', 'A'}:
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
            print("[MLD] No layers with channel assignments found")
            return None

        # Create/clear preview material
        mat_name = f"MLD_TextureMask::{obj.name}"
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

        # UV Map node - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ UV СЛОЙ
        uv = nodes.new("ShaderNodeUVMap")
        uv.location = (-1000, 0)
        uv.uv_map = uv_name  # Это ключевое исправление!
        print(f"[MLD] Set UV map node to use: {uv_name}")

        # Texture node for mask - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ UV
        tex_mask = nodes.new("ShaderNodeTexImage")
        tex_mask.location = (-1000, -300)
        tex_mask.image = texture
        tex_mask.interpolation = 'Cubic'
        tex_mask.extension = 'REPEAT'
        # Подключаем правильный UV к текстуре маски
        links.new(uv.outputs["UV"], tex_mask.inputs["Vector"])
        print(f"[MLD] Connected UV '{uv_name}' to mask texture")

        # Separate RGB to get individual channels
        sep_rgb = nodes.new("ShaderNodeSeparateRGB")
        sep_rgb.location = (-800, -300)
        links.new(tex_mask.outputs["Color"], sep_rgb.inputs["Image"])

        # Create mapping nodes for each layer
        x_offset = 0
        y_offset = 200
        layer_outputs = []
        
        for data in layers_data:
            L = data['layer']
            channel = data['channel']
            base_img = data['base_img']
            
            # Create mapping node for tiling - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ UV
            mapping = nodes.new("ShaderNodeMapping")
            mapping.location = (x_offset, y_offset)
            tiling = getattr(L, "tiling", 1.0)
            mapping.inputs["Scale"].default_value = (tiling, tiling, 1.0)
            # Подключаем правильный UV к mapping
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
            elif channel == 'A':
                # For alpha channel, we need to use the alpha output from the texture
                mask_output = tex_mask.outputs["Alpha"]
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
                infl, contr = _get_preview_params(s)
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
                    
                    # Height mapping - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ UV
                    h_mapping = nodes.new("ShaderNodeMapping")
                    h_mapping.location = (1000, -200)
                    h_mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
                    
                    # Подключаем правильный UV к height mapping
                    links.new(uv.outputs["UV"], h_mapping.inputs["Vector"])
                    links.new(h_mapping.outputs["Vector"], h_tex.inputs["Vector"])
                    links.new(h_tex.outputs["Color"], bump.inputs["Height"])
                    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
                    break

        # Don't assign material here - let the caller handle assignment
        
        print(f"[MLD] Successfully created packed texture mask shader with {len(layers_data)} layers using UV '{uv_name}'")
        return mat
        
    except Exception as e:
        print(f"[MLD] Failed to build packed texture mask shader: {e}")
        import traceback
        traceback.print_exc()
        return None

def ensure_preview_material(obj: bpy.types.Object, s) -> None:
    """Build the HeightLerp-style preview material for the object."""
    build_heightlerp_preview_shader_new(obj, s)