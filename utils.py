# utils.py — добавим функции для подсчета полигонов

import bpy

# Common helpers

def active_obj(context):
    """Return current active object or None."""
    return context.view_layer.objects.active if context and context.view_layer else None

def polycount(me: bpy.types.Mesh):
    """Return (verts, faces, tris)."""
    try:
        if not me.loop_triangles:
            me.calc_loop_triangles()
        return len(me.vertices), len(me.polygons), len(me.loop_triangles)
    except Exception:
        return 0, 0, 0

def get_evaluated_polycount(obj: bpy.types.Object, context=None, verbose=False):
    """Get polycount of evaluated mesh (with modifiers applied)."""
    try:
        if context is None:
            context = bpy.context
        
        # Force depsgraph update first
        context.view_layer.update()
        
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        eval_mesh = obj_eval.data
        
        # Force triangle calculation
        eval_mesh.calc_loop_triangles()
        
        verts = len(eval_mesh.vertices)
        faces = len(eval_mesh.polygons) 
        tris = len(eval_mesh.loop_triangles)
        
        if verbose:
            print(f"[MLD] Evaluated polycount: V:{verts} F:{faces} T:{tris}")
        return verts, faces, tris
        
    except Exception as e:
        if verbose:
            print(f"[MLD] get_evaluated_polycount failed: {e}")
        return 0, 0, 0

def get_polycount_up_to_modifier(obj: bpy.types.Object, modifier_name: str, context=None, verbose=False):
    """Get polycount with modifiers applied up to (but not including) specified modifier."""
    try:
        if context is None:
            context = bpy.context
        
        # Find target modifier
        target_mod = obj.modifiers.get(modifier_name)
        if not target_mod:
            return get_evaluated_polycount(obj, context, verbose)
        
        target_idx = obj.modifiers.find(modifier_name)
        
        # Store original states and disable modifiers after target
        modifier_states = []
        for i, mod in enumerate(obj.modifiers):
            modifier_states.append(mod.show_viewport)
            if i >= target_idx:
                mod.show_viewport = False
        
        # Force update after modifier changes
        context.view_layer.update()
        
        # Get polycount
        result = get_evaluated_polycount(obj, context, verbose)
        
        # Restore all modifier states
        for i, mod in enumerate(obj.modifiers):
            mod.show_viewport = modifier_states[i]
        
        # Force update after restoring states
        context.view_layer.update()
        
        if verbose:
            print(f"[MLD] Polycount up to {modifier_name}: V:{result[0]} F:{result[1]} T:{result[2]}")
        return result
        
    except Exception as e:
        if verbose:
            print(f"[MLD] get_polycount_up_to_modifier failed: {e}")
        return 0, 0, 0

def format_polycount(verts, faces, tris):
    """Format polycount for display."""
    return f"V:{verts:,} F:{faces:,} T:{tris:,}"

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