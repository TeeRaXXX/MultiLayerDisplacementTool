# ops_layers.py - ИСПРАВЛЕННАЯ ВЕРСИЯ для управления слоями

import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, IntProperty
from .utils import active_obj
from .attrs import remove_color_attr

class MLD_OT_add_layer(Operator):
    bl_idname = "mld.add_layer"
    bl_label = "Add Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        s = obj.mld_settings
        L = s.layers.add()
        idx = len(s.layers)
        L.name = f"New Layer {idx}"
        L.mask_name = f"MLD_Mask_{idx}"
        
        # Set as active layer
        s.active_layer_index = idx - 1
        
        return {'FINISHED'}

class MLD_OT_remove_layer(Operator):
    bl_idname = "mld.remove_layer"
    bl_label = "Remove Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    layer_index: IntProperty(default=-1)
    
    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        s = obj.mld_settings
        
        # Use provided index or current active
        i = self.layer_index if self.layer_index >= 0 else s.active_layer_index
        
        if not (0 <= i < len(s.layers)):
            return {'CANCELLED'}
        
        # Get mask name before removing
        mask_name = getattr(s.layers[i], 'mask_name', '')
        
        # Remove the layer
        s.layers.remove(i)
        
        # Remove associated mask attribute
        if mask_name:
            try:
                remove_color_attr(obj.data, mask_name)
                print(f"[MLD] Removed mask attribute: {mask_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove mask {mask_name}: {e}")
        
        # Update active index
        if s.layers:
            s.active_layer_index = min(i, len(s.layers) - 1)
        else:
            s.active_layer_index = 0
            
        return {'FINISHED'}

class MLD_OT_move_layer(Operator):
    bl_idname = "mld.move_layer"
    bl_label = "Move Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    layer_index: IntProperty(default=-1)
    direction: EnumProperty(
        items=[('UP', 'Up', 'Move layer up'), ('DOWN', 'Down', 'Move layer down')],
        default='UP'
    )
    
    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
            
        s = obj.mld_settings
        
        # Use provided index or current active
        i = self.layer_index if self.layer_index >= 0 else s.active_layer_index
        
        if not (0 <= i < len(s.layers)):
            return {'CANCELLED'}
        
        # Calculate new position
        if self.direction == 'UP':
            new_i = i - 1
        else:  # DOWN
            new_i = i + 1
        
        # Check bounds
        if not (0 <= new_i < len(s.layers)):
            # Don't show error, just do nothing (UI should disable the button)
            return {'FINISHED'}
        
        # Perform the move
        try:
            s.layers.move(i, new_i)
            # Update active index to follow the moved layer
            s.active_layer_index = new_i
            
            direction_text = "up" if self.direction == 'UP' else "down"
            self.report({'INFO'}, f"Moved layer {direction_text}")
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to move layer: {e}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

# Register/Unregister
classes = (MLD_OT_add_layer, MLD_OT_remove_layer, MLD_OT_move_layer)

def register():
    for c in classes: 
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes): 
        bpy.utils.unregister_class(c)