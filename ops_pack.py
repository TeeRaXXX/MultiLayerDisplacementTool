# ops_pack.py - ИСПРАВЛЕННАЯ ВЕРСИЯ для Pack Vertex Colors

import bpy
from bpy.types import Operator
from .utils import active_obj
from .attrs import ensure_color_attr, color_attr_exists, loop_red
from .constants import PACK_ATTR

def _any_channel_assigned(s):
    """Check if any layer has a VC channel assigned."""
    return any(getattr(L, 'vc_channel', 'NONE') in {'R','G','B','A'} for L in s.layers)

def _pack_vc_now(obj, s):
    """Pack selected channels per-loop into object's vertex colors with proper error handling."""
    me = obj.data
    
    # Get or create the main vertex color layer for the object
    # Use the first available vertex color layer or create a new one
    vc_layer = None
    
    # Try to find existing vertex color layer
    if hasattr(me, "vertex_colors") and len(me.vertex_colors) > 0:
        # Use the first VC layer, or try to find one with a specific name
        for vc in me.vertex_colors:
            if vc.name == "MLD_Packed" or vc.name == "Col":
                vc_layer = vc
                break
        if not vc_layer:
            vc_layer = me.vertex_colors[0]  # Use first VC layer
        print(f"[MLD] Using existing vertex color layer: {vc_layer.name}")
    else:
        # Create new vertex color layer
        try:
            vc_layer = me.vertex_colors.new(name="MLD_Packed")
            print(f"[MLD] Created new vertex color layer: {vc_layer.name}")
        except Exception as e:
            print(f"[MLD] Failed to create vertex color layer: {e}")
            return False
    
    if not vc_layer:
        print("[MLD] No vertex color layer available")
        return False
    
    nloops = len(me.loops)
    
    # Build per-channel assignments
    chan_map = {'R': None, 'G': None, 'B': None, 'A': None}
    for i, L in enumerate(s.layers):
        ch = getattr(L, 'vc_channel', 'NONE')
        if ch in chan_map and chan_map[ch] is None:
            chan_map[ch] = i

    # Default fill value
    default_fill = 1.0 if getattr(s, 'fill_empty_vc_white', False) else 0.0
    
    # Build per-loop arrays
    per_loop = {
        'R': [default_fill] * nloops, 
        'G': [default_fill] * nloops, 
        'B': [default_fill] * nloops, 
        'A': [1.0] * nloops  # Alpha always 1.0
    }

    # Fill assigned channels from mask data
    for ch, layer_idx in chan_map.items():
        if layer_idx is None:
            continue  # Use default fill
            
        L = s.layers[layer_idx]
        mask_name = getattr(L, 'mask_name', '')
        
        if not mask_name or not color_attr_exists(me, mask_name):
            print(f"[MLD] Warning: Layer {layer_idx} channel {ch} has no mask: {mask_name}")
            continue
        
        # Read mask data (red channel)
        for li in range(nloops):
            try:
                mask_value = loop_red(me, mask_name, li)
                if mask_value is not None:
                    per_loop[ch][li] = float(mask_value)
            except Exception:
                pass

    # Write packed data to vertex color layer
    try:
        for li in range(nloops):
            r = per_loop['R'][li]
            g = per_loop['G'][li] 
            b = per_loop['B'][li]
            a = per_loop['A'][li]
            vc_layer.data[li].color = (r, g, b, a)
        
        me.update()
        return True
        
    except Exception as e:
        print(f"[MLD] Pack VC failed: {e}")
        return False

class MLD_OT_pack_vcols(Operator):
    bl_idname = "mld.pack_vcols"
    bl_label = "Pack Vertex Colors"
    bl_description = "Pack per-layer masks into object's vertex color channels R/G/B/A"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return False
        s = getattr(obj, 'mld_settings', None)
        return s and _any_channel_assigned(s)

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        s = obj.mld_settings
        
        # Check assignments
        if not _any_channel_assigned(s):
            self.report({'ERROR'}, "No VC channels assigned. Set channels in layer settings first.")
            return {'CANCELLED'}
        
        # Show what will be packed
        assignments = []
        for i, L in enumerate(s.layers):
            ch = getattr(L, 'vc_channel', 'NONE')
            if ch in ['R', 'G', 'B', 'A']:
                layer_name = getattr(L, 'name', f'Layer {i+1}')
                assignments.append(f"{ch}={layer_name}")
        
        print(f"[MLD] Packing masks to vertex colors: {', '.join(assignments)}")
        
        # Perform packing
        success = _pack_vc_now(obj, s)
        
        if success:
            # Mark as packed
            s.vc_packed = True
            
            # Get the vertex color layer name for reporting
            vc_layer_name = "vertex colors"
            if hasattr(obj.data, "vertex_colors") and len(obj.data.vertex_colors) > 0:
                vc_layer_name = obj.data.vertex_colors[0].name
            
            # Report success
            pack_info = ', '.join(assignments)
            self.report({'INFO'}, f"Packed to {vc_layer_name}: {pack_info}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to pack vertex colors.")
            return {'CANCELLED'}

# Register/Unregister
classes = (MLD_OT_pack_vcols,)

def register():
    for c in classes: 
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes): 
        bpy.utils.unregister_class(c)