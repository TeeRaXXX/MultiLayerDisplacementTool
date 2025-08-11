import bpy

# Common helpers

def active_obj(context):
    """Return current active object or None."""
    return context.view_layer.objects.active if context and context.view_layer else None

def polycount(me: bpy.types.Mesh):
    """Return (verts, faces, approx_tris)."""
    try:
        tris = sum(max(0, len(p.vertices) - 2) for p in me.polygons)
        return len(me.vertices), len(me.polygons), tris
    except Exception:
        return 0, 0, 0

def set_view_shading(context, shading_type='SOLID'):
    """Switch viewport shading (best-effort, safe)."""
    try:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                if hasattr(sp, "shading"):
                    sp.shading.type = shading_type
                    return True
    except Exception:
        pass
    return False

def get_current_shading(context):
    """Get current viewport shading type."""
    try:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                if hasattr(sp, "shading"):
                    return sp.shading.type
    except Exception:
        pass
    return 'SOLID'  # fallback

def ensure_visible(obj):
    """Make object visible in viewport (best-effort)."""
    try:
        obj.hide_set(False)
        obj.hide_viewport = False
    except Exception:
        pass

def safe_mode(obj, mode: str):
    """Switch mode safely, return previous mode."""
    prev = getattr(obj, "mode", "OBJECT")
    if prev != mode:
        try:
            bpy.ops.object.mode_set(mode=mode)
        except Exception:
            pass
    return prev

def register():  # keeping API symmetry
    pass

def unregister():
    pass