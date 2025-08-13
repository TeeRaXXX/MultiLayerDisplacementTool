# Bake mesh: apply GN/Subdiv/Decimate, optionally pack VC, cleanup layer attrs
import bpy
from bpy.types import Operator
from .utils import active_obj, polycount, safe_mode
from .attrs import ensure_color_attr, color_attr_exists, loop_red
from .constants import PACK_ATTR, ALPHA_PREFIX, GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

def _any_channel_assigned(s):
    return any(L.vc_channel in {'R','G','B'} for L in s.layers)

def _pack_vc_now(obj, s):
    """Pack selected channels per-loop into object's vertex colors with proper error handling."""
    me = obj.data
    
    print(f"[MLD] Starting pack VC for object: {obj.name}")
    
    # Get or create the main vertex color layer for the object
    vc_layer = None
    vc_name = getattr(s, 'vc_attribute_name', 'Color')  # This will be set to bake_vc_attribute_name by the caller
    
    # First try to find existing vertex color layer
    if hasattr(me, "vertex_colors") and len(me.vertex_colors) > 0:
        for vc in me.vertex_colors:
            if vc.name == vc_name:
                vc_layer = vc
                print(f"[MLD] Using existing vertex color layer: {vc_layer.name}")
                break
    
    # If not found, try color_attributes
    if not vc_layer and hasattr(me, "color_attributes"):
        try:
            vc_layer = me.color_attributes.get(vc_name)
            if not vc_layer:
                vc_layer = me.color_attributes.new(name=vc_name, type='BYTE_COLOR', domain='CORNER')
                print(f"[MLD] Created new color attribute: {vc_layer.name}")
        except Exception as e:
            print(f"[MLD] Failed to create color attribute: {e}")
    
    # Fallback to vertex_colors
    if not vc_layer and hasattr(me, "vertex_colors"):
        try:
            vc_layer = me.vertex_colors.new(name=vc_name)
            print(f"[MLD] Created new vertex color layer: {vc_layer.name}")
        except Exception as e:
            print(f"[MLD] Failed to create vertex color layer: {e}")
    
    if not vc_layer:
        print("[MLD] No vertex color layer available")
        return False, None
    
    # Check if the VC layer name conflicts with any MLD mask attributes
    for L in s.layers:
        mask_name = getattr(L, 'mask_name', '')
        if mask_name and mask_name == vc_name:
            print(f"[MLD] Warning: VC layer name '{vc_name}' conflicts with layer mask '{mask_name}'")
            return False, None
    
    nloops = len(me.loops)
    
    # Build per-channel assignments
    chan_map = {'R': None, 'G': None, 'B': None}
    for i, L in enumerate(s.layers):
        ch = getattr(L, 'vc_channel', 'NONE')
        if ch in chan_map and chan_map[ch] is None:
            chan_map[ch] = i
    
    print(f"[MLD] Channel assignments: {chan_map}")

    # Default fill value
    default_fill = 1.0 if getattr(s, 'fill_empty_vc_white', False) else 0.0
    
    # Build per-loop arrays
    per_loop = {
        'R': [default_fill] * nloops, 
        'G': [default_fill] * nloops, 
        'B': [default_fill] * nloops
    }

    # Fill assigned channels from mask data
    for ch, layer_idx in chan_map.items():
        if layer_idx is None:
            continue
            
        L = s.layers[layer_idx]
        mask_name = getattr(L, 'mask_name', '')
        
        print(f"[MLD] Processing layer {layer_idx} channel {ch} with mask: {mask_name}")
        
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
        print(f"[MLD] Writing {nloops} loops to vertex color layer: {vc_layer.name}")
        
        # Определяем, какой API использовать для записи
        if hasattr(vc_layer, 'data'):
            # color_attributes или vertex_colors с .data
            for li in range(nloops):
                r = per_loop['R'][li]
                g = per_loop['G'][li] 
                b = per_loop['B'][li]
                vc_layer.data[li].color = (r, g, b, 1.0)  # Alpha always 1.0
        else:
            # Fallback если нет .data
            print(f"[MLD] Warning: vc_layer has no .data attribute")
            return False, None
        
        me.update()
        print(f"[MLD] Successfully packed to vertex color layer: {vc_layer.name}")
        return True, vc_layer.name  # Возвращаем success и имя слоя
        
    except Exception as e:
        print(f"[MLD] Pack VC failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def _cleanup_after_bake(obj, preserve_vc_name=None):
    me = obj.data
    removed_attrs = []
    
    # Remove MLD mask attributes (both color_attributes and vertex_colors)
    if hasattr(me, "color_attributes"):
        for a in list(me.color_attributes):
            try:
                if a.name.startswith("MLD_Mask_"):
                    attr_name = a.name  # Save name before removal
                    me.color_attributes.remove(a)
                    removed_attrs.append(f"color_attr:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove color attribute: {e}")
    
    if hasattr(me, "vertex_colors"):
        for a in list(me.vertex_colors):
            try:
                if a.name.startswith("MLD_Mask_"):
                    attr_name = a.name  # Save name before removal
                    me.vertex_colors.remove(a)
                    removed_attrs.append(f"vertex_color:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove vertex color: {e}")
    
    # Remove any other attributes that might conflict with the packed VC attribute
    # (but preserve the packed VC attribute if specified)
    if hasattr(me, "color_attributes"):
        for a in list(me.color_attributes):
            try:
                # Skip if this is the packed VC attribute we want to preserve
                if preserve_vc_name and a.name == preserve_vc_name:
                    print(f"[MLD] Skipping removal of preserved VC attribute: {a.name}")
                    continue
                    
                # Remove other MLD-related attributes that might conflict
                if a.name.startswith("MLD_") or a.name == "Color":
                    attr_name = a.name  # Save name before removal
                    me.color_attributes.remove(a)
                    removed_attrs.append(f"other_attr:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove other attribute: {e}")
    
    if hasattr(me, "vertex_colors"):
        for a in list(me.vertex_colors):
            try:
                # Skip if this is the packed VC attribute we want to preserve
                if preserve_vc_name and a.name == preserve_vc_name:
                    print(f"[MLD] Skipping removal of preserved VC attribute: {a.name}")
                    continue
                    
                # Remove other MLD-related attributes that might conflict
                if a.name.startswith("MLD_") or a.name == "Color":
                    attr_name = a.name  # Save name before removal
                    me.vertex_colors.remove(a)
                    removed_attrs.append(f"other_vc:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove other vertex color: {e}")
    
    # Remove MLD displacement attributes
    if hasattr(me, "attributes"):
        for a in list(me.attributes):
            try:
                if a.name.startswith("MLD_") and a.data_type == 'FLOAT_VECTOR':
                    attr_name = a.name  # Save name before removal
                    me.attributes.remove(a)
                    removed_attrs.append(f"displacement:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove displacement attribute: {e}")
    
    # Remove alpha attributes (if somehow present on object)
    if hasattr(me, "attributes"):
        for a in list(me.attributes):
            try:
                if a.name.startswith(ALPHA_PREFIX):
                    attr_name = a.name  # Save name before removal
                    me.attributes.remove(a)
                    removed_attrs.append(f"alpha:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove alpha attribute: {e}")
    
    # Remove MLD_Pack attribute if it exists (from old implementation)
    if hasattr(me, "color_attributes"):
        pack_attr = me.color_attributes.get(PACK_ATTR)
        if pack_attr:
            try:
                attr_name = pack_attr.name  # Save name before removal
                me.color_attributes.remove(pack_attr)
                removed_attrs.append(f"pack_attr:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove pack attribute: {e}")
    
    if hasattr(me, "vertex_colors"):
        pack_vc = me.vertex_colors.get(PACK_ATTR)
        if pack_vc:
            try:
                attr_name = pack_vc.name  # Save name before removal
                me.vertex_colors.remove(pack_vc)
                removed_attrs.append(f"pack_vc:{attr_name}")
            except Exception as e:
                print(f"[MLD] Failed to remove pack vertex color: {e}")
    
    # Preserve the packed VC attribute if specified
    if preserve_vc_name:
        print(f"[MLD] Preserving packed VC attribute: {preserve_vc_name}")
    
    me.update()
    
    if removed_attrs:
        print(f"[MLD] Cleaned up attributes: {', '.join(removed_attrs)}")
    else:
        print("[MLD] No MLD attributes found to clean up")

class MLD_OT_bake_mesh(Operator):
    bl_idname = "mld.bake_mesh"
    bl_label = "Bake Mesh"
    bl_description = "Apply Subdiv/GN/Decimate, pack masks to vertex colors if channels assigned, remove layer attributes and carrier, clear settings"

    def execute(self, context):
        obj=active_obj(context)
        if not obj or obj.type!='MESH': return {'CANCELLED'}
        s=obj.mld_settings
        
        # Check if pack VC is enabled but no channels are assigned
        if getattr(s, "bake_pack_vc", False) and not _any_channel_assigned(s):
            self.report({'ERROR'}, "Pack to Vertex Colors is enabled but no VC channels are assigned. Please assign channels in layer settings first.")
            return {'CANCELLED'}

        # STEP 1: Create preview material FIRST (before any modifications) - ONLY if pack to VC is enabled
        preview_material_created = False
        if getattr(s, "bake_pack_vc", False) and getattr(s, "preview_enable", False):
            try:
                from .materials import build_heightlerp_preview_shader
                print("[MLD] Creating preview material before bake (pack to VC enabled)...")
                mat = build_heightlerp_preview_shader(
                    obj, s,
                    preview_influence=getattr(s, "preview_mask_influence", 1.0),
                    preview_contrast=getattr(s, "preview_contrast", 1.0),
                )
                if mat:
                    preview_material_created = True
                    print(f"[MLD] Preview material created: {mat.name}")
                    
                    # Ensure material is assigned to object
                    if len(obj.data.materials) == 0:
                        obj.data.materials.append(mat)
                    else:
                        obj.data.materials[0] = mat
                    
                    # Ensure all polygons use this material
                    for poly in obj.data.polygons:
                        poly.material_index = 0
                    
                    obj.data.update()
                    print(f"[MLD] Preview material '{mat.name}' assigned to all {len(obj.data.polygons)} polygons")
                else:
                    print("[MLD] Failed to create preview material")
            except Exception as e:
                print(f"[MLD] Failed to create preview material: {e}")
                import traceback
                traceback.print_exc()

        # STEP 2: Pack VC if enabled and any channel assigned (before removing attributes)
        vc_packed = False
        packed_vc_name = None
        if getattr(s, "bake_pack_vc", False) and _any_channel_assigned(s):
            # Check for attribute name conflicts
            bake_vc_name = getattr(s, "bake_vc_attribute_name", "Color")
            conflict_found = False
            
            # Check if the bake VC name conflicts with any existing MLD mask attributes
            for L in s.layers:
                mask_name = getattr(L, 'mask_name', '')
                if mask_name and mask_name == bake_vc_name:
                    conflict_found = True
                    self.report({'ERROR'}, f"VC attribute name '{bake_vc_name}' conflicts with layer mask '{mask_name}'. Please use a different name.")
                    return {'CANCELLED'}
            
            if not conflict_found:
                # Temporarily set the VC attribute name for packing
                original_vc_name = getattr(s, 'vc_attribute_name', 'Color')
                s.vc_attribute_name = bake_vc_name
                
                success, vc_layer_name = _pack_vc_now(obj, s)
                
                # Restore original VC attribute name
                s.vc_attribute_name = original_vc_name
                
                if success:
                    vc_packed = True
                    packed_vc_name = vc_layer_name
                    s.vc_packed = True
                    s.vc_attribute_name = bake_vc_name  # Keep the bake name for the shader

        prev = safe_mode(obj, 'OBJECT')

        # STEP 3: Apply modifiers in order: Subdiv -> GN -> Decimate
        # Handle both new Geometry Nodes subdivision and fallback subdivision
        subdiv_modifiers = ["MLD_SubdivGN", "MLD_Subdiv", SUBDIV_MOD_NAME]  # Try all possible names
        for subdiv_name in subdiv_modifiers:
            md = obj.modifiers.get(subdiv_name)
            if md:
                try:
                    bpy.ops.object.modifier_apply(modifier=subdiv_name)
                    print(f"[MLD] Applied subdivision modifier: {subdiv_name}")
                    break
                except Exception as e:
                    print(f"[MLD] Failed to apply {subdiv_name}: {e}")
        
        # Apply other modifiers
        for name in (GN_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try:
                    bpy.ops.object.modifier_apply(modifier=name)
                    print(f"[MLD] Applied modifier: {name}")
                except Exception as e:
                    print(f"[MLD] Failed to apply {name}: {e}")
        
        # Verify that preview material is still assigned after modifiers
        if preview_material_created and len(obj.data.materials) > 0:
            mat = obj.data.materials[0]
            if mat and mat.name.startswith("MLD_Preview::"):
                print(f"[MLD] Preview material '{mat.name}' preserved after modifiers")
            else:
                print(f"[MLD] Warning: Preview material may have been lost after modifiers")

        # STEP 4: Remove carrier object
        cname=f"MLD_Carrier::{obj.name}"
        carr=bpy.data.objects.get(cname)
        if carr:
            try:
                me=carr.data
                bpy.data.objects.remove(carr, do_unlink=True)
                if me and me.users==0:
                    bpy.data.meshes.remove(me, do_unlink=True)
            except Exception: pass

        # STEP 5: Apply packed VC shader if VC was packed (overrides preview material)
        if vc_packed:
            try:
                from .materials import build_packed_vc_preview_shader
                mat = build_packed_vc_preview_shader(obj, s)
                if mat:
                    print(f"[MLD] Applied packed VC shader after bake: {mat.name}")
                    
                    # Ensure material is assigned to object (overrides preview material)
                    if len(obj.data.materials) == 0:
                        obj.data.materials.append(mat)
                    else:
                        obj.data.materials[0] = mat
                    
                    # Ensure all polygons use this material
                    for poly in obj.data.polygons:
                        poly.material_index = 0
                    
                    obj.data.update()
                    print(f"[MLD] Packed VC material '{mat.name}' assigned to all {len(obj.data.polygons)} polygons")
                    
                    # Update preview_material_created flag since we now have a different material
                    preview_material_created = False
                else:
                    print(f"[MLD] Failed to create packed VC shader")
            except Exception as e:
                print(f"[MLD] Failed to apply packed VC shader: {e}")
                import traceback
                traceback.print_exc()

        # STEP 6: Cleanup attributes AFTER materials are created
        _cleanup_after_bake(obj, preserve_vc_name=packed_vc_name if vc_packed else None)
        
        # Verify that material is still working after cleanup
        if len(obj.data.materials) > 0:
            mat = obj.data.materials[0]
            if mat:
                print(f"[MLD] Final material after cleanup: '{mat.name}'")
                if mat.name.startswith("MLD_Preview::") or mat.name.startswith("MLD_PackedVC::"):
                    print(f"[MLD] ✓ Material should work correctly after attribute cleanup")
                else:
                    print(f"[MLD] ⚠ Material may not be MLD preview material")
            else:
                print(f"[MLD] ⚠ No material assigned after cleanup")
        else:
            print(f"[MLD] ⚠ No materials found after cleanup")

        # clear settings (layers etc.) - но сохраняем информацию о VC
        vc_attr_name = getattr(s, 'vc_attribute_name', 'Color')  # Сохраняем имя атрибута
        s.layers.clear()
        s.is_painting=False
        # НЕ сбрасываем vc_packed и vc_attribute_name, чтобы шейдер мог их использовать
        # s.vc_packed остается True если был packed
        s.vc_attribute_name = vc_attr_name  # Восстанавливаем имя

        # refresh stats
        v,f,t = polycount(obj.data)
        s.last_poly_v, s.last_poly_f, s.last_poly_t = v,f,t

        safe_mode(obj, prev)
        
        # Force viewport update to show new material
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                    # Force shading mode update
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            # Переключаем на Material Preview если был Solid
                            if space.shading.type == 'SOLID':
                                space.shading.type = 'MATERIAL'
        except Exception:
            pass
        
        # Report success with details
        if vc_packed and packed_vc_name:
            self.report({'INFO'}, f"Baked mesh with vertex colors packed to '{packed_vc_name}' and shader applied.")
        elif preview_material_created:
            self.report({'INFO'}, "Baked mesh with preview material created.")
        else:
            self.report({'INFO'}, "Baked mesh.")
        return {'FINISHED'}

classes=(MLD_OT_bake_mesh,)
def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)