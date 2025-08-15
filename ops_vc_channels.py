# Choose/clear per-layer Vertex Color channels (R/G/B/A)
import bpy
from bpy.types import Operator
from bpy.props import IntProperty, EnumProperty
from .utils import active_obj

class MLD_OT_set_layer_channel(Operator):
    bl_idname = "mld.set_layer_channel"
    bl_label = "Set VC channel"
    bl_description = "Assign a Vertex Color channel (R/G/B/A) to this layer for packing"

    layer_index: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=160)

    def draw(self, context):
        layout=self.layout
        obj=active_obj(context); s=obj.mld_settings
        used=set([x.vc_channel for x in s.layers if x.vc_channel in {'R','G','B','A'}])
        current_channel = s.layers[self.layer_index].vc_channel if 0 <= self.layer_index < len(s.layers) else 'NONE'
        
        col=layout.column()
        
        # Always show NONE option to clear the channel
        row=col.row()
        op=row.operator("mld._apply_layer_channel", text="None (Clear)")
        op.layer_index=self.layer_index; op.channel='NONE'
        
        # Show available channels (excluding current channel)
        any_drawn=False
        for ch in ('R','G','B','A'):
            if ch in used or ch == current_channel: continue
            any_drawn=True
            row=col.row()
            op=row.operator("mld._apply_layer_channel", text=f"Use {ch}")
            op.layer_index=self.layer_index; op.channel=ch
        
        if not any_drawn:
            layout.label(text="All channels are taken.")

    def execute(self, context):
        return {'FINISHED'}

class MLD_OT__apply_layer_channel(Operator):
    bl_idname = "mld._apply_layer_channel"
    bl_label = "Apply VC channel"
    layer_index: IntProperty()
    channel: EnumProperty(items=[('NONE','NONE',''),('R','R',''),('G','G',''),('B','B',''),('A','A','')])

    def execute(self, context):
        obj=active_obj(context); s=obj.mld_settings
        if 0<=self.layer_index<len(s.layers):
            s.layers[self.layer_index].vc_channel=self.channel
        # Force UI update
        context.area.tag_redraw()
        return {'FINISHED'}

classes=(MLD_OT_set_layer_channel, MLD_OT__apply_layer_channel)

def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
