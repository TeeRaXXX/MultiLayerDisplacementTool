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
    """Ensure color attribute exists for masks."""
    ca = getattr(me, "color_attributes", None)
    if not ca:
        return None
    attr = ca.get(name) if hasattr(ca, "get") else None
    if not attr:
        # FLOAT_COLOR for precision in masks
        try:
            attr = ca.new(name=name, type='FLOAT_COLOR', domain='CORNER')
        except Exception:
            # fallback domain
            try:
                attr = ca.new(name=name, type='FLOAT_COLOR', domain='POINT')
            except Exception:
                # last resort - byte color
                try:
                    attr = ca.new(name=name, type='BYTE_COLOR', domain='CORNER')
                except Exception:
                    attr = ca.new(name=name, type='BYTE_COLOR', domain='POINT')
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
    """Switch to the mask of currently active layer and ensure it's displayed."""
    if not obj or not s or len(s.layers) == 0:
        return
    
    name = _active_mask_name(s)
    if not name:
        return
    
    # If mask doesn't exist and we're painting, create it automatically
    if not _has_mask_attr(obj.data, name) and _get_paint(s):
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return
        # Initialize new mask with black (no mask)
        try:
            for d in _iter_colors(attr):
                d.color = (0.0, 0.0, 0.0, 1.0)
            obj.data.update()
        except Exception:
            pass
    elif not _has_mask_attr(obj.data, name):
        return
    
    # Get the mask attribute
    attr = None
    try:
        attr = obj.data.color_attributes.get(name)
    except Exception:
        try:
            attr = obj.data.vertex_colors.get(name) 
        except Exception:
            pass
    
    if not attr:
        return
    
    # Set as active attribute
    try:
        if hasattr(obj.data, "color_attributes"):
            obj.data.color_attributes.active = attr
        else:
            obj.data.vertex_colors.active = attr
    except Exception:
        pass
    
    # CRITICAL: Set the attribute for vertex paint display
    if _get_paint(s) and obj.mode == 'VERTEX_PAINT':
        try:
            # Force the vertex paint system to use this specific attribute
            obj.data.color_attributes.active_color = attr
            
            # Also try the render color (for display)
            try:
                obj.data.color_attributes.render_color_index = obj.data.color_attributes.find(name)
            except:
                pass
                
            # Update mesh and force viewport refresh
            obj.data.update()
            
            # Refresh all 3D viewports
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                    
            print(f"[MLD] Switched to mask: {name}")
                    
        except Exception as e:
            print(f"[MLD] Failed to switch viewport to mask {name}: {e}")

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
        
        # Ensure mask name is set
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
            
        # Initialize new mask with black color (0 = no mask)
        try:
            for d in _iter_colors(attr):
                # Set to black with full alpha (no mask initially)
                d.color = (0.0, 0.0, 0.0, 1.0)
            obj.data.update()
        except Exception:
            pass
            
        # Make it active and visible in vertex paint
        try:
            if hasattr(obj.data, "color_attributes"):
                obj.data.color_attributes.active = attr
                obj.data.color_attributes.active_color = attr
            else:
                obj.data.vertex_colors.active = attr
        except Exception:
            pass
            
        print(f"[MLD] Created/activated mask: {name}")
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
            name = _ensure_active_mask_name(s)
            attr = _ensure_color_attr(obj.data, name)
            if attr:
                # Initialize if empty
                try:
                    for d in _iter_colors(attr):
                        d.color = (0.0, 0.0, 0.0, 1.0)
                    obj.data.update()
                except Exception:
                    pass
                    
                # Set as active for viewport display
                try:
                    obj.data.color_attributes.active = attr
                    obj.data.color_attributes.active_color = attr
                except Exception:
                    try:
                        obj.data.vertex_colors.active = attr
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
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
            
        # Fill value: 0.0 for zero, 1.0 for 100%
        val = 0.0 if self.mode == 'ZERO' else 1.0
        
        try:
            for d in _iter_colors(attr):
                # Get current color
                c = list(getattr(d, "color", (0.0, 0.0, 0.0, 1.0)))
                # Set ONLY red channel (mask value), keep others
                c[0] = val  # Red channel = mask
                # Keep alpha = 1.0 for visibility
                c[3] = 1.0
                d.color = tuple(c)
        except Exception as e:
            print(f"[MLD] Fill mask failed: {e}")
            
        obj.data.update()
        
        # Force viewport refresh
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                
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
        if not (obj and s): 
            return {'CANCELLED'}
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr: 
            return {'CANCELLED'}
            
        try:
            # Copy ONLY the red channel values (mask data)
            _MASK_CLIPBOARD = []
            for d in _iter_colors(attr):
                color = getattr(d, "color", (0.0, 0.0, 0.0, 1.0))
                # Store only red channel value
                _MASK_CLIPBOARD.append(float(color[0]))
        except Exception as e:
            print(f"[MLD] Copy mask failed: {e}")
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
        if not (obj and s): 
            return {'CANCELLED'}
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr: 
            return {'CANCELLED'}
            
        data = list(_iter_colors(attr))
        if len(data) != len(_MASK_CLIPBOARD):
            return {'CANCELLED'}
            
        try:
            # Paste ONLY red channel values (mask data)
            for i, d in enumerate(data):
                c = list(getattr(d, "color", (0.0, 0.0, 0.0, 1.0)))
                # Set red channel from clipboard
                c[0] = float(_MASK_CLIPBOARD[i])
                # Keep alpha = 1.0
                c[3] = 1.0
                d.color = tuple(c)
        except Exception as e:
            print(f"[MLD] Paste mask failed: {e}")
            
        obj.data.update()
        
        # Force viewport refresh
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                
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
        if not (obj and s): 
            return {'CANCELLED'}
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr: 
            return {'CANCELLED'}
            
        try:
            # Invert ONLY red channel (mask data)
            for d in _iter_colors(attr):
                c = list(getattr(d, "color", (0.0, 0.0, 0.0, 1.0)))
                # Invert red channel
                c[0] = 1.0 - float(c[0])
                # Keep alpha = 1.0
                c[3] = 1.0
                d.color = tuple(c)
        except Exception as e:
            print(f"[MLD] Invert mask failed: {e}")
            
        obj.data.update()
        
        # Force viewport refresh
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                
        return {'FINISHED'}


class MLD_OT_add_mask_from_clip(Operator):
    bl_idname = "mld.add_mask_from_clip"
    bl_label  = "Add From Clipboard"
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
        if not (obj and s): 
            return {'CANCELLED'}
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr: 
            return {'CANCELLED'}
            
        data = list(_iter_colors(attr))
        if len(data) != len(_MASK_CLIPBOARD):
            return {'CANCELLED'}
            
        try:
            # Add operation: current + clipboard
            for i, d in enumerate(data):
                c = list(getattr(d, "color", (0.0, 0.0, 0.0, 1.0)))
                current_mask = float(c[0])
                clipboard_mask = float(_MASK_CLIPBOARD[i])
                new_mask = max(0.0, min(1.0, current_mask + clipboard_mask))
                c[0] = new_mask
                c[3] = 1.0
                d.color = tuple(c)
            obj.data.update()
            
            # Force viewport refresh
            for area in ctx.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                    
            return {'FINISHED'}
        except Exception as e:
            print(f"[MLD] Add mask failed: {e}")
            return {'CANCELLED'}


class MLD_OT_sub_mask_from_clip(Operator):
    bl_idname = "mld.sub_mask_from_clip"
    bl_label  = "Subtract From Clipboard"
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
        if not (obj and s): 
            return {'CANCELLED'}
            
        name = _ensure_active_mask_name(s)
        attr = _ensure_color_attr(obj.data, name)
        if not attr: 
            return {'CANCELLED'}
            
        data = list(_iter_colors(attr))
        if len(data) != len(_MASK_CLIPBOARD):
            return {'CANCELLED'}
            
        try:
            # Subtract operation: current - clipboard
            for i, d in enumerate(data):
                c = list(getattr(d, "color", (0.0, 0.0, 0.0, 1.0)))
                current_mask = float(c[0])
                clipboard_mask = float(_MASK_CLIPBOARD[i])
                new_mask = max(0.0, min(1.0, current_mask - clipboard_mask))
                c[0] = new_mask
                c[3] = 1.0
                d.color = tuple(c)
            obj.data.update()
            
            # Force viewport refresh
            for area in ctx.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                    
            return {'FINISHED'}
        except Exception as e:
            print(f"[MLD] Subtract mask failed: {e}")
            return {'CANCELLED'}


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
        bpy.utils.register_class(cls)

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

def cleanup_mask_attributes(obj):
    """Remove all MLD mask attributes from object."""
    if not obj or obj.type != 'MESH':
        return
    
    me = obj.data
    removed = []
    
    # Remove color attributes (masks)
    if hasattr(me, "color_attributes"):
        for attr in list(me.color_attributes):
            if attr.name.startswith("MLD_Mask_") or attr.name == "MLD_Pack":
                try:
                    me.color_attributes.remove(attr)
                    removed.append(attr.name)
                except Exception:
                    pass
    
    # Remove legacy vertex colors
    if hasattr(me, "vertex_colors"):
        for attr in list(me.vertex_colors):
            if attr.name.startswith("MLD_Mask_") or attr.name == "MLD_Pack":
                try:
                    me.vertex_colors.remove(attr)
                    removed.append(attr.name)
                except Exception:
                    pass
    
    # Remove point attributes (ALPHA, OFFS)
    if hasattr(me, "attributes"):
        for attr in list(me.attributes):
            if (attr.name.startswith("MLD_A_") or 
                attr.name == "MLD_Offs" or 
                attr.name.startswith("MLD_")):
                try:
                    me.attributes.remove(attr)
                    removed.append(attr.name)
                except Exception:
                    pass
    
    me.update()
    return removed