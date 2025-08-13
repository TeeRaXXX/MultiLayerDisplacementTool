# ui.py — UI Panel for Multi Layer Displacement Tool (ИСПРАВЛЕННАЯ ВЕРСИЯ)
from __future__ import annotations
import bpy
from bpy.props import IntProperty

# ----------------- helpers ----------------------------------------------------

def _s(obj):
    if obj and getattr(obj, "mld_settings", None):
        return obj.mld_settings
    return getattr(bpy.context.scene, "mld_settings", None)

def _is_painting(s) -> bool:
    return bool(getattr(s, "is_painting", getattr(s, "painting", False)))

def _active_idx(s) -> int:
    return int(getattr(s, "active_layer_index", getattr(s, "active_index", 0)))

def _polycount_str(obj: bpy.types.Object) -> str:
    """Get comprehensive polycount info with evaluated mesh."""
    try:
        from .utils import polycount, get_evaluated_polycount, format_polycount
        
        # Original mesh
        orig_v, orig_f, orig_t = polycount(obj.data)
        
        # Evaluated mesh (with all modifiers) - force fresh calculation
        eval_v, eval_f, eval_t = get_evaluated_polycount(obj, verbose=False)
        
        # If they're the same, show simple format
        if orig_v == eval_v and orig_f == eval_f:
            return f"Tris: {orig_t:,}"
        else:
            # Show both original and final
            multiplier = eval_t / orig_t if orig_t > 0 else 1.0
            if multiplier > 1.1:  # Show multiplier if significant increase
                return f"Orig: {orig_t:,}T → Final: {eval_t:,}T ({multiplier:.1f}x)"
            else:
                return f"Orig: {orig_t:,}T → Final: {eval_t:,}T"
            
    except Exception:
        try:
            # Fallback to simple count
            if not obj.data.loop_triangles:
                obj.data.calc_loop_triangles()
            return f"Tris: {len(obj.data.loop_triangles):,}"
        except Exception:
            return "—"

def _get_detailed_polycount_info(obj: bpy.types.Object, s) -> list:
    """Get detailed polycount breakdown including displacement and decimate stages."""
    info_lines = []
    
    try:
        from .utils import polycount, get_evaluated_polycount
        
        # Original mesh
        orig_v, orig_f, orig_t = polycount(obj.data)
        
        # Calculate final polycount through pipeline
        current_tris = orig_t
        pipeline_info = []
        
        # After subdivision (if enabled)
        if getattr(s, "subdiv_enable", False):
            subdiv_levels = getattr(s, "subdiv_view", 1)
            if subdiv_levels > 0:
                subdiv_tris = orig_t * (4 ** subdiv_levels)
                current_tris = subdiv_tris
                pipeline_info.append(f"Subdiv: {subdiv_tris:,}")
        
        # After displacement (if we have displacement data)
        try:
            has_displacement = False
            for attr in obj.data.attributes:
                if attr.name.startswith("MLD_") and attr.data_type == 'FLOAT_VECTOR':
                    has_displacement = True
                    break
            
            if has_displacement:
                eval_v, eval_f, eval_t = get_evaluated_polycount(obj, verbose=False)
                if eval_t != current_tris:
                    current_tris = eval_t
                    pipeline_info.append(f"Disp: {eval_t:,}")
        except Exception:
            pass
        
        # After decimate (if enabled)
        if getattr(s, "decimate_enable", False):
            decimate_ratio = getattr(s, "decimate_ratio", 0.5)
            if decimate_ratio < 1.0:
                decimate_tris = int(current_tris * decimate_ratio)
                current_tris = decimate_tris
                pipeline_info.append(f"Decimate: {decimate_tris:,}")
        
        # Create compact summary
        if len(pipeline_info) > 0:
            info_lines.append(f"Pipeline: {' → '.join(pipeline_info)}")
            info_lines.append(f"Final: {current_tris:,} tris")
        else:
            info_lines.append(f"Current: {orig_t:,} tris")
        
    except Exception:
        info_lines.append("Error calculating polycount")
    
    return info_lines

def _op(layout, idname, text=None, icon='NONE'):
    try:
        return layout.operator(idname, text=text if text is not None else "", icon=icon)
    except Exception:
        row = layout.row(); row.enabled = False
        row.label(text=f"{text or idname} (op missing)")
        return None

def _op_any(layout, ids, text, icon='NONE'):
    """Try several operator idnames; return the first that exists."""
    for _id in ids:
        try:
            return layout.operator(_id, text=text, icon=icon)
        except Exception:
            continue
    row = layout.row(); row.enabled = False
    row.label(text=f"{text} (op missing)")
    return None

def _set(op, **kwargs):
    if not op:
        return
    for k, v in kwargs.items():
        if hasattr(op, k):
            setattr(op, k, v)

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

# ----------------- tiny operator to set active layer --------------------------

class MLD_OT_ui_set_active(bpy.types.Operator):
    """Set active layer index from UI row click"""
    bl_idname = "mld.ui_set_active"
    bl_label  = "Set Active Layer (UI)"
    bl_options = {'INTERNAL'}

    index: IntProperty(default=0)

    def execute(self, context):
        s = _s(context.object)
        if not s:
            return {'CANCELLED'}
        if 0 <= self.index < len(s.layers):
            # old/new names compatibility
            if hasattr(s, "active_layer_index"):
                s.active_layer_index = self.index
            elif hasattr(s, "active_index"):
                s.active_index = self.index
        return {'FINISHED'}

# ----------------- validation drawer -----------------------------------------

def _draw_validation(layout, context, s):
    box = layout.box()
    row = box.row(align=True); row.label(text="Validation", icon='INFO')
    try:
        from .validation import collect_validation
        obj = context.object
        msgs = collect_validation(obj) or []
        if not msgs:
            box.label(text="No issues found.", icon='CHECKMARK')
        else:
            for t, txt in msgs:
                icon = 'ERROR' if (t or "").lower() == 'error' else 'QUESTION'
                box.label(text=txt, icon=icon)
    except Exception:
        box.label(text="No issues found.", icon='CHECKMARK')

# ----------------- layer row --------------------------------------------------

def _draw_layer_row_improved(ui, layout, s, idx: int, active_idx: int, painting: bool):
    """Layer row with active layer indication and smart arrows."""
    L = s.layers[idx]
    row = layout.row(align=True)
    
    # Active layer button
    sel = (idx == active_idx)
    if sel:
        # Use a colored row for active layer
        button_layout = row.box()
        bsel = button_layout.operator("mld.ui_set_active", text=f"● {L.name or f'Layer {idx+1}'}")
    else:
        bsel = row.operator("mld.ui_set_active", text=L.name or f"Layer {idx+1}")
    bsel.index = idx

    # enable toggle
    row.prop(L, "enabled", text="")

    # material
    sub = row.row(align=True); sub.enabled = not painting
    sub.prop(L, "material", text="")

    # VC channel
    sub = row.row(align=True); sub.enabled = not painting
    current_channel = getattr(L, "vc_channel", 'NONE')
    if current_channel == 'NONE':
        op = _op(sub, "mld.set_layer_channel", text="Set VC", icon='GROUP_VCOL')
        _set(op, layer_index=idx, index=idx)
    else:
        op = _op(sub, "mld.set_layer_channel", text=current_channel, icon='GROUP_VCOL')
        _set(op, layer_index=idx, index=idx)

    # Smart up / down / remove arrows
    sub = row.row(align=True); sub.enabled = not painting
    
    # Up arrow - disabled for top layer (index 0)
    up_row = sub.row(); up_row.enabled = (idx > 0)
    op = _op(up_row, "mld.move_layer", text="", icon='TRIA_UP')
    _set(op, layer_index=idx, index=idx, direction='UP')
    
    # Down arrow - disabled for bottom layer (last index)
    down_row = sub.row(); down_row.enabled = (idx < len(s.layers) - 1)
    op = _op(down_row, "mld.move_layer", text="", icon='TRIA_DOWN')
    _set(op, layer_index=idx, index=idx, direction='DOWN')
    
    # Remove button - always enabled
    op = _op(sub, "mld.remove_layer", text="", icon='X')
    _set(op, layer_index=idx, index=idx)

# ----------------- main panel -------------------------------------------------

class VIEW3D_PT_mld(bpy.types.Panel):
    bl_label = "Multi Layer Displacement"
    bl_idname = "VIEW3D_PT_mld"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "MLD Tool"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        s = _s(obj)

        if not obj or obj.type != 'MESH' or s is None:
            layout.label(text="Select a mesh object.", icon='MESH_DATA')
            return

        painting = _is_painting(s)

        # 0) Validation
        _draw_validation(layout, context, s)

        # 1) Settings I/O
        row = layout.row(align=True)
        sub = row.row(align=True); sub.enabled = not painting
        _op(sub, "mld.copy_settings",  text="Copy",  icon='COPYDOWN')
        _op(sub, "mld.paste_settings", text="Paste", icon='PASTEDOWN')
        _op(sub, "mld.reset_all",      text="Reset All", icon='TRASH')

        # 2) Polycount with detailed info
        box = layout.box()
        
        # Detailed polycount breakdown (compact)
        detailed_info = _get_detailed_polycount_info(obj, s)
        if len(detailed_info) > 0:
            col = box.column(align=True)
            col.scale_y = 0.8
            
            # Show first line with icon, rest without
            for i, info_line in enumerate(detailed_info):
                if i == 0:
                    col.label(text=info_line, icon='MESH_DATA')
                else:
                    col.label(text=info_line, icon='NONE')
        
        # Legacy info removed for cleaner UI

        # 3) Global parameters
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Global Displacement")
        col.prop(s, "strength")
        col.prop(s, "midlevel")
        col.prop(s, "fill_power")

        # 4) Layers list
        box = layout.box()
        header = box.row(align=True)
        header.label(text="Layers")
        r = header.row(align=True); r.enabled = not painting
        _op(r, "mld.add_layer", text="", icon='ADD')

        has_layers = len(s.layers) > 0
        ai = _active_idx(s)
        
        if has_layers:
            for i in range(len(s.layers)):
                _draw_layer_row_improved(self, box, s, i, ai, painting)
        else:
            box.label(text="No layers yet. Click + to add.", icon='INFO')

        # 5) Active layer settings
        ai = max(0, min(ai, len(s.layers)-1)) if has_layers else -1
        L = s.layers[ai] if has_layers else None
        box = layout.box()
        box.label(text="Active Layer Settings")
        if L:
            col = box.column(align=True); col.enabled = not painting
            col.prop(L, "multiplier")
            col.prop(L, "bias")
            col.prop(L, "tiling")
            col.prop(L, "mask_name", text="Mask Attribute")
        else:
            box.label(text="Select a layer.", icon='BLANK1')

        # 6) Mask tools - show if we have any layers
        if has_layers:
            box = layout.box()
            box.label(text="Mask Paint")
            
            # Paint Mask button - automatically creates mask on first use
            row = box.row(align=True)
            paint_text = "Stop Painting" if painting else "Paint Mask"
            paint_icon = 'BRUSH_DATA' if not painting else 'X'
            row.operator('mld.toggle_paint', text=paint_text, icon=paint_icon)

            # Fill buttons - only active during painting
            sub = box.row(align=True)
            sub.enabled = painting
            op1 = sub.operator('mld.fill_mask', text='0% (Black)')
            if op1: op1.mode = 'ZERO'
            op2 = sub.operator('mld.fill_mask', text='100% (Red)') 
            if op2: op2.mode = 'ONE'

            # Blur/Sharpen row - only active during painting
            sub = box.row(align=True)
            sub.enabled = painting
            sub.operator("mld.blur_mask", text="Blur", icon='MOD_SMOOTH')
            sub.operator("mld.sharpen_mask", text="Sharpen", icon='MOD_EDGESPLIT')

            # Clipboard operations - only active during painting
            sub = box.row(align=True)
            sub.enabled = painting
            sub.operator("mld.copy_mask", text="Copy", icon='COPYDOWN')
            sub.operator("mld.paste_mask", text="Paste", icon='PASTEDOWN')
            
            # Advanced clipboard operations
            sub = box.row(align=True)
            sub.enabled = painting
            sub.operator("mld.add_mask_from_clip", text="Add", icon='ADD')
            sub.operator("mld.sub_mask_from_clip", text="Sub", icon='REMOVE')
            sub.operator("mld.invert_mask", text="Invert", icon='ARROW_LEFTRIGHT')
        else:
            # Show message when no layers
            box = layout.box()
            box.label(text="Mask Paint")
            box.label(text="Add layers to enable mask tools.", icon='INFO')

        # 7) Recalculate + Resets
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        
        # Recalculate button - 2x height
        recalc_row = col.row(align=True)
        recalc_row.scale_y = 2.0
        _op(recalc_row, "mld.recalculate", text="Recalculate", icon='FILE_REFRESH')
        
        # Reset buttons
        row = col.row(align=True)
        try:
            row.operator("mld.reset_displacement", text="Reset Displacement", icon='LOOP_BACK')
            row.operator("mld.reset_layers", text="Reset Layers", icon='TRASH')
        except Exception:
            lab = col.row(align=True); lab.enabled = False; lab.label(text="Reset ops missing")

        # 8) Subdivision refine
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        
        # Header with info
        header = col.row(align=True)
        header.label(text="Refine (Subdivision)", icon='MOD_SUBSURF')
        info_button = header.row()
        info_button.scale_x = 0.5
        info_button.label(text="📝", icon='NONE')  # Indicates changes applied on Recalculate
        
        col.prop(s, "subdiv_enable", text="Enable")
        if getattr(s, "subdiv_enable", False):
            row = col.row(align=True)
            row.prop(s, "subdiv_type", text="")
            row = col.row(align=True)
            row.prop(s, "subdiv_view", text="Viewport")
            row.prop(s, "subdiv_render", text="Render")
            
            # Subtle hint
            hint = col.row()
            hint.scale_y = 0.7
            hint.label(text="Applied on Recalculate", icon='INFO')

        # 9) Materials + Preview
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Materials Assignment")
        col.prop(s, "auto_assign_materials", text="Auto assign on Recalculate")
        col.prop(s, "mask_threshold", text="Assignment Threshold")
        _op(col, "mld.assign_materials_from_disp", text="Assign Now", icon='MATERIAL')

        col.separator()
        
        # Preview header with info
        header = col.row(align=True)
        header.label(text="Preview Materials", icon='MATERIAL')
        info_button = header.row()
        info_button.scale_x = 0.5
        info_button.label(text="📝", icon='NONE')  # Indicates changes applied on Recalculate
        
        col.prop(s, "preview_enable", text="Enable Preview")
        if getattr(s, "preview_enable", False):
            # Subtle hint
            hint = col.row()
            hint.scale_y = 0.7
            hint.label(text="Applied on Recalculate", icon='INFO')

        # 10) Decimate (preview)
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        
        # Header with info
        header = col.row(align=True)
        header.label(text="Decimate (preview)", icon='MOD_DECIM')
        info_button = header.row()
        info_button.scale_x = 0.5
        info_button.label(text="📝", icon='NONE')  # Indicates changes applied on Recalculate
        
        col.prop(s, "decimate_enable", text="Enable")
        if getattr(s, "decimate_enable", False):
            sub = col.row(align=True)
            sub.prop(s, "decimate_ratio", text="Ratio")
            
            # Subtle hint
            hint = col.row()
            hint.scale_y = 0.7
            hint.label(text="Applied on Recalculate", icon='INFO')

        # 11) Bake
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        
        # Header
        col.label(text="Bake Mesh", icon='CHECKMARK')
        
        # Pack to Vertex Colors section
        col.prop(s, "bake_pack_vc", text="Pack to Vertex Colors")
        
        if getattr(s, "bake_pack_vc", False):
            # Show which channels are assigned
            assigned_channels = []
            for L in s.layers:
                ch = getattr(L, "vc_channel", 'NONE')
                if ch in ['R', 'G', 'B']:
                    assigned_channels.append(ch)
            
            if assigned_channels:
                info_text = f"Assigned: {', '.join(sorted(assigned_channels))}"
                col.label(text=info_text, icon='INFO')
            else:
                col.label(text="No channels assigned", icon='ERROR')
            
            col.prop(s, "bake_vc_attribute_name", text="Attribute Name")
            col.prop(s, "fill_empty_vc_white", text="Fill empty with white")
            
            # Check for name conflicts
            bake_vc_name = getattr(s, "bake_vc_attribute_name", "Color")
            conflict_found = False
            for L in s.layers:
                mask_name = getattr(L, 'mask_name', '')
                if mask_name and mask_name == bake_vc_name:
                    conflict_found = True
                    break
            
            if conflict_found:
                col.label(text=f"⚠ Name conflicts with layer mask", icon='ERROR')
        
        # Bake button
        bake_row = col.row()
        if getattr(s, "bake_pack_vc", False):
            # Check if channels are assigned when pack VC is enabled
            assigned_channels = []
            for L in s.layers:
                ch = getattr(L, "vc_channel", 'NONE')
                if ch in ['R', 'G', 'B']:
                    assigned_channels.append(ch)
            
            # Check for name conflicts
            bake_vc_name = getattr(s, "bake_vc_attribute_name", "Color")
            conflict_found = False
            for L in s.layers:
                mask_name = getattr(L, 'mask_name', '')
                if mask_name and mask_name == bake_vc_name:
                    conflict_found = True
                    break
            
            bake_row.enabled = len(assigned_channels) > 0 and not conflict_found
        else:
            bake_row.enabled = True
        _op(bake_row, "mld.bake_mesh", text="Bake Mesh", icon='CHECKMARK')


# --------------- register -----------------------------------------------------

classes = (MLD_OT_ui_set_active, VIEW3D_PT_mld)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)