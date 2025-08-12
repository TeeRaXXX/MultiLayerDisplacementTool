# ... (предыдущий код до MLD_OT_sharpen_mask остается без изменений) ...

class MLD_OT_sharpen_mask(Operator):
    bl_idname = "mld.sharpen_mask"
    bl_label  = "Sharpen Mask" 
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
            # Sharpen using unsharp mask technique
            me = obj.data
            
            # Build vertex connectivity
            vert_neighbors = [set() for _ in range(len(me.vertices))]
            for edge in me.edges:
                v1, v2 = edge.vertices
                vert_neighbors[v1].add(v2)
                vert_neighbors[v2].add(v1)
            
            # Get current mask values per vertex
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
            
            # Create blurred version
            blurred_values = vert_values[:]
            for vi in range(len(me.vertices)):
                if len(vert_neighbors[vi]) > 0:
                    neighbor_sum = sum(vert_values[ni] for ni in vert_neighbors[vi])
                    neighbor_avg = neighbor_sum / len(vert_neighbors[vi])
                    blurred_values[vi] = (vert_values[vi] + neighbor_avg) * 0.5
            
            # Sharpen: original + (original - blurred) * strength
            new_values = []
            for i in range(len(vert_values)):
                diff = vert_values[i] - blurred_values[i]
                sharpened = vert_values[i] + diff * 20.0  # Increased sharpen strength
                new_values.append(max(0.0, min(1.0, sharpened)))
            
            # Write back to loops
            for loop_idx, loop in enumerate(me.loops):
                vi = loop.vertex_index
                c = list(getattr(attr.data[loop_idx], "color", (0.0, 0.0, 0.0, 1.0)))
                c[0] = new_values[vi]
                c[3] = 1.0
                attr.data[loop_idx].color = tuple(c)
                
            obj.data.update()
            
            # Force viewport refresh
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                    
            return {'FINISHED'}
        except Exception as e:
            print(f"[MLD] Sharpen mask failed: {e}")
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


# Правильный список классов для регистрации
_CLASSES = (
    MLD_OT_create_mask,      # Был пропущен!
    MLD_OT_toggle_paint,
    MLD_OT_fill_mask,
    MLD_OT_blur_mask,
    MLD_OT_sharpen_mask,     # Теперь будет зарегистрирован
    MLD_OT_copy_mask,
    MLD_OT_paste_mask,
    MLD_OT_invert_mask,
    MLD_OT_add_mask_from_clip,
    MLD_OT_sub_mask_from_clip,
)

def register():
    print("[MLD] Registering mask operators...")
    print(f"[MLD] Total operators to register: {len(_CLASSES)}")
    for i, cls in enumerate(_CLASSES):
        try:
            print(f"[MLD] [{i+1}] Attempting to register {cls.__name__} -> {cls.bl_idname}")
            bpy.utils.register_class(cls)
            print(f"[MLD] ✓ Successfully registered {cls.bl_idname}")
        except Exception as e:
            print(f"[MLD] ✗ Failed to register {cls.bl_idname}: {e}")
            import traceback
            traceback.print_exc()
    print("[MLD] Mask operators registration complete.")

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