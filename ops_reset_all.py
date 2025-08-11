# ops_reset_all.py
import bpy
from bpy.types import Operator
from .utils import active_obj
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

class MLD_OT_reset_all(Operator):
    bl_idname = "mld.reset_all"
    bl_label = "Reset All"
    bl_description = "Clear GN & carrier, remove all MLD masks, materials and settings"

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

        # Remove MLD materials using new cleanup function
        try:
            from .settings import remove_mld_materials
            removed_mats = remove_mld_materials(obj)
            print(f"[MLD] Removed materials: {removed_mats}")
        except Exception as e:
            print(f"[MLD] Failed to clean materials: {e}")

        # Reset settings
        s.layers.clear()
        s.is_painting = False
        s.vc_packed = False
        s.active_index = 0

        self.report({'INFO'}, "MLD: Reset All done.")
        return {'FINISHED'}

classes = (MLD_OT_reset_all,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)