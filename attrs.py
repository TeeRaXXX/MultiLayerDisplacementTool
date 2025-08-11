# attrs.py — helpers for mesh attributes & color attributes (Blender 4.x safe)
from __future__ import annotations
import bpy
from typing import Optional

# ---------------------------
# Generic mesh attributes (FLOAT / FLOAT_VECTOR etc.)
# ---------------------------

def ensure_float_attr(me: bpy.types.Mesh, name: str,
                      domain: str = 'POINT',
                      data_type: str = 'FLOAT') -> bpy.types.Attribute:
    """
    Ensure a generic mesh attribute exists (me.attributes).
    data_type: 'FLOAT' | 'FLOAT_VECTOR' | 'INT' | ...
    domain   : 'POINT' | 'EDGE' | 'FACE' | 'CORNER'
    """
    attr = me.attributes.get(name) if hasattr(me, "attributes") else None
    if attr and attr.data_type == data_type and attr.domain == domain:
        return attr
    # recreate with the proper signature
    if attr:
        try:
            me.attributes.remove(attr)
        except Exception:
            pass
    return me.attributes.new(name=name, type=data_type, domain=domain)

def remove_attribute_safely(me: bpy.types.Mesh, name: str):
    """Remove attribute by name from attributes or color_attributes/vertex_colors."""
    # generic
    try:
        attr = me.attributes.get(name)
        if attr:
            me.attributes.remove(attr)
            return
    except Exception:
        pass
    # color attributes
    try:
        ca = getattr(me, "color_attributes", None)
        if ca:
            a = ca.get(name)
            if a:
                ca.remove(a);  return
    except Exception:
        pass
    # legacy vertex colors
    try:
        vc = getattr(me, "vertex_colors", None)
        if vc and name in vc:
            vc.remove(vc[name])
    except Exception:
        pass

# ---------------------------
# Color attributes (masks etc.)
# ---------------------------

def ensure_color_attr(me: bpy.types.Mesh, name: str,
                      domain: str = 'CORNER',
                      color_type: str = 'BYTE_COLOR') -> bpy.types.ColorAttribute:
    """
    Ensure a color attribute (mask) exists.
    color_type: 'BYTE_COLOR' | 'FLOAT_COLOR'
    domain    : 'CORNER' (loops) or 'POINT'
    """
    ca = getattr(me, "color_attributes", None)
    if ca:
        attr = ca.get(name)
        if attr and attr.domain == domain and attr.data_type == color_type:
            return attr
        if attr:
            try:
                ca.remove(attr)
            except Exception:
                pass
        return ca.new(name=name, domain=domain, type=color_type)

    # Fallback to legacy vertex_colors API (corner domain only)
    vc = getattr(me, "vertex_colors", None)
    if vc is not None:
        if name in vc:
            return vc[name]
        try:
            return vc.new(name=name)
        except Exception:
            pass
    raise RuntimeError("No color attribute storage found on mesh")

def color_attr_exists(me: bpy.types.Mesh, name: str) -> bool:
    try:
        ca = getattr(me, "color_attributes", None)
        if ca and ca.get(name):
            return True
    except Exception:
        pass
    try:
        vc = getattr(me, "vertex_colors", None)
        if vc and (name in vc):
            return True
    except Exception:
        pass
    return False

# ---------------------------
# Read helpers for masks (red channel)
# ---------------------------

def _get_color_attr(me: bpy.types.Mesh, name: str):
    ca = getattr(me, "color_attributes", None)
    if ca:
        a = ca.get(name)
        if a:
            return a
    vc = getattr(me, "vertex_colors", None)
    if vc and (name in vc):
        return vc[name]
    return None

def loop_red(me: bpy.types.Mesh, name: str, loop_index: int) -> Optional[float]:
    """
    Read red channel (0..1) from CORNER domain color attribute.
    Returns None if attribute is not CORNER or index invalid.
    """
    a = _get_color_attr(me, name)
    if not a:
        return None
    try:
        # color_attributes / vertex_colors both expose .data[li].color
        return float(a.data[loop_index].color[0])
    except Exception:
        return None

def point_red(me: bpy.types.Mesh, name: str, vert_index: int) -> Optional[float]:
    """
    Read red channel from POINT domain color attribute.
    Returns None if not POINT or index invalid.
    """
    a = _get_color_attr(me, name)
    if not a:
        return None
    # new API: ColorAttribute has .domain
    dom = getattr(a, "domain", 'CORNER')
    try:
        if dom == 'POINT':
            return float(a.data[vert_index].color[0])
    except Exception:
        pass
    return None


# --- Added helpers for mask/color attributes ---
def remove_color_attr(me: bpy.types.Mesh, name: str) -> bool:
    ca = getattr(me, "color_attributes", None)
    if not ca: return False
    try:
        attr = ca.get(name) if hasattr(ca, "get") else None
        if not attr:
            for a in ca:
                if getattr(a, "name", None) == name:
                    attr = a; break
        if attr: ca.remove(attr); return True
    except Exception: pass
    return False

def fill_attr_color(me: bpy.types.Mesh, name: str, col=(0.0,0.0,0.0,1.0)) -> bool:
    a = _get_color_attr(me, name)
    if not a: return False
    try:
        for d in a.data: d.color = col
        return True
    except Exception: return False

def read_mask_rgba_list(me: bpy.types.Mesh, name: str):
    a = _get_color_attr(me, name)
    if not a: return []
    try: return [tuple(d.color) for d in a.data]
    except Exception: return []

def write_mask_rgba_list(me: bpy.types.Mesh, name: str, values) -> bool:
    a = _get_color_attr(me, name)
    if not a: return False
    try:
        if len(values) != len(a.data): return False
        for i, d in enumerate(a.data): d.color = values[i]
        return True
    except Exception: return False
