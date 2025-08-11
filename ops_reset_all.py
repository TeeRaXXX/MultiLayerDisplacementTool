# ops_reset_all.py
import bpy
from bpy.types import Operator
from .utils import active_obj
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

class MLD_OT_reset_all(Operator):
    bl_idname = "mld.reset_all"
    bl_label = "Reset All"
    bl_description = "Clear GN & carrier, remove all MLD masks and settings"

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        s = obj.mld_settings

        # remove modifiers
        for name in (GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try:
                    obj.modifiers.remove(md)
                except Exception:
                    pass

        # remove carrier
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

        # remove preview material (если есть и не используется)
        pname = f"MLD_Preview::{obj.name}"
        pm = bpy.data.materials.get(pname)
        if pm and pm.users == 0:
            try:
                bpy.data.materials.remove(pm, do_unlink=True)
            except Exception:
                pass

        # удалить маски/пак VC на самом меше
        me = obj.data
        if hasattr(me, "color_attributes"):
            for a in list(me.color_attributes):
                if a.name.startswith("MLD_Mask_") or a.name == "MLD_Pack":
                    try:
                        me.color_attributes.remove(a)
                    except Exception:
                        pass
        elif hasattr(me, "vertex_colors"):
            for a in list(me.vertex_colors):
                if a.name.startswith("MLD_Mask_") or a.name == "MLD_Pack":
                    try:
                        me.vertex_colors.remove(a)
                    except Exception:
                        pass
        me.update()

        # сброс настроек
        s.layers.clear()
        s.is_painting = False
        s.vc_packed = False

        self.report({'INFO'}, "MLD: Reset All done.")
        return {'FINISHED'}

classes = (MLD_OT_reset_all,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
