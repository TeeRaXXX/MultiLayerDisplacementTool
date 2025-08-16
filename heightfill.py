# heightfill.py — НОВАЯ СИСТЕМА СМЕШИВАНИЯ с Height Blend и Switch

from __future__ import annotations
import bpy
from typing import List, Optional, Tuple
from .sampling import (
    make_sampler, find_image_and_uv_from_displacement,
    active_uv_layer_name, sample_height_at_loop,
)
from .attrs import ensure_float_attr, ensure_color_attr, point_red, loop_red, color_attr_exists
from .constants import OFFS_ATTR, ALPHA_PREFIX

def _get_evaluated_mesh(obj: bpy.types.Object, context):
    """Get mesh with modifiers applied for heightfill calculation."""
    try:
        # Get dependency graph
        depsgraph = context.evaluated_depsgraph_get()
        
        # Get evaluated object (with modifiers applied)
        obj_eval = obj.evaluated_get(depsgraph)
        
        # Get the evaluated mesh
        mesh_eval = obj_eval.data
        
        print(f"[MLD] Heightfill using evaluated mesh: {len(mesh_eval.vertices)} verts, {len(mesh_eval.polygons)} faces")
        return mesh_eval, obj_eval
        
    except Exception as e:
        print(f"[MLD] Failed to get evaluated mesh: {e}")
        print(f"[MLD] Falling back to original mesh: {len(obj.data.vertices)} verts")
        return obj.data, obj

def _ensure_output_attrs(me: bpy.types.Mesh, n_layers: int):
    """Ensure output attributes exist on ORIGINAL mesh."""
    # vector OFFS (point domain)
    ensure_float_attr(me, OFFS_ATTR, domain='POINT', data_type='FLOAT_VECTOR')
    # point-domain alphas per layer
    for i in range(n_layers):
        ensure_float_attr(me, f"{ALPHA_PREFIX}{i}", domain='POINT', data_type='FLOAT')

def _gather_layer_samplers(obj: bpy.types.Object, s) -> Tuple[List[Optional[object]], Optional[str]]:
    """For each enabled layer return ImageSampler or None; also return active UV name."""
    me = obj.data
    uv_name = active_uv_layer_name(me)
    samplers: List[Optional[object]] = []
    for L in s.layers:
        if not (L.enabled and L.material):
            samplers.append(None); continue
        img, _ = find_image_and_uv_from_displacement(L.material)
        samplers.append(make_sampler(img))
    return samplers, uv_name

def _transfer_result_to_original(original_me: bpy.types.Mesh, eval_me: bpy.types.Mesh, 
                                accum_offs: list, accum_alpha: list, n_layers: int):
    """Transfer heightfill results from evaluated mesh back to original mesh attributes."""
    
    # Prepare write access on ORIGINAL mesh
    offs_attr = original_me.attributes.get(OFFS_ATTR)
    alpha_attrs = [original_me.attributes.get(f"{ALPHA_PREFIX}{i}") for i in range(n_layers)]
    
    if not offs_attr:
        print("[MLD] Error: OFFS_ATTR not found on original mesh")
        return False
    
    # Calculate vertex correspondence (eval→orig mapping)
    orig_vcount = len(original_me.vertices)
    eval_vcount = len(eval_me.vertices)
    
    print(f"[MLD] Mapping: {eval_vcount} eval vertices → {orig_vcount} original vertices")
    
    # Direct mapping for same topology
    for vi in range(min(orig_vcount, eval_vcount)):
        if vi < len(accum_offs):
            ox, oy, oz = accum_offs[vi]
            offs_attr.data[vi].vector = (0.0, 0.0, oz)
            for i in range(n_layers):
                if alpha_attrs[i] and vi < len(accum_alpha[i]):
                    alpha_attrs[i].data[vi].value = accum_alpha[i][vi]
    
    original_me.update()
    return True

def _get_mask_value_for_loop(obj, eval_me, layer, li, vi, uv_name):
    """Get mask value for loop with proper mapping."""
    m = 0.0
    if layer.mask_name and color_attr_exists(obj.data, layer.mask_name):
        # Map work mesh loop to original mesh loop properly
        if li < len(obj.data.loops):
            orig_li = li
        else:
            # For modified meshes, find closest original loop
            try:
                work_uv = eval_me.uv_layers[uv_name].data[li].uv
                min_dist = float('inf')
                orig_li = 0
                for orig_loop_idx in range(min(len(obj.data.loops), 1000)):  # Limit search
                    try:
                        orig_uv = obj.data.uv_layers[uv_name].data[orig_loop_idx].uv
                        dist = ((work_uv.x - orig_uv.x) ** 2 + (work_uv.y - orig_uv.y) ** 2) ** 0.5
                        if dist < min_dist:
                            min_dist = dist
                            orig_li = orig_loop_idx
                    except Exception:
                        continue
            except Exception:
                orig_li = min(li, len(obj.data.loops) - 1)
        
        m = loop_red(obj.data, layer.mask_name, orig_li)
        if m is None:
            # Fallback to vertex-based reading
            orig_vi = min(vi, len(obj.data.vertices) - 1)
            m = point_red(obj.data, layer.mask_name, orig_vi) or 0.0
    return m

def _get_height_value_for_loop(eval_me, uv_name, li, layer, sampler):
    """Get height value for loop."""
    if sampler is None:
        return 0.0
    
    try:
        h = sample_height_at_loop(eval_me, uv_name, li, max(1e-8, layer.tiling), sampler)
        return h
    except Exception:
        return 0.0

def _blend_layers_new(layer_data, settings):
    """
    НОВАЯ СИСТЕМА СМЕШИВАНИЯ с Height Blend и Switch modes.
    
    Args:
        layer_data: List of dicts with 'height', 'mask', 'layer' for each layer
        settings: Global MLD settings
    
    Returns:
        (final_height, alphas_list)
    """
    if not layer_data:
        return 0.0, []
    
    n_layers = len(layer_data)
    alphas = [0.0] * n_layers
    
    # Начинаем с первого слоя (базовый слой, без смешивания)
    current_height = layer_data[0]['height'] * layer_data[0]['mask']
    alphas[0] = layer_data[0]['mask']
    
    # Смешиваем последующие слои
    for i in range(1, n_layers):
        layer = layer_data[i]
        L = layer['layer']
        
        # Пропускаем отключенные слои или слои без маски
        if not L.enabled or layer['mask'] <= 0.0:
            continue
            
        if L.blend_mode == 'SIMPLE':
            current_height, alpha = _apply_simple_blend(
                current_height,
                layer['height'],
                layer['mask']
            )
            alphas[i] = alpha
            
        elif L.blend_mode == 'HEIGHT_BLEND':
            current_height, alpha = _apply_height_blend(
                current_height, 
                layer['height'], 
                layer['mask'],
                L.height_offset
            )
            alphas[i] = alpha
            
        elif L.blend_mode == 'SWITCH':
            current_height, alpha = _apply_switch_blend(
                current_height,
                layer['height'],
                layer['mask'],
                L.switch_opacity
            )
            alphas[i] = alpha
    
    return current_height, alphas

def _apply_simple_blend(base_height, layer_height, layer_mask):
    """
    Применить простое смешивание по маске.
    
    Args:
        base_height: Высота от слоев ниже
        layer_height: Высота текущего слоя
        layer_mask: Сила маски (0-1) - прямое управление смешиванием
    
    Returns:
        (blended_height, alpha_contribution)
    """
    if layer_mask <= 0.0:
        return base_height, 0.0
    
    # Прямое использование маски как blend factor
    final_blend = max(0.0, min(1.0, layer_mask))
    
    # Простая линейная интерполяция
    blended_height = base_height * (1.0 - final_blend) + layer_height * final_blend
    
    return blended_height, final_blend

def _apply_height_blend(base_height, layer_height, layer_mask, height_offset):
    """
    Применить Height Blend в стиле Substance Designer.
    
    Args:
        base_height: Высота от слоев ниже
        layer_height: Высота текущего слоя  
        layer_mask: Сила маски (0-1)
        height_offset: Порог высоты (0-1)
    
    Returns:
        (blended_height, alpha_contribution)
    """
    if layer_mask <= 0.0:
        return base_height, 0.0
    
    # Расчет разности высот
    height_diff = layer_height - base_height
    
    # Применяем height_offset как порог
    # При offset=0: слой никогда не проступает
    # При offset=1: слой всегда проступает полностью
    # При offset=0.5: сбалансированное смешивание на основе разности высот
    
    # Преобразуем height_offset в blend_factor
    # Это имитирует поведение height blend из Substance Designer
    if height_offset <= 0.0:
        blend_factor = 0.0
    elif height_offset >= 1.0:
        blend_factor = 1.0
    else:
        # Плавное смешивание на основе разности высот и offset
        # Offset действует как смещение - больший offset означает, что слой проступает легче
        normalized_diff = (height_diff + 1.0) * 0.5  # Нормализуем в диапазон 0-1
        
        # Создаем S-образную кривую для более естественного смешивания
        # height_offset контролирует точку перехода
        blend_factor = max(0.0, min(1.0, 
            (normalized_diff - (1.0 - height_offset)) / height_offset
        ))
        
        # Сглаживание с помощью smoothstep
        if blend_factor > 0.0 and blend_factor < 1.0:
            blend_factor = blend_factor * blend_factor * (3.0 - 2.0 * blend_factor)
    
    # Применяем маску к blend_factor
    final_blend = blend_factor * layer_mask
    
    # Линейная интерполяция
    blended_height = base_height * (1.0 - final_blend) + layer_height * final_blend
    
    return blended_height, final_blend

def _apply_switch_blend(base_height, layer_height, layer_mask, switch_opacity):
    """
    Применить простое Switch/lerp смешивание.
    
    Args:
        base_height: Высота от слоев ниже
        layer_height: Высота текущего слоя
        layer_mask: Сила маски (0-1) 
        switch_opacity: Фактор переключения (0-1)
    
    Returns:
        (blended_height, alpha_contribution)
    """
    if layer_mask <= 0.0 or switch_opacity <= 0.0:
        return base_height, 0.0
    
    # Комбинируем switch opacity с маской слоя
    final_blend = switch_opacity * layer_mask
    final_blend = max(0.0, min(1.0, final_blend))
    
    # Простая линейная интерполяция
    blended_height = base_height * (1.0 - final_blend) + layer_height * final_blend
    
    return blended_height, final_blend

def solve_heightfill(obj: bpy.types.Object, s, context=None, work_mesh: bpy.types.Mesh = None) -> bool:
    """
    ОБНОВЛЕННАЯ Core heightfill с новой системой смешивания слоев.
    Returns True on success.
    """
    if context is None:
        context = bpy.context
    
    # Use provided work_mesh or get evaluated mesh
    if work_mesh:
        eval_me = work_mesh
        print(f"[MLD] Using provided work mesh: {len(eval_me.vertices)} vertices")
    else:
        eval_me, eval_obj = _get_evaluated_mesh(obj, context)
    
    if eval_me is None or eval_me.loop_triangles is None:
        eval_me.calc_loop_triangles()

    # UV layer (check both work mesh and original)
    uv_name = active_uv_layer_name(eval_me)
    if not uv_name:
        uv_name = active_uv_layer_name(obj.data)  # fallback to original
    if not uv_name:
        print("[MLD] Error: No UV layer found")
        return False

    # samplers per layer
    samplers, uv_from = _gather_layer_samplers(obj, s)
    if not any(samplers):
        print("[MLD] Error: No valid samplers found")
        return False

    n_layers = len(s.layers)
    
    # Ensure output attributes exist on ORIGINAL mesh
    _ensure_output_attrs(obj.data, n_layers)

    # Init accumulators for WORK mesh
    vcount = len(eval_me.vertices)
    accum_offs = [(0.0, 0.0, 0.0)] * vcount
    accum_alpha = [ [0.0]*vcount for _ in range(n_layers) ]

    print(f"[MLD] Processing {len(eval_me.polygons)} polygons with NEW blending system...")

    # Process polygons on WORK mesh
    for poly in eval_me.polygons:
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            vi = eval_me.loops[li].vertex_index

            # Собираем данные по всем слоям для этого loop
            layer_data = []
            
            for i, L in enumerate(s.layers):
                if not L.enabled:
                    layer_data.append({'height': 0.0, 'mask': 0.0, 'layer': L})
                    continue
                    
                # Получаем значение маски (из оригинального меша)
                m = _get_mask_value_for_loop(obj, eval_me, L, li, vi, uv_name)
                
                # Получаем значение высоты (из work mesh)
                h = _get_height_value_for_loop(eval_me, uv_name, li, L, samplers[i])
                
                # НОВОЕ: Применяем strength и bias слоя ДО смешивания
                h_processed = h * L.strength + L.bias
                
                layer_data.append({
                    'height': h_processed,
                    'mask': m,
                    'layer': L
                })

            # НОВЫЙ АЛГОРИТМ СМЕШИВАНИЯ
            final_height, alphas = _blend_layers_new(layer_data, s)

            # Накапливаем для вершины work mesh
            ox, oy, oz = accum_offs[vi]
            accum_offs[vi] = (ox, oy, oz + (final_height - s.midlevel) * s.strength)
            for i in range(n_layers):
                accum_alpha[i][vi] += alphas[i]

    # Average loop contributions per vertex by valence on WORK mesh
    valence = [0]*vcount
    for p in eval_me.polygons:
        for li in range(p.loop_start, p.loop_start + p.loop_total):
            vi = eval_me.loops[li].vertex_index
            valence[vi] += 1

    for vi in range(vcount):
        d = max(1, valence[vi])
        ox, oy, oz = accum_offs[vi]
        accum_offs[vi] = (0.0, 0.0, oz / d)
        for i in range(n_layers):
            accum_alpha[i][vi] = accum_alpha[i][vi] / d

    # Transfer results back to ORIGINAL mesh attributes
    success = _transfer_result_to_original(obj.data, eval_me, accum_offs, accum_alpha, n_layers)
    
    if success:
        print(f"[MLD] NEW heightfill completed successfully on {vcount} vertices")
        blend_modes_used = [L.blend_mode for L in s.layers if L.enabled]
        print(f"[MLD] Blend modes used: {blend_modes_used}")
    
    return success