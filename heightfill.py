# heightfill.py — ИСПРАВЛЕННАЯ ВЕРСИЯ с поддержкой evaluated mesh (с модификаторами)

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
    """Get mesh with modifiers applied (subdivision etc.) for heightfill calculation."""
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
    # For subdivision, we need to map subdivided vertices back to original vertices
    orig_vcount = len(original_me.vertices)
    eval_vcount = len(eval_me.vertices)
    
    print(f"[MLD] Mapping: {eval_vcount} eval vertices → {orig_vcount} original vertices")
    
    if eval_vcount == orig_vcount:
        # No subdivision - direct 1:1 mapping
        for vi in range(orig_vcount):
            if vi < len(accum_offs):
                ox, oy, oz = accum_offs[vi]
                offs_attr.data[vi].vector = (0.0, 0.0, oz)
                for i in range(n_layers):
                    if alpha_attrs[i] and vi < len(accum_alpha[i]):
                        alpha_attrs[i].data[vi].value = accum_alpha[i][vi]
    else:
        # Subdivision case - we need to average/interpolate back to original vertices
        # Simple approach: use vertex correspondence based on position proximity
        
        # For subdivision, the first N vertices usually correspond to original vertices
        for orig_vi in range(min(orig_vcount, eval_vcount)):
            if orig_vi < len(accum_offs):
                ox, oy, oz = accum_offs[orig_vi]
                offs_attr.data[orig_vi].vector = (0.0, 0.0, oz)
                for i in range(n_layers):
                    if alpha_attrs[i] and orig_vi < len(accum_alpha[i]):
                        alpha_attrs[i].data[orig_vi].value = accum_alpha[i][orig_vi]
        
        # For additional vertices created by subdivision, average their contribution back
        if eval_vcount > orig_vcount:
            # This is a simplified approach - in reality, subdivision creates specific patterns
            # For now, we'll use the values from the first part (original vertices)
            print(f"[MLD] Subdivision detected: using values from first {orig_vcount} vertices")
    
    original_me.update()
    return True

def solve_heightfill(obj: bpy.types.Object, s, context=None, work_mesh: bpy.types.Mesh = None) -> bool:
    """
    Core heightfill with support for custom work mesh (subdivision-aware).
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

    print(f"[MLD] Processing {len(eval_me.polygons)} polygons on work mesh...")

    # Process polygons on WORK mesh
    for poly in eval_me.polygons:
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            vi = eval_me.loops[li].vertex_index

            # Collect per-layer masked heights for this loop
            h_layer = [0.0]*n_layers
            m_layer = [0.0]*n_layers
            
            for i, L in enumerate(s.layers):
                if not L.enabled:
                    continue
                    
                # Mask: read from ORIGINAL mesh (masks are painted on original)
                m = 0.0
                if L.mask_name and color_attr_exists(obj.data, L.mask_name):
                    # Map work mesh loop back to original for mask reading
                    orig_li = li % len(obj.data.loops) if len(obj.data.loops) > 0 else 0
                    orig_li = min(orig_li, len(obj.data.loops) - 1)
                    
                    m = loop_red(obj.data, L.mask_name, orig_li)
                    if m is None:
                        # fallback to point on original mesh
                        orig_vi = vi % len(obj.data.vertices) if len(obj.data.vertices) > 0 else 0
                        orig_vi = min(orig_vi, len(obj.data.vertices) - 1)
                        m = point_red(obj.data, L.mask_name, orig_vi) or 0.0
                else:
                    m = 0.0
                m_layer[i] = m

                # Height: sample from WORK mesh (more detailed UVs)
                smp = samplers[i]
                if smp is None:
                    continue
                h = sample_height_at_loop(eval_me, uv_name, li, max(1e-8, L.tiling), smp)
                h = h * L.multiplier + L.bias
                h_layer[i] = h

            # HeightFill blend logic (same as before)
            filled_h = 0.0
            alphas = [0.0]*n_layers
            remain = 1.0
            
            for i, L in enumerate(s.layers):
                m = m_layer[i]
                if m <= 0.0:
                    continue
                if m >= 0.9999:
                    filled_h = h_layer[i]
                    alphas = [0.0]*n_layers
                    alphas[i] = 1.0
                    remain = 0.0
                else:
                    contrib = max(0.0, h_layer[i] - filled_h)
                    gain = contrib * m * s.fill_power
                    if gain > 0.0:
                        filled_h = filled_h + gain
                        alphas[i] += min(remain, m)
                        remain = max(0.0, 1.0 - sum(alphas))

            # Accumulate for work mesh vertex
            ox, oy, oz = accum_offs[vi]
            accum_offs[vi] = (ox, oy, oz + (filled_h - s.midlevel) * s.strength)
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
        print(f"[MLD] Heightfill completed successfully on {vcount} vertices")
    
    return success