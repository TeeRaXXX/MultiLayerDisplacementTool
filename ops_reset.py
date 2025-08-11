
import bpy
from bpy.types import Operator
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

class MLD_OT_reset_displacement(Operator):
    bl_idname = "mld.reset_displacement"
    bl_label = "Reset Displacement"
    bl_options = {'UNDO'}
    def execute(self, ctx):
        obj = ctx.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        for name in (GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try: obj.modifiers.remove(md)
                except Exception: pass
        return {'FINISHED'}

class MLD_OT_reset_layers(Operator):
    bl_idname = "mld.reset_layers"
    bl_label = "Reset Layers"
    bl_options = {'UNDO'}
    def execute(self, ctx):
        obj = ctx.object
        s = getattr(obj, "mld_settings", None)
        if not s:
            return {'CANCELLED'}
        try:
            s.layers.clear()
            s.active_index = 0
        except Exception:
            pass
        return {'FINISHED'}

_CLASSES = (MLD_OT_reset_displacement, MLD_OT_reset_layers)

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
