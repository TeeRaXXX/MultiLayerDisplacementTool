# Layer management (add/remove/move)
import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, IntProperty
from .utils import active_obj
from .attrs import remove_color_attr

class MLD_OT_add_layer(Operator):
    bl_idname = "mld.add_layer"
    bl_label = "Add Layer"
    def execute(self, context):
        obj=active_obj(context); s=obj.mld_settings
        L=s.layers.add(); idx=len(s.layers)
        L.name=f"New Layer {idx}"
        L.mask_name=f"MLD_Mask_{idx}"
        s.active_layer_index=idx-1
        return {'FINISHED'}

class MLD_OT_remove_layer(Operator):
    bl_idname = "mld.remove_layer"
    bl_label = "Remove Layer"
    layer_index: IntProperty(default=-1)
    def execute(self, context):
        obj=active_obj(context); s=obj.mld_settings
        i=s.active_layer_index
        if 0<=i<len(s.layers):
            name = s.layers[i].mask_name
            s.layers.remove(i)
            if name: remove_color_attr(obj.data, name)
            s.active_layer_index=min(i, len(s.layers)-1) if s.layers else 0
        return {'FINISHED'}
class MLD_OT_move_layer(Operator):
    bl_idname = "mld.move_layer"
    bl_label = "Move Layer"
    layer_index: IntProperty(default=-1)
    direction: EnumProperty(items=[('UP','Up',''),('DOWN','Down','')])
    def execute(self, context):
        obj=active_obj(context); s=obj.mld_settings
        i=s.active_layer_index
        if not (0<=i<len(s.layers)): return {'CANCELLED'}
        new = i-1 if self.direction=='UP' else i+1
        if not (0<=new<len(s.layers)): return {'CANCELLED'}
        s.layers.move(i, new)
        s.active_layer_index=new
        return {'FINISHED'}
classes = (MLD_OT_add_layer, MLD_OT_remove_layer, MLD_OT_move_layer)

def register():
    for c in classes: bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
