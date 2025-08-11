# Copy/Paste settings & layers (without masks/attributes)
import bpy
from bpy.types import Operator
from .utils import active_obj

_SETTINGS_CLIPBOARD = None

def _serialize_settings(obj):
    s=obj.mld_settings
    data = dict(
        strength=s.strength, midlevel=s.midlevel, fill_power=s.fill_power,
        refine_enable=s.refine_enable, subdiv_type=s.subdiv_type,
        subdiv_levels_view=s.subdiv_levels_view, subdiv_levels_render=s.subdiv_levels_render,
        decimate_enable=s.decimate_enable, decimate_ratio=s.decimate_ratio,
        auto_assign_materials=s.auto_assign_materials, mat_assign_threshold=s.mat_assign_threshold,
        preview_blend=s.preview_blend, preview_mask_influence=s.preview_mask_influence,
        layers=[]
    )
    for L in s.layers:
        data["layers"].append(dict(
            name=L.name,
            material=L.material.name if L.material else None,
            multiplier=L.multiplier, bias=L.bias, tiling=L.tiling,
            enabled=L.enabled,
            vc_channel=L.vc_channel,
        ))
    return data

def _apply_settings(obj, data):
    s=obj.mld_settings
    # globals
    s.strength = data.get('strength', s.strength)
    s.midlevel = data.get('midlevel', s.midlevel)
    s.fill_power = data.get('fill_power', s.fill_power)
    s.refine_enable = data.get('refine_enable', s.refine_enable)
    s.subdiv_type = data.get('subdiv_type', s.subdiv_type)
    s.subdiv_levels_view = data.get('subdiv_levels_view', s.subdiv_levels_view)
    s.subdiv_levels_render = data.get('subdiv_levels_render', s.subdiv_levels_render)
    s.decimate_enable = data.get('decimate_enable', s.decimate_enable)
    s.decimate_ratio = data.get('decimate_ratio', s.decimate_ratio)
    s.auto_assign_materials = data.get('auto_assign_materials', s.auto_assign_materials)
    s.mat_assign_threshold = data.get('mat_assign_threshold', s.mat_assign_threshold)
    s.preview_blend = data.get('preview_blend', s.preview_blend)
    s.preview_mask_influence = data.get('preview_mask_influence', s.preview_mask_influence)

    # layers
    s.layers.clear()
    for i, LD in enumerate(data.get("layers", []), start=1):
        L=s.layers.add()
        L.name = LD.get("name") or f"New Layer {i}"
        mat_name = LD.get("material")
        L.material = bpy.data.materials.get(mat_name) if mat_name else None
        L.multiplier = LD.get("multiplier", 1.0)
        L.bias = LD.get("bias", 0.0)
        L.tiling = LD.get("tiling", 1.0)
        L.enabled = LD.get("enabled", True)
        L.vc_channel = LD.get("vc_channel", 'NONE')
        L.mask_name = f"MLD_Mask_{i}"  # new mask attr name; not created here
    s.active_layer_index = max(0, len(s.layers)-1)

class MLD_OT_copy_settings(Operator):
    bl_idname = "mld.copy_settings"
    bl_label = "Copy Settings"
    bl_description = "Copy all MLD settings and layers (without masks/attributes) to clipboard"

    def execute(self, context):
        global _SETTINGS_CLIPBOARD
        obj=active_obj(context)
        if not obj or obj.type!='MESH': return {'CANCELLED'}
        _SETTINGS_CLIPBOARD = _serialize_settings(obj)
        self.report({'INFO'}, "Settings copied")
        return {'FINISHED'}

class MLD_OT_paste_settings(Operator):
    bl_idname = "mld.paste_settings"
    bl_label = "Paste Settings"
    bl_description = "Paste previously copied MLD settings and layers to current object"

    def execute(self, context):
        global _SETTINGS_CLIPBOARD
        obj=active_obj(context)
        if not obj or obj.type!='MESH' or not _SETTINGS_CLIPBOARD:
            return {'CANCELLED'}
        _apply_settings(obj, _SETTINGS_CLIPBOARD)
        self.report({'INFO'}, "Settings pasted")
        return {'FINISHED'}

def _clipboard_has_data():
    return _SETTINGS_CLIPBOARD is not None

classes=(MLD_OT_copy_settings, MLD_OT_paste_settings)

def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)

# expose helper to UI
has_settings_clipboard = _clipboard_has_data
