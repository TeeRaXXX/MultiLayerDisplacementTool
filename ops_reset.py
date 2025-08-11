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
        
        # Remove modifiers
        for name in (GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try: 
                    obj.modifiers.remove(md)
                except Exception: 
                    pass
                    
        # Remove carrier object
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
            
        # Remove mask attributes
        try:
            from .ops_masks import cleanup_mask_attributes
            removed = cleanup_mask_attributes(obj)
            print(f"[MLD] Removed mask attributes: {removed}")
        except Exception as e:
            print(f"[MLD] Failed to clean mask attributes: {e}")
            
        # Clear layers
        try:
            s.layers.clear()
            s.active_index = 0
            s.is_painting = False
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