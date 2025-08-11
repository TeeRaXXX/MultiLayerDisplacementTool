import bpy
from bpy.types import Operator
from .utils import set_view_shading

# --- Compatibility shims ------------------------------------------------------

def _ai(s):
    """Active layer index with fallbacks."""
    return int(getattr(s, 'active_layer_index', getattr(s, 'active_index', 0)))

def _get_paint(s):
    return bool(getattr(s, 'is_painting', getattr(s, 'painting', False)))

def _set_paint(s, v: bool):
    if hasattr(s, 'is_painting'):
        setattr(s, 'is_painting', bool(v))
    else:
        setattr(s, 'painting', bool(v))

def _active_mask_name(s):
    """Mask name of active layer, or sensible default."""
    try:
        L = s.layers[_ai(s)]
    except Exception:
        return "MLD_Mask_1"
    name = getattr(L, "mask_name", "") or f"MLD_Mask_{_ai(s)+1}"
    return name

def _ensure_active_mask_name(s):
    """Ensure active layer has mask_name set (use in execute(), not poll())."""
    try:
        L = s.layers[_ai(s)]
        if not getattr(L, "mask_name", ""):
            L.mask_name = f"MLD_Mask_{_ai(s)+1}"
        return L.mask_name
    except Exception:
        return "MLD_Mask_1"

def _ensure_color_attr(me: bpy.types.Mesh, name: str):
    ca = getattr(me, "color_attributes", None)
    if not ca:
        return None
    attr = ca.get(name) if hasattr(ca, "get") else None
    if not attr:
        # FLOAT_COLOR/ByteColor both fine for masks; use FLOAT_COLOR for precision.
        try:
            attr = ca.new(name=name, type='FLOAT_COLOR', domain='CORNER')
        except Exception:
            # fallback domain
            attr = ca.new(name=name, type='FLOAT_COLOR', domain='POINT')
    return attr

def _iter_colors(attr):
    try:
        return attr.data
    except Exception:
        class _Empty: 
            def __iter__(self): return iter(())
        return _Empty()

def _has_mask_attr(me: bpy.types.Mesh, name: str) -> bool:
    """Check if mask attribute exists."""
    if not name:
        return False
    ca = getattr(me, "color_attributes", None)
    if ca and ca.get(name):
        return True
    vc = getattr(me, "vertex_colors", None)
    if vc and name in vc:
        return True
    return False

def _store_shading_mode(context):
    """Store current viewport shading mode in scene properties."""
    try:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                if hasattr(sp, "shading"):
                    context.scene["mld_prev_shading"] = sp.shading.type
                    return
    except Exception:
        pass

def _restore_shading_mode(context):
    """Restore previous viewport shading mode."""
    try:
        prev_mode = context.scene.get("mld_prev_shading", "SOLID")
        set_view_shading(context, prev_mode)
        # Clean up stored value
        if "mld_prev_shading" in context.scene:
            del context.scene["mld_prev_shading"]
    except Exception:
        pass

def _switch_to_active_mask(obj, s):
    """Switch to the mask of currently active layer."""
    if not obj or not s or len(s.layers) == 0:
        return
    
    name = _active_mask_name(s)  # Use read-only version
    if not name:
        return
    
    # If mask doesn't exist and we're painting, create it automatically
    if not _has_mask_attr(obj.data, name) and _get_paint(s):
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return
    elif not _has_mask_attr(obj.data, name):
        return
    
    try:
        attr = obj.data.color_attributes.get(name)
        if attr:
            obj.data.color_attributes.active = attr
            return
    except Exception:
        pass
    
    try:
        attr = obj.data.vertex_colors.get(name)
        if attr:
            obj.data.vertex_colors.active = attr
    except Exception:
        pass

# --- Operators ----------------------------------------------------------------

class MLD_OT_create_mask(Operator):
    bl_idname = "mld.create_mask"
    bl_label  = "Create/Activate Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH': 
            return False
        s = getattr(obj, "mld_settings", None)
        if not s or len(getattr(s, "layers", [])) == 0:
            return False
        
        # Only active if current layer doesn't have mask attribute
        # Don't modify anything in poll() - just read
        name = _active_mask_name(s)
        if not name:  # fallback if no name could be determined
            return True
        return not _has_mask_attr(obj.data, name)

    def execute(self, ctx):
        obj = ctx.object
        if not obj or obj.type != 'MESH': 
            return {'CANCELLED'}
        s = getattr(obj, "mld_settings", None)
        if not s or len(getattr(s, "layers", [])) == 0:
            return {'CANCELLED'}
        
        # Ensure mask name is set (safe to modify in execute())
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        # Make it active in mesh
        try:
            obj.data.color_attributes.active = attr
        except Exception:
            try:
                obj.data.vertex_colors.active = attr  # very old fallback
            except Exception:
                pass
        return {'FINISHED'}


class MLD_OT_toggle_paint(Operator):
    bl_idname = "mld.toggle_paint"
    bl_label  = "Paint Mask"
    bl_options = {'UNDO'}

    def execute(self, ctx):
        obj = ctx.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        s = getattr(obj, "mld_settings", None)
        if not s:
            return {'CANCELLED'}
        
        current_painting = _get_paint(s)
        
        if not current_painting:
            # Entering paint mode
            _store_shading_mode(ctx)
            set_view_shading(ctx, 'SOLID')
            
            # Ensure mask attribute exists/active
            name = _ensure_active_mask_name(s)  # Use safe version
            attr = _ensure_color_attr(obj.data, name)
            if attr:
                try:
                    obj.data.color_attributes.active = attr
                except Exception:
                    pass
            
            # Switch to Vertex Paint mode
            try:
                if obj.mode != 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
            except Exception:
                pass
        else:
            # Exiting paint mode
            _restore_shading_mode(ctx)
            
            # Exit Vertex Paint mode
            try:
                if obj.mode == 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
            except Exception:
                pass
        
        # Toggle painting flag
        _set_paint(s, not current_painting)
        return {'FINISHED'}


class MLD_OT_fill_mask(Operator):
    bl_idname = "mld.fill_mask"
    bl_label  = "Fill Mask"
    bl_options = {'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[('ZERO',"Zero","Fill 0%"), ('ONE',"One","Fill 100%")],
        default='ZERO'
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, "mld_settings", None)
        return s and _get_paint(s)

    def execute(self, ctx):
        obj = ctx.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        s = getattr(obj, "mld_settings", None)
        if not s:
            return {'CANCELLED'}
        name = _ensure_active_mask_name(s)  # Use safe version
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        val = 0.0 if self.mode == 'ZERO' else 1.0
        try:
            for d in _iter_colors(attr):
                # store mask in Red, keep alpha = 1
                c = list(getattr(d, "color", (0.0,0.0,0.0,1.0)))
                c[0] = val
                c[3] = 1.0
                d.color = c
        except Exception:
            pass
        return {'FINISHED'}


# Simple clipboard for masks within session
_MASK_CLIPBOARD = None

class MLD_OT_copy_mask(Operator):
    bl_idname = "mld.copy_mask"
    bl_label  = "Copy Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, "mld_settings", None)
        return s and _get_paint(s)

    def execute(self, ctx):
        global _MASK_CLIPBOARD
        obj = ctx.object
        s = getattr(obj, "mld_settings", None) if obj else None
        if not (obj and s): return {'CANCELLED'}
        name = _ensure_active_mask_name(s)  # Use safe version
        attr = _ensure_color_attr(obj.data, name)
        if not attr: return {'CANCELLED'}
        try:
            _MASK_CLIPBOARD = [tuple(d.color) for d in _iter_colors(attr)]
        except Exception:
            _MASK_CLIPBOARD = None
        return {'FINISHED'}


class MLD_OT_paste_mask(Operator):
    bl_idname = "mld.paste_mask"
    bl_label  = "Paste Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        global _MASK_CLIPBOARD
        if not _MASK_CLIPBOARD:
            return False
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, "mld_settings", None)
        return s and _get_paint(s)

    def execute(self, ctx):
        global _MASK_CLIPBOARD
        if not _MASK_CLIPBOARD:
            return {'CANCELLED'}
        obj = ctx.object
        s = getattr(obj, "mld_settings", None) if obj else None
        if not (obj and s): return {'CANCELLED'}
        name = _ensure_active_mask_name(s)  # Use safe version
        attr = _ensure_color_attr(obj.data, name)
        if not attr: return {'CANCELLED'}
        data = list(_iter_colors(attr))
        if len(data) != len(_MASK_CLIPBOARD):
            return {'CANCELLED'}
        try:
            for i, d in enumerate(data):
                d.color = _MASK_CLIPBOARD[i]
        except Exception:
            pass
        return {'FINISHED'}


class MLD_OT_invert_mask(Operator):
    bl_idname = "mld.invert_mask"
    bl_label  = "Invert Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, "mld_settings", None)
        return s and _get_paint(s)

    def execute(self, ctx):
        obj = ctx.object
        s = getattr(obj, "mld_settings", None) if obj else None
        if not (obj and s): return {'CANCELLED'}
        name = _ensure_active_mask_name(s)  # Use safe version
        attr = _ensure_color_attr(obj.data, name)
        if not attr: return {'CANCELLED'}
        try:
            for d in _iter_colors(attr):
                c = list(getattr(d, "color", (0,0,0,1)))
                c[0] = 1.0 - float(c[0])
                d.color = c
        except Exception:
            pass
        return {'FINISHED'}


class _MaskBlendBase(Operator):
    """Base for add/sub with clipboard; op='ADD'|'SUB'"""
    op: bpy.props.StringProperty(default="ADD")

    @classmethod
    def poll(cls, context):
        global _MASK_CLIPBOARD
        if not _MASK_CLIPBOARD:
            return False
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, "mld_settings", None)
        return s and _get_paint(s)

    def mix(self, a, b):
        ra = float(a[0]); rb = float(b[0])
        if self.op == "ADD":
            r = max(0.0, min(1.0, ra + rb))
        else:
            r = max(0.0, min(1.0, ra - rb))
        return (r, 0.0, 0.0, 1.0)

    def apply(self, ctx):
        global _MASK_CLIPBOARD
        if not _MASK_CLIPBOARD: 
            return False
        obj = ctx.object
        s = getattr(obj, "mld_settings", None) if obj else None
        if not (obj and s): return False
        name = _ensure_active_mask_name(s)  # Use safe version
        attr = _ensure_color_attr(obj.data, name)
        if not attr: return False
        data = list(_iter_colors(attr))
        if len(data) != len(_MASK_CLIPBOARD):
            return False
        try:
            for i, d in enumerate(data):
                d.color = self.mix(getattr(d, "color", (0,0,0,1)), _MASK_CLIPBOARD[i])
            return True
        except Exception:
            return False

class MLD_OT_add_mask_from_clip(_MaskBlendBase):
    bl_idname = "mld.add_mask_from_clip"
    bl_label  = "Add From Clipboard"
    bl_options = {'UNDO'}
    def __init__(self): self.op = "ADD"
    def execute(self, ctx):
        return {'FINISHED'} if self.apply(ctx) else {'CANCELLED'}

class MLD_OT_sub_mask_from_clip(_MaskBlendBase):
    bl_idname = "mld.sub_mask_from_clip"
    bl_label  = "Subtract From Clipboard"
    bl_options = {'UNDO'}
    def __init__(self): self.op = "SUB"
    def execute(self, ctx):
        return {'FINISHED'} if self.apply(ctx) else {'CANCELLED'}


_CLASSES = (
    MLD_OT_create_mask,
    MLD_OT_toggle_paint,
    MLD_OT_fill_mask,
    MLD_OT_copy_mask,
    MLD_OT_paste_mask,
    MLD_OT_invert_mask,
    MLD_OT_add_mask_from_clip,
    MLD_OT_sub_mask_from_clip,
)

def register():
    for cls in _CLASSES:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            bpy.utils.unregister_class(cls); bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

# Export function for other modules to use
def switch_to_active_mask(obj, s):
    """Public function to switch mask when layer changes."""
    _switch_to_active_mask(obj, s)