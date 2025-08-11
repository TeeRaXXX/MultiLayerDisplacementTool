# Self-contained UV/image helpers + bilinear CPU sampler
from __future__ import annotations
import bpy
from typing import Optional, Tuple

def active_uv_layer_name(me: bpy.types.Mesh) -> Optional[str]:
    uvs = getattr(me, "uv_layers", None)
    if not uvs or len(uvs) == 0:
        return None
    return (uvs.active and uvs.active.name) or uvs[0].name

def _walk_to_principled_basecolor(nt: bpy.types.NodeTree):
    hits = []
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            sock = n.inputs.get("Base Color")
            if not sock:
                continue
            for l in sock.links:
                src = l.from_node
                if src.bl_idname == "ShaderNodeTexImage":
                    hits.append((src, src.inputs.get("Vector")))
                elif src.bl_idname in {
                    "ShaderNodeMixRGB","ShaderNodeRGBCurve","ShaderNodeHueSaturation",
                    "ShaderNodeInvert","ShaderNodeGamma"
                }:
                    for i_in in src.inputs:
                        for l2 in i_in.links:
                            if l2.from_node.bl_idname == "ShaderNodeTexImage":
                                hits.append((l2.from_node, l2.from_node.inputs.get("Vector")))
    return hits

def find_basecolor_image_and_uv(mat: bpy.types.Material) -> Tuple[Optional[bpy.types.Image], Optional[str]]:
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None, None
    nt = mat.node_tree
    for img_node, _ in _walk_to_principled_basecolor(nt):
        if img_node.image:
            return img_node.image, None
    prefs = ("basecolor","base_color","albedo","diffuse","color")
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            if any(k in (n.image.name or "").lower() for k in prefs):
                return n.image, None
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            return n.image, None
    return None, None

def find_image_and_uv_from_displacement(mat: bpy.types.Material):
    if not mat or not mat.use_nodes:
        return None, None
    nt = mat.node_tree
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeOutputMaterial":
            inp = n.inputs.get("Displacement")
            if not inp:
                continue
            for l in inp.links:
                src = l.from_node
                if src.bl_idname == "ShaderNodeTexImage" and src.image:
                    return src.image, None
                if src.bl_idname in {"ShaderNodeBump","ShaderNodeDisplacement"}:
                    for s_in in src.inputs:
                        for l2 in s_in.links:
                            n2 = l2.from_node
                            if n2.bl_idname == "ShaderNodeTexImage" and n2.image:
                                return n2.image, None
    return find_basecolor_image_and_uv(mat)

def make_sampler(img: Optional[bpy.types.Image]):
    if not img:
        return None
    try:
        w, h = int(img.size[0]), int(img.size[1])
    except Exception:
        w = int(getattr(img, "width", 0)); h = int(getattr(img, "height", 0))
    if w <= 0 or h <= 0:
        return None
    ch = int(getattr(img, "channels", 4))
    px = list(img.pixels[:])
    return {"w": w, "h": h, "ch": ch, "px": px}

def _pix(px, w, h, ch, x, y):
    x %= w; y %= h
    idx = (y * w + x) * ch
    r = px[idx] if idx < len(px) else 0.0
    if ch >= 3:
        g = px[idx+1] if idx+1 < len(px) else r
        b = px[idx+2] if idx+2 < len(px) else r
        return 0.2126*r + 0.7152*g + 0.0722*b
    return r

def _sample_bilinear(sampler, u: float, v: float) -> float:
    w = sampler["w"]; h = sampler["h"]; ch = sampler["ch"]; px = sampler["px"]
    u = u - int(u); v = v - int(v)
    if u < 0: u += 1.0
    if v < 0: v += 1.0
    x = u * (w - 1); y = v * (h - 1)
    x0 = int(x); y0 = int(y)
    x1 = (x0 + 1) % w; y1 = (y0 + 1) % h
    tx = x - x0; ty = y - y0
    c00 = _pix(px, w, h, ch, x0, y0)
    c10 = _pix(px, w, h, ch, x1, y0)
    c01 = _pix(px, w, h, ch, x0, y1)
    c11 = _pix(px, w, h, ch, x1, y1)
    c0 = c00*(1-tx) + c10*tx
    c1 = c01*(1-tx) + c11*tx
    val = c0*(1-ty) + c1*ty
    return max(0.0, min(1.0, float(val)))

def sample_height_at_loop(me: bpy.types.Mesh, uv_name: str, loop_index: int, tiling: float, sampler) -> float:
    if not sampler or not uv_name:
        return 0.0
    uv_layer = me.uv_layers.get(uv_name)
    if not uv_layer:
        return 0.0
    try:
        uv = uv_layer.data[loop_index].uv
    except Exception:
        return 0.0
    u = float(uv.x) * float(tiling)
    v = float(uv.y) * float(tiling)
    return _sample_bilinear(sampler, u, v)
