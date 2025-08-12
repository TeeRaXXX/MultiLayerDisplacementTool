# ops_masks.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import bpy
from bpy.types import Operator
from .utils import set_view_shading
from .attrs import ensure_color_attr, color_attr_exists, remove_color_attr

# --- Compatibility helpers (centralized) ------------------------------------

def _get_settings(obj):
    """Get MLD settings from object with fallback."""
    return getattr(obj, "mld_settings", None) if obj else None

def _get_active_layer_index(s):
    """Get active layer index with compatibility."""
    if not s:
        return 0
    return int(getattr(s, 'active_layer_index', getattr(s, 'active_index', 0)))

def _get_is_painting(s):
    """Get painting state with compatibility."""
    if not s:
        return False
    return bool(getattr(s, 'is_painting', getattr(s, 'painting', False)))

def _set_is_painting(s, value):
    """Set painting state with compatibility."""
    if not s:
        return
    if hasattr(s, 'is_painting'):
        s.is_painting = bool(value)
    elif hasattr(s, 'painting'):
        s.painting = bool(value)

def _get_active_layer(s):
    """Get currently active layer or None."""
    if not s or not s.layers:
        return None
    idx = _get_active_layer_index(s)
    if 0 <= idx < len(s.layers):
        return s.layers[idx]
    return None

def _get_active_mask_name(s):
    """Get mask name of active layer with fallback."""
    layer = _get_active_layer(s)
    if layer and getattr(layer, "mask_name", ""):
        return layer.mask_name
    # Fallback name
    idx = _get_active_layer_index(s)
    return f"MLD_Mask_{idx + 1}"

def _ensure_active_mask_name(s):
    """Ensure active layer has mask_name set."""
    layer = _get_active_layer(s)
    if not layer:
        return f"MLD_Mask_1"
    if not getattr(layer, "mask_name", ""):
        idx = _get_active_layer_index(s)
        layer.mask_name = f"MLD_Mask_{idx + 1}"
    return layer.mask_name

# --- Viewport management (optimized) ----------------------------------------

def _store_shading_mode(context):
    """Store current viewport shading mode."""
    try:
        # Кэшируем только один раз
        if "mld_prev_shading" not in context.scene:
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
        if "mld_prev_shading" in context.scene:
            del context.scene["mld_prev_shading"]
    except Exception:
        pass

def _refresh_viewport_minimal(context=None):
    """Minimal viewport refresh - only tag redraw, no forced updates."""
    ctx = context or bpy.context
    try:
        # Только tag_redraw, без других операций
        for area in ctx.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                break  # Только первый 3D viewport
    except Exception:
        pass

# --- Mask attribute management ---------------------------------------------

def _ensure_mask_attr_fast(obj, name):
    """Fast mask attribute creation/access without unnecessary updates."""
    if not obj or not name:
        return None
        
    # Сначала проверяем - может маска уже существует
    attr = None
    try:
        attr = obj.data.color_attributes.get(name)
    except Exception:
        try:
            attr = obj.data.vertex_colors.get(name)
        except Exception:
            pass
    
    # Если маска уже есть - просто возвращаем её, НЕ переинициализируем
    if attr:
        return attr
        
    # Создаем только если её нет
    attr = ensure_color_attr(obj.data, name)
    if not attr:
        return None
        
    # Инициализация ТОЛЬКО для новой маски
    try:
        for d in attr.data:
            d.color = (0.0, 0.0, 0.0, 1.0)
        # Один update после инициализации
        obj.data.update()
        print(f"[MLD] Created new mask: {name}")
    except Exception:
        pass
    
    return attr

def switch_to_active_mask_fast(obj, s):
    """Fast mask switching without viewport refresh."""
    if not obj or not s or not s.layers:
        return
    
    name = _get_active_mask_name(s)
    if not name:
        return
    
    # Быстрое переключение - только если в режиме рисования
    if not _get_is_painting(s):
        return
    
    # Проверяем существование маски
    attr = None
    try:
        attr = obj.data.color_attributes.get(name)
    except Exception:
        try:
            attr = obj.data.vertex_colors.get(name)
        except Exception:
            pass
    
    if not attr:
        # Создаем только если рисуем и маски нет
        attr = _ensure_mask_attr_fast(obj, name)
    
    if attr:
        try:
            # Быстрое переключение активного атрибута БЕЗ mesh.update()
            obj.data.color_attributes.active = attr
            obj.data.color_attributes.active_color = attr
            # НЕ вызываем _refresh_viewport здесь - слишком медленно
            print(f"[MLD] Fast switched to mask: {name}")
        except Exception:
            try:
                obj.data.vertex_colors.active = attr
            except Exception:
                pass

# --- Mask operations helpers -----------------------------------------------

def _get_mask_data(attr):
    """Get mask data with error handling."""
    try:
        return list(attr.data)
    except Exception:
        return []

def _apply_to_mask_red_channel_fast(attr, operation):
    """Fast mask operation without mesh.update() during operation."""
    if not attr:
        return False
    
    try:
        data = _get_mask_data(attr)
        if not data:
            return False
        
        # Batch operation without intermediate updates
        for d in data:
            color = list(d.color)
            new_red = operation(color[0])
            # Set proper viewport colors in one go
            d.color = (new_red, 0.0, 0.0, 1.0)
        
        return True
    except Exception as e:
        print(f"[MLD] Fast mask operation failed: {e}")
        return False

# --- Simple clipboard for masks -------------------------------------------

_MASK_CLIPBOARD = None

def _copy_mask_data(attr):
    """Copy mask red channel data to clipboard."""
    global _MASK_CLIPBOARD
    try:
        _MASK_CLIPBOARD = []
        for d in attr.data:
            _MASK_CLIPBOARD.append(float(d.color[0]))  # Red channel only
        return True
    except Exception:
        _MASK_CLIPBOARD = None
        return False

def _paste_mask_data(attr, operation='replace'):
    """Paste mask data from clipboard with operation and proper viewport colors."""
    global _MASK_CLIPBOARD
    if not _MASK_CLIPBOARD or not attr:
        return False
    
    try:
        data = _get_mask_data(attr)
        if len(data) != len(_MASK_CLIPBOARD):
            return False
        
        for i, d in enumerate(data):
            color = list(d.color)
            current = float(color[0])
            clipboard = float(_MASK_CLIPBOARD[i])
            
            if operation == 'replace':
                new_red = clipboard
            elif operation == 'add':
                new_red = max(0.0, min(1.0, current + clipboard))
            elif operation == 'subtract':
                new_red = max(0.0, min(1.0, current - clipboard))
            else:
                new_red = current
            
            # Set proper viewport colors: Red=mask, Green=0, Blue=0, Alpha=1
            color[0] = new_red  # Red = mask value
            color[1] = 0.0      # Green = 0
            color[2] = 0.0      # Blue = 0  
            color[3] = 1.0      # Alpha = 1
            d.color = tuple(color)
        
        return True
    except Exception:
        return False

# --- Operators --------------------------------------------------------------

class MLD_OT_create_mask(Operator):
    bl_idname = "mld.create_mask"
    bl_label = "Create/Activate Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        if not s or not s.layers:
            return False
        
        name = _get_active_mask_name(s)
        return not color_attr_exists(obj.data, name)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _ensure_active_mask_name(s)
        attr = _ensure_mask_attr_active(obj, name)
        
        if attr:
            self.report({'INFO'}, f"Created/activated mask: {name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to create mask attribute")
            return {'CANCELLED'}


class MLD_OT_toggle_paint(Operator):
    bl_idname = "mld.toggle_paint"
    bl_label = "Paint Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and s.layers  # Only enabled if we have layers

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        s = _get_settings(obj)
        if not s or not s.layers:
            self.report({'ERROR'}, "No layers available. Add a layer first.")
            return {'CANCELLED'}
        
        current_painting = _get_is_painting(s)
        
        if not current_painting:
            # Enter paint mode - optimized
            _store_shading_mode(context)
            set_view_shading(context, 'SOLID')
            
            # Быстрое создание/переключение маски
            name = _ensure_active_mask_name(s)
            attr = _ensure_mask_attr_fast(obj, name)
            
            if not attr:
                self.report({'ERROR'}, f"Failed to create mask attribute: {name}")
                return {'CANCELLED'}
            
            # Установка активного атрибута ДО входа в vertex paint
            try:
                obj.data.color_attributes.active = attr
                obj.data.color_attributes.active_color = attr
            except Exception:
                pass
            
            # Быстрый вход в Vertex Paint mode
            try:
                if obj.mode != 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
            except Exception as e:
                self.report({'WARNING'}, f"Could not enter vertex paint mode: {e}")
            
            _set_is_painting(s, True)
            self.report({'INFO'}, f"Started painting: {name}")
        else:
            # Exit paint mode - быстрый выход
            try:
                if obj.mode == 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
            except Exception:
                pass
                
            _restore_shading_mode(context)
            _set_is_painting(s, False)
            self.report({'INFO'}, "Stopped painting")
        
        return {'FINISHED'}


class MLD_OT_fill_mask(Operator):
    bl_idname = "mld.fill_mask"
    bl_label = "Fill Mask"
    bl_options = {'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[('ZERO', "Zero", "Fill 0%"), ('ONE', "One", "Fill 100%")],
        default='ZERO'
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and _get_is_painting(s)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        fill_value = 0.0 if self.mode == 'ZERO' else 1.0
        success = _apply_to_mask_red_channel_fast(attr, lambda x: fill_value)
        
        if success:
            # Только один update в конце
            obj.data.update()
            # Минимальный refresh
            _refresh_viewport_minimal(context)
            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class MLD_OT_copy_mask(Operator):
    bl_idname = "mld.copy_mask"
    bl_label = "Copy Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and _get_is_painting(s)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        if _copy_mask_data(attr):
            self.report({'INFO'}, "Mask copied to clipboard")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to copy mask")
            return {'CANCELLED'}


class MLD_OT_paste_mask(Operator):
    bl_idname = "mld.paste_mask"
    bl_label = "Paste Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _MASK_CLIPBOARD is not None

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        if _paste_mask_data(attr, 'replace'):
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Mask pasted from clipboard")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to paste mask")
            return {'CANCELLED'}


class MLD_OT_invert_mask(Operator):
    bl_idname = "mld.invert_mask"
    bl_label = "Invert Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and _get_is_painting(s)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        success = _apply_to_mask_red_channel(attr, lambda x: 1.0 - x)
        
        if success:
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Mask inverted")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class MLD_OT_add_mask_from_clip(Operator):
    bl_idname = "mld.add_mask_from_clip"
    bl_label = "Add From Clipboard"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _MASK_CLIPBOARD is not None

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        if _paste_mask_data(attr, 'add'):
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Added clipboard to mask")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class MLD_OT_sub_mask_from_clip(Operator):
    bl_idname = "mld.sub_mask_from_clip"
    bl_label = "Subtract From Clipboard"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _MASK_CLIPBOARD is not None

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        if _paste_mask_data(attr, 'subtract'):
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Subtracted clipboard from mask")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class MLD_OT_blur_mask(Operator):
    bl_idname = "mld.blur_mask"
    bl_label = "Blur Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and _get_is_painting(s)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        try:
            # Stronger vertex-based blur
            me = obj.data
            
            # Build vertex connectivity
            vert_neighbors = [set() for _ in range(len(me.vertices))]
            for edge in me.edges:
                v1, v2 = edge.vertices
                vert_neighbors[v1].add(v2)
                vert_neighbors[v2].add(v1)
            
            # Get current values per vertex
            vert_values = [0.0] * len(me.vertices)
            vert_counts = [0] * len(me.vertices)
            
            for loop_idx, loop in enumerate(me.loops):
                vi = loop.vertex_index
                try:
                    color = attr.data[loop_idx].color
                    vert_values[vi] += float(color[0])
                    vert_counts[vi] += 1
                except:
                    pass
            
            # Average per vertex
            for i in range(len(vert_values)):
                if vert_counts[i] > 0:
                    vert_values[i] /= vert_counts[i]
            
            # Apply strong blur (multiple iterations for stronger effect)
            new_values = vert_values[:]
            for iteration in range(3):  # Multiple blur iterations
                temp_values = new_values[:]
                for vi in range(len(me.vertices)):
                    if len(vert_neighbors[vi]) > 0:
                        neighbor_sum = sum(temp_values[ni] for ni in vert_neighbors[vi])
                        neighbor_avg = neighbor_sum / len(vert_neighbors[vi])
                        # Strong blur: 80% neighbor influence
                        new_values[vi] = temp_values[vi] * 0.2 + neighbor_avg * 0.8
            
            # Write back to loops with proper viewport colors
            for loop_idx, loop in enumerate(me.loops):
                vi = loop.vertex_index
                new_red = new_values[vi]
                # Red=mask, Green=0, Blue=0, Alpha=1 for proper viewport display
                attr.data[loop_idx].color = (new_red, 0.0, 0.0, 1.0)
            
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Mask blurred")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Blur failed: {e}")
            return {'CANCELLED'}


class MLD_OT_sharpen_mask(Operator):
    bl_idname = "mld.sharpen_mask"
    bl_label = "Sharpen Mask"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            return False
        s = _get_settings(obj)
        return s and _get_is_painting(s)

    def execute(self, context):
        obj = context.object
        s = _get_settings(obj)
        if not s:
            return {'CANCELLED'}
        
        name = _get_active_mask_name(s)
        attr = ensure_color_attr(obj.data, name)
        if not attr:
            return {'CANCELLED'}
        
        try:
            # Strong unsharp mask technique
            me = obj.data
            
            # Build vertex connectivity
            vert_neighbors = [set() for _ in range(len(me.vertices))]
            for edge in me.edges:
                v1, v2 = edge.vertices
                vert_neighbors[v1].add(v2)
                vert_neighbors[v2].add(v1)
            
            # Get current values
            vert_values = [0.0] * len(me.vertices)
            vert_counts = [0] * len(me.vertices)
            
            for loop_idx, loop in enumerate(me.loops):
                vi = loop.vertex_index
                try:
                    color = attr.data[loop_idx].color
                    vert_values[vi] += float(color[0])
                    vert_counts[vi] += 1
                except:
                    pass
            
            # Average per vertex
            for i in range(len(vert_values)):
                if vert_counts[i] > 0:
                    vert_values[i] /= vert_counts[i]
            
            # Create blurred version for unsharp mask
            blurred_values = vert_values[:]
            for vi in range(len(me.vertices)):
                if len(vert_neighbors[vi]) > 0:
                    neighbor_sum = sum(vert_values[ni] for ni in vert_neighbors[vi])
                    neighbor_avg = neighbor_sum / len(vert_neighbors[vi])
                    blurred_values[vi] = (vert_values[vi] + neighbor_avg) * 0.5
            
            # Strong sharpen: original + (original - blurred) * high_strength
            new_values = []
            for i in range(len(vert_values)):
                diff = vert_values[i] - blurred_values[i]
                sharpened = vert_values[i] + diff * 3.0  # Strong sharpen factor
                new_values.append(max(0.0, min(1.0, sharpened)))
            
            # Write back with proper viewport colors
            for loop_idx, loop in enumerate(me.loops):
                vi = loop.vertex_index
                new_red = new_values[vi]
                # Red=mask, Green=0, Blue=0, Alpha=1 for proper viewport display
                attr.data[loop_idx].color = (new_red, 0.0, 0.0, 1.0)
            
            obj.data.update()
            _refresh_viewport(context)
            self.report({'INFO'}, "Mask sharpened")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Sharpen failed: {e}")
            return {'CANCELLED'}


# Export functions for compatibility with settings.py
switch_to_active_mask = switch_to_active_mask_fast  # Alias for backward compatibility

def cleanup_mask_attributes(obj):
    """Remove all MLD mask attributes from object."""
    if not obj or obj.type != 'MESH':
        return []
    
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
    
    # Remove point attributes
    from .constants import ALPHA_PREFIX
    if hasattr(me, "attributes"):
        for attr in list(me.attributes):
            if (attr.name.startswith(ALPHA_PREFIX) or 
                attr.name == "MLD_Offs" or 
                attr.name.startswith("MLD_")):
                try:
                    me.attributes.remove(attr)
                    removed.append(attr.name)
                except Exception:
                    pass
    
    me.update()
    return removed


# --- Registration ------------------------------------------------------------

_CLASSES = (
    # Убрали MLD_OT_create_mask - теперь маска создается автоматически
    MLD_OT_toggle_paint,
    MLD_OT_fill_mask,
    MLD_OT_blur_mask,
    MLD_OT_sharpen_mask,
    MLD_OT_copy_mask,
    MLD_OT_paste_mask,
    MLD_OT_invert_mask,
    MLD_OT_add_mask_from_clip,
    MLD_OT_sub_mask_from_clip,
)

def register():
    print("[MLD] Registering mask operators...")
    for i, cls in enumerate(_CLASSES):
        try:
            bpy.utils.register_class(cls)
            print(f"[MLD] ✓ Registered {cls.bl_idname}")
        except Exception as e:
            print(f"[MLD] ✗ Failed to register {cls.bl_idname}: {e}")

def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass