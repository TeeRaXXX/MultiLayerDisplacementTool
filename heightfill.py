# heightfill.py — compute per-vertex offsets (OFFS) and alphas using wrapped UV sampling
from __future__ import annotations
import bpy
from typing import List, Optional, Tuple
from .sampling import (
    make_sampler, find_image_and_uv_from_displacement,
    active_uv_layer_name, sample_height_at_loop,
)
from .attrs import ensure_float_attr, ensure_color_attr, point_red, loop_red, color_attr_exists
from .constants import OFFS_ATTR, ALPHA_PREFIX

def _ensure_output_attrs(me: bpy.types.Mesh, n_layers: int):
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

def solve_heightfill(obj: bpy.types.Object, s) -> bool:
    """
    Core: computes OFFS (vector) and ALPHA_i (float) per point, using height-fill mixing.
    Returns True on success.
    """
    me = obj.data
    if me is None or me.loop_triangles is None:
        me.calc_loop_triangles()

    # UV layer
    uv_name = active_uv_layer_name(me)
    if not uv_name:
        return False

    # samplers per layer
    samplers, uv_from = _gather_layer_samplers(obj, s)
    if not any(samplers):
        return False

    n_layers = len(s.layers)
    _ensure_output_attrs(me, n_layers)

    # Prepare write access
    offs_attr = me.attributes.get(OFFS_ATTR)
    alpha_attrs = [me.attributes.get(f"{ALPHA_PREFIX}{i}") for i in range(n_layers)]

    # Init accumulators
    vcount = len(me.vertices)
    accum_offs = [(0.0, 0.0, 0.0)] * vcount
    accum_alpha = [ [0.0]*vcount for _ in range(n_layers) ]

    # Pre-cache per-loop masks (red channel of the layer's mask) and heights
    # HeightFill rule: strict top layer when mask≈1; on fractional masks blend with below.
    for poly in me.polygons:
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            vi = me.loops[li].vertex_index

            # Collect per-layer masked heights for this loop
            h_layer = [0.0]*n_layers
            m_layer = [0.0]*n_layers
            for i, L in enumerate(s.layers):
                if not L.enabled:
                    continue
                # mask: corner (loop) color red if exists, else point fallback
                m = 0.0
                if L.mask_name and color_attr_exists(me, L.mask_name):
                    m = loop_red(me, L.mask_name, li)
                    if m is None:
                        # fallback to point
                        m = point_red(me, L.mask_name, vi) or 0.0
                else:
                    # if no mask created — treat as 0 (must Create/Activate → Fill 100% if needed)
                    m = 0.0
                m_layer[i] = m

                # height: sample with WRAP (handled inside sample_height_at_loop)
                smp = samplers[i]
                if smp is None:
                    continue
                h = sample_height_at_loop(me, uv_name, li, max(1e-8, L.tiling), smp)
                # per-layer remap with multiplier/bias
                h = h * L.multiplier + L.bias
                h_layer[i] = h

            # HeightFill blend:
            # go from bottom to top; where top mask==1 use it; where 0..1 fill by weighted max
            filled_h = 0.0
            alphas = [0.0]*n_layers
            remain = 1.0
            for i, L in enumerate(s.layers):
                m = m_layer[i]
                if m <= 0.0:  # nothing from this layer
                    continue
                if m >= 0.9999:
                    # take strictly this layer here
                    filled_h = h_layer[i]
                    alphas = [0.0]*n_layers
                    alphas[i] = 1.0
                    remain = 0.0
                    # since it's strict, higher layers (i+1..end) override later iterations
                else:
                    # partial: mix by mask*magnitude (fill power is global)
                    # We consider "how much this layer protrudes over current" and add a share.
                    contrib = max(0.0, h_layer[i] - filled_h)
                    gain = contrib * m * s.fill_power
                    if gain > 0.0:
                        filled_h = filled_h + gain
                        alphas[i] += min(remain, m)  # accumulate visible share
                        remain = max(0.0, 1.0 - sum(alphas))

            # write per-vertex accumulations (average per-loops to vertex)
            # accumulate to vertex (we'll average later)
            ox, oy, oz = accum_offs[vi]
            # displacement is along normal; gn will apply vector, we store scalar in Z here
            accum_offs[vi] = (ox, oy, oz + (filled_h - s.midlevel) * s.strength)
            for i in range(n_layers):
                accum_alpha[i][vi] += alphas[i]

    # Average loop contributions per vertex by valence
    valence = [0]*vcount
    for p in me.polygons:
        for li in range(p.loop_start, p.loop_start + p.loop_total):
            vi = me.loops[li].vertex_index
            valence[vi] += 1

    for vi in range(vcount):
        d = max(1, valence[vi])
        ox, oy, oz = accum_offs[vi]
        offs_attr.data[vi].vector = (0.0, 0.0, oz / d)
        for i in range(n_layers):
            alpha_attrs[i].data[vi].value = accum_alpha[i][vi] / d

    me.update()
    return True
