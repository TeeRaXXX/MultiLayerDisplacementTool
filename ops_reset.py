# ops_reset.py — ИСПРАВЛЕННЫЕ reset операторы

import bpy
from bpy.types import Operator
from .constants import GN_MOD_NAME, SUBDIV_GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME
from .gn_multires import remove_multires_gn

class MLD_OT_reset_displacement(Operator):
    bl_idname = "mld.reset_displacement"
    bl_label = "Reset Displacement"
    bl_description = "Remove all displacement modifiers and carrier object"
    bl_options = {'UNDO'}
    
    def execute(self, ctx):
        obj = ctx.object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        print("[MLD] === RESET DISPLACEMENT START ===")
        
        # Remove multiresolution modifier specifically
        print("[MLD] Removing multiresolution modifiers...")
        remove_multires_gn(obj)
        
        # Remove other MLD modifiers
        mld_modifiers = [
            SUBDIV_GN_MOD_NAME, "MLD_Subdiv", "MLD_MultiresGN", "MLD_Multires",
            GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME
        ]
        
        for name in mld_modifiers:
            md = obj.modifiers.get(name)
            if md:
                try: 
                    obj.modifiers.remove(md)
                    print(f"[MLD] ✓ Removed modifier: {name}")
                except Exception as e:
                    print(f"[MLD] ⚠ Failed to remove modifier {name}: {e}")
                    
        # Remove carrier object
        cname = f"MLD_Carrier::{obj.name}"
        carr = bpy.data.objects.get(cname)
        if carr:
            try:
                me = carr.data
                bpy.data.objects.remove(carr, do_unlink=True)
                if me and me.users == 0:
                    bpy.data.meshes.remove(me, do_unlink=True)
                print(f"[MLD] ✓ Removed carrier: {cname}")
            except Exception as e:
                print(f"[MLD] ⚠ Failed to remove carrier: {e}")
        
        # Remove displacement attributes from object
        try:
            from .constants import OFFS_ATTR, ALPHA_PREFIX
            me = obj.data
            
            # Remove displacement vector attribute
            offs_attr = me.attributes.get(OFFS_ATTR)
            if offs_attr:
                try:
                    me.attributes.remove(offs_attr)
                    print(f"[MLD] ✓ Removed displacement attribute: {OFFS_ATTR}")
                except Exception as e:
                    print(f"[MLD] ⚠ Failed to remove {OFFS_ATTR}: {e}")
            
            # Remove alpha attributes
            removed_alphas = []
            for attr in list(me.attributes):
                if attr.name.startswith(ALPHA_PREFIX):
                    try:
                        me.attributes.remove(attr)
                        removed_alphas.append(attr.name)
                    except Exception:
                        pass
            
            if removed_alphas:
                print(f"[MLD] ✓ Removed alpha attributes: {removed_alphas}")
            
            me.update()
            
        except Exception as e:
            print(f"[MLD] ⚠ Failed to clean displacement attributes: {e}")
        
        # Force viewport update
        try:
            ctx.view_layer.update()
            for area in ctx.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        except Exception:
            pass
        
        print("[MLD] === RESET DISPLACEMENT COMPLETE ===")
        self.report({'INFO'}, "Displacement reset completed")
        return {'FINISHED'}

class MLD_OT_reset_layers(Operator):
    bl_idname = "mld.reset_layers"
    bl_label = "Reset Layers"
    bl_description = "Clear all layers and remove mask attributes"
    bl_options = {'UNDO'}
    
    def execute(self, ctx):
        obj = ctx.object
        s = getattr(obj, "mld_settings", None)
        if not s:
            return {'CANCELLED'}
        
        print("[MLD] === RESET LAYERS START ===")
        
        # Exit painting mode if active
        if getattr(s, 'is_painting', False) or getattr(s, 'painting', False):
            try:
                if obj.mode == 'VERTEX_PAINT':
                    bpy.ops.paint.vertex_paint_toggle()
                    print("[MLD] ✓ Exited vertex paint mode")
            except Exception:
                pass
        
        # Remove mask attributes
        try:
            from .ops_masks import cleanup_mask_attributes
            removed = cleanup_mask_attributes(obj)
            if removed:
                print(f"[MLD] ✓ Removed mask attributes: {removed}")
            else:
                print(f"[MLD] ○ No mask attributes to remove")
        except Exception as e:
            print(f"[MLD] ⚠ Failed to clean mask attributes: {e}")
            
        # Clear layers
        try:
            layer_count = len(s.layers)
            s.layers.clear()
            s.active_index = 0
            s.is_painting = False
            s.painting = False
            print(f"[MLD] ✓ Cleared {layer_count} layers")
        except Exception as e:
            print(f"[MLD] ⚠ Failed to clear layers: {e}")
        
        # Force UI update
        try:
            for area in ctx.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()
        except Exception:
            pass
        
        print("[MLD] === RESET LAYERS COMPLETE ===")
        self.report({'INFO'}, f"Layers reset completed")
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