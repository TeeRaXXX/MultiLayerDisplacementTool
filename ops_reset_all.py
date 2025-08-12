# ops_reset_all.py
import bpy
from bpy.types import Operator
from .utils import active_obj
from .constants import (
    GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME,
    # Default values
    DEFAULT_ACTIVE_INDEX, DEFAULT_PAINTING, DEFAULT_VC_PACKED,
    DEFAULT_STRENGTH, DEFAULT_MIDLEVEL, DEFAULT_FILL_POWER,
    DEFAULT_SUBDIV_ENABLE, DEFAULT_SUBDIV_TYPE, DEFAULT_SUBDIV_VIEW, DEFAULT_SUBDIV_RENDER,
    DEFAULT_AUTO_ASSIGN_MATERIALS, DEFAULT_MASK_THRESHOLD, DEFAULT_ASSIGN_THRESHOLD,
    DEFAULT_PREVIEW_ENABLE, DEFAULT_PREVIEW_BLEND, DEFAULT_PREVIEW_MASK_INFLUENCE, DEFAULT_PREVIEW_CONTRAST,
    DEFAULT_DECIMATE_ENABLE, DEFAULT_DECIMATE_RATIO,
    DEFAULT_FILL_EMPTY_VC_WHITE,
    DEFAULT_LAST_POLY_V, DEFAULT_LAST_POLY_F, DEFAULT_LAST_POLY_T
)

class MLD_OT_reset_all(Operator):
    bl_idname = "mld.reset_all"
    bl_label = "Reset All"
    bl_description = "Clear GN & carrier, remove all MLD masks, materials and settings"

    def _remove_all_mld_materials(self, obj):
        """Remove ALL MLD-related materials from object and data."""
        if not obj or obj.type != 'MESH':
            return []
            
        removed = []
        materials_to_remove = []
        
        # Get settings to check layer materials
        s = getattr(obj, "mld_settings", None)
        layer_materials = set()
        if s:
            for layer in s.layers:
                if layer.material:
                    layer_materials.add(layer.material.name)
        
        # Find ALL MLD materials in object slots (various prefixes)
        for i, mat in enumerate(obj.data.materials):
            if mat and (
                mat.name.startswith("MLD_Preview::") or
                mat.name.startswith("MLD_") or
                mat.name.startswith("MLD_HeightLerp::") or
                mat.name.startswith("MLD_Displacement::") or
                mat.name in layer_materials  # Remove materials assigned to layers
            ):
                materials_to_remove.append((i, mat))
                
        # Remove from slots (in reverse order to maintain indices)
        for i, mat in reversed(materials_to_remove):
            try:
                obj.data.materials.pop(index=i)
                removed.append(mat.name)
            except Exception:
                pass
        
        # Remove unused MLD materials from data (all MLD prefixes + layer materials)
        mld_materials = [mat for mat in bpy.data.materials 
                         if ((mat.name.startswith("MLD_Preview::") or
                              mat.name.startswith("MLD_") or
                              mat.name.startswith("MLD_HeightLerp::") or
                              mat.name.startswith("MLD_Displacement::") or
                              mat.name in layer_materials) and 
                         mat.users == 0)]
        
        for mat in mld_materials:
            try:
                bpy.data.materials.remove(mat, do_unlink=True)
                if mat.name not in removed:
                    removed.append(mat.name)
            except Exception:
                pass
                
        return removed

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        s = obj.mld_settings

        # Exit painting mode if active
        if getattr(s, 'is_painting', False) or getattr(s, 'painting', False):
            try:
                if obj.mode == 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
            except Exception:
                pass

        # Remove modifiers
        for name in (GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try:
                    obj.modifiers.remove(md)
                except Exception:
                    pass

        # Remove carrier
        cname = f"MLD_Carrier::{obj.name}"
        carr = bpy.data.objects.get(cname)
        if carr:
            try:
                me = carr.data
                bpy.data.objects.remove(carr, do_unlink=True)
                if me and me.users == 0:
                    bpy.data.meshes.remove(me, do_unlink=True)
            except Exception:
                pass

        # Remove mask attributes using new cleanup function
        try:
            from .ops_masks import cleanup_mask_attributes
            removed_attrs = cleanup_mask_attributes(obj)
            print(f"[MLD] Removed attributes: {removed_attrs}")
        except Exception as e:
            print(f"[MLD] Failed to clean attributes: {e}")

        # Remove ALL MLD-related materials from object
        try:
            removed_mats = self._remove_all_mld_materials(obj)
            print(f"[MLD] Removed materials: {removed_mats}")
        except Exception as e:
            print(f"[MLD] Failed to clean materials: {e}")

        # Clear layer materials before clearing layers
        for layer in s.layers:
            if layer.material:
                layer.material = None
        
        # Reset ALL settings to default values using constants
        s.layers.clear()
        s.is_painting = DEFAULT_PAINTING
        s.vc_packed = DEFAULT_VC_PACKED
        s.active_index = DEFAULT_ACTIVE_INDEX
        
        # Reset global displacement parameters to defaults
        s.strength = DEFAULT_STRENGTH
        s.midlevel = DEFAULT_MIDLEVEL
        s.fill_power = DEFAULT_FILL_POWER
        
        # Reset subdivision settings to defaults
        s.subdiv_enable = DEFAULT_SUBDIV_ENABLE
        s.subdiv_type = DEFAULT_SUBDIV_TYPE
        s.subdiv_view = DEFAULT_SUBDIV_VIEW
        s.subdiv_render = DEFAULT_SUBDIV_RENDER
        
        # Reset material assignment settings to defaults
        s.auto_assign_materials = DEFAULT_AUTO_ASSIGN_MATERIALS
        s.mask_threshold = DEFAULT_MASK_THRESHOLD
        s.assign_threshold = DEFAULT_ASSIGN_THRESHOLD
        
        # Reset preview settings to defaults
        s.preview_enable = DEFAULT_PREVIEW_ENABLE
        s.preview_blend = DEFAULT_PREVIEW_BLEND
        s.preview_mask_influence = DEFAULT_PREVIEW_MASK_INFLUENCE
        s.preview_contrast = DEFAULT_PREVIEW_CONTRAST
        
        # Reset decimate settings to defaults
        s.decimate_enable = DEFAULT_DECIMATE_ENABLE
        s.decimate_ratio = DEFAULT_DECIMATE_RATIO
        
        # Reset vertex color packing settings to defaults
        s.fill_empty_vc_white = DEFAULT_FILL_EMPTY_VC_WHITE
        
        # Reset polycount tracking to defaults
        s.last_poly_v = DEFAULT_LAST_POLY_V
        s.last_poly_f = DEFAULT_LAST_POLY_F
        s.last_poly_t = DEFAULT_LAST_POLY_T

        self.report({'INFO'}, "MLD: Reset All done - all settings restored to defaults.")
        return {'FINISHED'}

classes = (MLD_OT_reset_all,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)