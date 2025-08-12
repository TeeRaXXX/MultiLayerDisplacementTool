# ui.py — UI Panel for Multi Layer Displacement Tool
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
    try:
        me = obj.data
        if not me:
            return "—"
        if not me.loop_triangles:
            me.calc_loop_triangles()
        return f"Tris: {len(me.loop_triangles):,}"
    except Exception:
        try:
            return f"Faces: {len(obj.data.polygons):,}"
        except Exception:
            return "—"

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

def _draw_layer_row(ui, layout, s, idx: int, active_idx: int, painting: bool):
    L = s.layers[idx]
    row = layout.row(align=True)

    # Blue select button for active layer (no radio buttons)
    sel = (idx == active_idx)
    bsel = row.operator("mld.ui_set_active", text=L.name or f"Layer {idx+1}")
    bsel.index = idx
    
    # Make active layer button blue
    if sel:
        bsel_row = row.row()
        bsel_row.alert = True  # This makes it red unfortunately, we'll use a different approach
    
    # Alternative: use emboss for active layer
    if sel:
        row.separator()
        # Add a small indicator
        indicator = row.row(align=True)
        indicator.scale_x = 0.3
        indicator.label(text="●", icon='NONE')

    # enable toggle
    row.prop(L, "enabled", text="")

    # material
    sub = row.row(align=True); sub.enabled = not painting
    sub.prop(L, "material", text="")

    # VC channel
    sub = row.row(align=True); sub.enabled = not painting
    if getattr(L, "vc_channel", 'NONE') == 'NONE':
        op = _op(sub, "mld.set_layer_channel", text="Set VC", icon='GROUP_VCOL')
        _set(op, layer_index=idx, index=idx)
    else:
        sub.label(text=L.vc_channel, icon='GROUP_VCOL')
        op = _op(sub, "mld.clear_layer_channel", text="", icon='X')
        _set(op, layer_index=idx, index=idx)

    # up / down / remove
    sub = row.row(align=True); sub.enabled = not painting
    op = _op(sub, "mld.move_layer", text="", icon='TRIA_UP');    _set(op, layer_index=idx, index=idx, direction='UP')
    op = _op(sub, "mld.move_layer", text="", icon='TRIA_DOWN');  _set(op, layer_index=idx, index=idx, direction='DOWN')
    op = _op(sub, "mld.remove_layer", text="", icon='X');        _set(op, layer_index=idx, index=idx)

# Custom draw method for active layer button with blue color
def _draw_active_layer_button(layout, s, idx: int, active_idx: int, L):
    """Draw layer selection button with blue highlight for active layer."""
    sel = (idx == active_idx)
    
    if sel:
        # Create a blue background using a box
        blue_box = layout.box()
        # Try to make it blue-ish by using different UI elements
        blue_row = blue_box.row(align=True)
        blue_row.scale_y = 0.8
        bsel = blue_row.operator("mld.ui_set_active", text=f"► {L.name or f'Layer {idx+1}'}")
        bsel.index = idx
        return blue_row
    else:
        # Normal button for non-active layers
        bsel = layout.operator("mld.ui_set_active", text=L.name or f"Layer {idx+1}")
        bsel.index = idx
        return layout

def _draw_layer_row_improved(ui, layout, s, idx: int, active_idx: int, painting: bool):
    """Improved layer row with blue active layer indication."""
    L = s.layers[idx]
    row = layout.row(align=True)
    
    # Active layer button (blue highlight)
    sel = (idx == active_idx)
    if sel:
        # Use a colored row/box for active layer
        button_layout = row.box() if sel else row
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
    if getattr(L, "vc_channel", 'NONE') == 'NONE':
        op = _op(sub, "mld.set_layer_channel", text="Set VC", icon='GROUP_VCOL')
        _set(op, layer_index=idx, index=idx)
    else:
        sub.label(text=L.vc_channel, icon='GROUP_VCOL')
        op = _op(sub, "mld.clear_layer_channel", text="", icon='X')
        _set(op, layer_index=idx, index=idx)

    # up / down / remove
    sub = row.row(align=True); sub.enabled = not painting
    op = _op(sub, "mld.move_layer", text="", icon='TRIA_UP');    _set(op, layer_index=idx, index=idx, direction='UP')
    op = _op(sub, "mld.move_layer", text="", icon='TRIA_DOWN');  _set(op, layer_index=idx, index=idx, direction='DOWN')
    op = _op(sub, "mld.remove_layer", text="", icon='X');        _set(op, layer_index=idx, index=idx)

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

        # 2) Polycount
        row = layout.row(align=True)
        row.label(text=_polycount_str(obj), icon='MESH_DATA')

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

        # 6) Mask tools - always show if we have any layers
        if has_layers:
            box = layout.box()
            box.label(text="Mask Paint")
            
            # Paint Mask button - always enabled when we have layers, dynamic text
            row = box.row(align=True)
            row.enabled = bool(has_layers)
            paint_text = "Stop Painting" if painting else "Paint Mask"
            row.operator('mld.toggle_paint', text=paint_text, icon='BRUSH_DATA')

            # Fill buttons - only active during painting
            sub = box.row(align=True)
            sub.enabled = painting
            op1 = sub.operator('mld.fill_mask', text='Fill 0%')
            if op1: op1.mode = 'ZERO'
            op2 = sub.operator('mld.fill_mask', text='Fill 100%') 
            if op2: op2.mode = 'ONE'

            # Blur/Sharpen row - only active during painting
            sub = box.row(align=True)
            sub.enabled = painting
            sub.operator("mld.blur_mask", text="Blur", icon='MOD_SMOOTH')
            sub.operator("mld.sharpen_mask", text="Sharpen", icon='MOD_EDGESPLIT')

            # Clipboard row - only active during painting
            sub = box.row(align=True); sub.enabled = painting and bool(has_layers)
            sub.operator("mld.copy_mask",  text="Copy",  icon='COPYDOWN')
            sub.operator("mld.paste_mask", text="Paste", icon='PASTEDOWN')
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
        _op(col, "mld.recalculate", text="Recalculate", icon='FILE_REFRESH')
        row = col.row(align=True)
        try:
            row.operator("mld.reset_displacement", text="Reset Displacement", icon='LOOP_BACK')
            row.operator("mld.reset_layers", text="Reset Layers", icon='TRASH')
        except Exception:
            lab = col.row(align=True); lab.enabled = False; lab.label(text="Reset ops missing")

        # 8) Subdivision refine
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Refine (Subdivision)")
        col.prop(s, "subdiv_enable", text="Enable")
        row = col.row(align=True)
        row.prop(s, "subdiv_type", text="Type")
        row = col.row(align=True)
        row.prop(s, "subdiv_view", text="Viewport Levels")
        row.prop(s, "subdiv_render", text="Render Levels")

        # 9) Materials + Preview
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Materials by displacement")
        col.prop(s, "auto_assign_materials", text="Auto assign on Recalculate")
        col.prop(s, "mask_threshold", text="Assign Threshold")
        _op(col, "mld.assign_materials_from_disp", text="Assign Materials", icon='MATERIAL')

        col.separator()
        col.label(text="Preview blend (materials)")
        col.prop(s, "preview_enable", text="Enable")
        sub = col.column(align=True); sub.enabled = bool(getattr(s, "preview_enable", False))
        sub.prop(s, "preview_mask_influence")
        sub.prop(s, "preview_contrast")

        # 10) Decimate (preview after GN)
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Decimate (preview after GN)")
        col.prop(s, "decimate_enable", text="Enable")
        sub = col.row(align=True); sub.enabled = bool(getattr(s, "decimate_enable", False))
        sub.prop(s, "decimate_ratio", text="Ratio")

        # 11) Pack Vertex Colors
        box = layout.box()
        col = box.column(align=True); col.enabled = not painting
        col.label(text="Pack Vertex Colors")
        col.prop(s, "fill_empty_vc_white")
        _op(col, "mld.pack_vcols", text="Pack to VC", icon='GROUP_VCOL')

        # 12) Bake
        row = layout.row(align=True); row.enabled = not painting
        _op(row, "mld.bake_mesh", text="Bake Mesh", icon='CHECKMARK')


# --------------- register -----------------------------------------------------

classes = (MLD_OT_ui_set_active, VIEW3D_PT_mld)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)