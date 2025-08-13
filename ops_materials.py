# ops_materials.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from __future__ import annotations
import bpy
from bpy.types import Operator
from .utils import active_obj
from .constants import ALPHA_PREFIX

# ---------------- helpers ----------------

def _ensure_obj_mode(obj: bpy.types.Object):
    """Ensure object is in Object mode and active."""
    ctx = bpy.context
    if ctx.view_layer.objects.active is not obj:
        ctx.view_layer.objects.active = obj
    if not obj.select_get():
        obj.select_set(True)
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def _ensure_mat_slot(obj: bpy.types.Object, mat: bpy.types.Material) -> int:
    """Ensure material is in object's material slots, return slot index."""
    slots = obj.data.materials
    for i, m in enumerate(slots):
        if m is mat:
            return i
    # Add material to new slot
    slots.append(mat)
    return len(slots) - 1

def _poly_alpha(me: bpy.types.Mesh, layer_index: int, poly: bpy.types.MeshPolygon) -> float:
    """Get average point-domain ALPHA_i over polygon vertices."""
    attr = me.attributes.get(f"{ALPHA_PREFIX}{layer_index}")
    if not attr:
        return 0.0
    
    try:
        acc = 0.0
        cnt = len(poly.vertices)
        for vi in poly.vertices:
            if vi < len(attr.data):
                acc += float(attr.data[vi].value)
        return acc / max(1, cnt)
    except Exception:
        return 0.0

# ---------------- operator ----------------

class MLD_OT_assign_materials(Operator):
    """Assign materials by actual displacement result (ALPHA winners)."""
    bl_idname  = "mld.assign_materials_from_disp"  # FIXED: consistent with pipeline
    bl_label   = "Assign Materials by Displacement"
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}
        
        s = obj.mld_settings
        me = obj.data

        _ensure_obj_mode(obj)

        # Check if we have ALPHA attributes (displacement must be calculated first)
        has_alphas = False
        for i in range(len(s.layers)):
            if me.attributes.get(f"{ALPHA_PREFIX}{i}"):
                has_alphas = True
                break
        
        if not has_alphas:
            self.report({'ERROR'}, "No displacement data found. Run Recalculate first.")
            return {'CANCELLED'}

        # Build material slots for enabled layers with materials
        slot_by_layer = {}
        for i, L in enumerate(s.layers):
            if L.enabled and L.material:
                slot_by_layer[i] = _ensure_mat_slot(obj, L.material)
        
        if not slot_by_layer:
            self.report({'WARNING'}, "No enabled layers with materials to assign.")
            return {'CANCELLED'}

        # Get threshold
        thr = float(getattr(s, 'mat_assign_threshold', 
                           getattr(s, 'assign_threshold', 
                                  getattr(s, 'mask_threshold', 0.05))))

        changed = 0
        total_polys = len(me.polygons)

        # Assign materials based on strongest displacement per polygon
        for poly in me.polygons:
            best_layer = None
            best_alpha = 0.0
            
            # Find layer with highest alpha for this polygon
            for layer_idx, slot_idx in slot_by_layer.items():
                alpha = _poly_alpha(me, layer_idx, poly)
                if alpha > best_alpha:
                    best_alpha = alpha
                    best_layer = layer_idx
            
            # Assign material if alpha is above threshold
            if best_layer is not None and best_alpha >= thr:
                target_slot = slot_by_layer[best_layer]
                if poly.material_index != target_slot:
                    poly.material_index = target_slot
                    changed += 1

        me.update()
        
        # Report results
        percentage = (changed / max(1, total_polys)) * 100
        self.report({'INFO'}, 
                   f"Assigned materials: {changed}/{total_polys} polygons ({percentage:.1f}%)")
        
        return {'FINISHED'}

# Register/Unregister
def register():
    bpy.utils.register_class(MLD_OT_assign_materials)

def unregister():
    bpy.utils.unregister_class(MLD_OT_assign_materials)


class MLD_OT_apply_packed_vc_shader(Operator):
    """Apply shader that works with packed vertex colors after mesh bake."""
    bl_idname = "mld.apply_packed_vc_shader"
    bl_label = "Apply Packed VC Shader"
    bl_description = "Create and apply a shader that reads from packed vertex colors"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}
        
        s = obj.mld_settings
        
        # Check if we have packed vertex colors
        vc_name = getattr(s, 'vc_attribute_name', 'Color')
        if not hasattr(obj.data, "vertex_colors") or not obj.data.vertex_colors:
            self.report({'ERROR'}, "No vertex colors found on mesh. Run Bake Mesh first.")
            return {'CANCELLED'}
        
        # Check if the specific vertex color exists
        vc_layer = None
        for vc in obj.data.vertex_colors:
            if vc.name == vc_name:
                vc_layer = vc
                break
        
        if not vc_layer:
            self.report({'ERROR'}, f"Packed vertex color '{vc_name}' not found. Run Bake Mesh first.")
            return {'CANCELLED'}
        
        # Check if we have layers with VC channel assignments
        has_assignments = False
        for L in s.layers:
            if getattr(L, "vc_channel", 'NONE') in {'R', 'G', 'B', 'A'}:
                has_assignments = True
                break
        
        if not has_assignments:
            self.report({'ERROR'}, "No layers with VC channel assignments found.")
            return {'CANCELLED'}
        
        # Import and apply the shader
        try:
            from .materials import build_packed_vc_preview_shader
            mat = build_packed_vc_preview_shader(obj, s)
            
            if mat:
                self.report({'INFO'}, f"Applied packed VC shader using '{vc_name}' attribute")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to create packed VC shader")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply packed VC shader: {e}")
            return {'CANCELLED'}


# Update register/unregister
classes = (MLD_OT_assign_materials, MLD_OT_apply_packed_vc_shader)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)