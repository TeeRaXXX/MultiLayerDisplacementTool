# ops_pipeline.py — CARRIER-BASED ПОДХОД: displacement на subdivided mesh

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill
from .materials import build_heightlerp_preview_shader
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME, OFFS_ATTR
from .carrier import ensure_carrier, sync_carrier_mesh

def _ensure_subdiv(obj: bpy.types.Object, s):
    """Create/update subdivision modifier."""
    md = obj.modifiers.get(SUBDIV_MOD_NAME)
    
    if getattr(s, "subdiv_enable", True):
        if not md or md.type != 'SUBSURF':
            if md:
                try:
                    obj.modifiers.remove(md)
                except Exception:
                    pass
            md = obj.modifiers.new(SUBDIV_MOD_NAME, 'SUBSURF')
        
        try:
            subdiv_type = getattr(s, "subdiv_type", 'SIMPLE')
            if hasattr(md, 'subdivision_type'):
                md.subdivision_type = subdiv_type
            
            viewport_levels = int(getattr(s, "subdiv_view", 1))
            if hasattr(md, 'levels'):
                md.levels = max(0, min(6, viewport_levels))
            
            render_levels = int(getattr(s, "subdiv_render", 1))
            if hasattr(md, 'render_levels'):
                md.render_levels = max(0, min(6, render_levels))
            
            if hasattr(md, 'use_limit_surface'):
                md.use_limit_surface = False
                
            print(f"[MLD] Subdiv configured: type={subdiv_type}, viewport={viewport_levels}, render={render_levels}")
            
        except Exception as e:
            print(f"[MLD] Failed to configure subdiv modifier: {e}")
        
        return md
    else:
        if md:
            try: 
                obj.modifiers.remove(md)
                print(f"[MLD] Removed subdivision modifier")
            except Exception:
                pass
        return None

def _get_subdivided_mesh(obj: bpy.types.Object, context) -> bpy.types.Mesh:
    """Get mesh with ONLY subdivision applied."""
    try:
        # Временно отключим все модификаторы кроме subdivision
        modifiers_states = []
        for mod in obj.modifiers:
            modifiers_states.append((mod.name, mod.show_viewport))
            if mod.name != SUBDIV_MOD_NAME:
                mod.show_viewport = False
        
        # Получим evaluated mesh с только subdivision
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_subdivided = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        
        # Восстановим состояния модификаторов
        for mod_name, show_state in modifiers_states:
            mod = obj.modifiers.get(mod_name)
            if mod:
                mod.show_viewport = show_state
        
        print(f"[MLD] Got subdivided mesh: {len(mesh_subdivided.vertices)} verts (from {len(obj.data.vertices)} original)")
        return mesh_subdivided
        
    except Exception as e:
        print(f"[MLD] Failed to get subdivided mesh: {e}")
        return None

def _write_displacement_to_carrier(obj: bpy.types.Object, carrier, subdivided_mesh, per_vert_displacement):
    """Write displacement data directly to carrier mesh attributes."""
    try:
        # Обновим carrier mesh с subdivided топологией
        sync_carrier_mesh(carrier, subdivided_mesh)
        
        # Убедимся что у carrier есть OFFS атрибут
        carrier_mesh = carrier.data
        offs_attr = carrier_mesh.attributes.get(OFFS_ATTR)
        if not offs_attr:
            offs_attr = carrier_mesh.attributes.new(name=OFFS_ATTR, type='FLOAT_VECTOR', domain='POINT')
        
        # Записываем displacement напрямую в carrier
        for vi, displacement in enumerate(per_vert_displacement):
            if vi < len(offs_attr.data):
                offs_attr.data[vi].vector = (0.0, 0.0, displacement)  # Z = scalar displacement
        
        carrier_mesh.update()
        print(f"[MLD] Wrote displacement to carrier: {len(per_vert_displacement)} values")
        return True
        
    except Exception as e:
        print(f"[MLD] Failed to write displacement to carrier: {e}")
        return False

def _ensure_gn_modifier(obj: bpy.types.Object):
    """Ensure GN modifier exists and reads from carrier."""
    try:
        from .gn import ensure_gn
        md = ensure_gn(obj)
        
        # Важно: GN должен читать данные из carrier mesh через Object Info node
        # Это требует модификации GN графа для работы с carrier
        
        return md is not None
    except Exception as e:
        print(f"[MLD] Failed to create GN modifier: {e}")
        return False

def _ensure_decimate(obj: bpy.types.Object, s):
    """Create decimate modifier after GN."""
    md = obj.modifiers.get(DECIMATE_MOD_NAME)
    
    if getattr(s, "decimate_enable", False):
        if not md or md.type != 'DECIMATE':
            if md:
                try:
                    obj.modifiers.remove(md)
                except Exception:
                    pass
            md = obj.modifiers.new(DECIMATE_MOD_NAME, 'DECIMATE')
        
        try:
            if hasattr(md, 'decimate_type'):
                md.decimate_type = 'COLLAPSE'
            
            ratio = float(getattr(s, "decimate_ratio", 0.5))
            if hasattr(md, 'ratio'):
                md.ratio = max(0.0, min(1.0, ratio))
            
            if hasattr(md, 'use_collapse_triangulate'):
                md.use_collapse_triangulate = False
                
            print(f"[MLD] Decimate configured: ratio={ratio}")
            
        except Exception as e:
            print(f"[MLD] Failed to configure decimate modifier: {e}")
        
        # Убедимся что decimate после GN
        try:
            gn = obj.modifiers.get(GN_MOD_NAME)
            if gn:
                gn_idx = obj.modifiers.find(gn.name)
                decimate_idx = obj.modifiers.find(DECIMATE_MOD_NAME)
                
                while decimate_idx <= gn_idx and decimate_idx < len(obj.modifiers) - 1:
                    bpy.ops.object.modifier_move_down(modifier=DECIMATE_MOD_NAME)
                    decimate_idx += 1
        except Exception as e:
            print(f"[MLD] Failed to reorder decimate: {e}")
        
        return md
    else:
        if md:
            try: 
                obj.modifiers.remove(md)
                print(f"[MLD] Removed decimate modifier")
            except Exception:
                pass
        return None

class MLD_OT_recalculate(bpy.types.Operator):
    bl_idname = "mld.recalculate"
    bl_label = "Recalculate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}

        s = getattr(obj, "mld_settings", None)
        if s is None:
            self.report({'ERROR'}, "No MLD settings found.")
            return {'CANCELLED'}

        if len(s.layers) == 0:
            self.report({'WARNING'}, "No layers to process.")
            return {'CANCELLED'}

        # Ensure Object mode
        try:
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        print("[MLD] === CARRIER-BASED RECALCULATE START ===")
        
        # STEP 1: Setup subdivision modifier
        subdiv_md = None
        try:
            subdiv_md = _ensure_subdiv(obj, s)
            if subdiv_md:
                print(f"[MLD] ✓ Subdivision modifier ready: {subdiv_md.levels} levels")
            else:
                print("[MLD] ○ Subdivision: disabled")
        except Exception as e:
            print(f"[MLD] ✗ Subdiv setup failed: {e}")

        # STEP 2: Force depsgraph update
        try:
            context.view_layer.update()
            print("[MLD] ✓ Dependency graph updated")
        except Exception as e:
            print(f"[MLD] Warning: depsgraph update failed: {e}")

        # STEP 3: Get subdivided mesh
        subdivided_mesh = None
        if subdiv_md:
            subdivided_mesh = _get_subdivided_mesh(obj, context)
        
        # Use subdivided or original mesh for heightfill
        work_mesh = subdivided_mesh if subdivided_mesh else obj.data
        print(f"[MLD] Using work mesh: {len(work_mesh.vertices)} vertices")

        # STEP 4: Create carrier for subdivided topology
        try:
            carrier = ensure_carrier(obj)
            print(f"[MLD] ✓ Carrier created: {carrier.name}")
        except Exception as e:
            print(f"[MLD] ✗ Carrier creation failed: {e}")
            return {'CANCELLED'}

        # STEP 5: Compute heightfill on work mesh
        print("[MLD] Computing heightfill on work mesh...")
        try:
            # Модифицируем solve_heightfill чтобы он возвращал per-vertex displacement
            displacement_result = solve_heightfill_for_carrier(obj, s, context, work_mesh)
            if not displacement_result:
                raise Exception("Heightfill returned no data")
            
            print(f"[MLD] ✓ Heightfill computed: {len(displacement_result)} displacement values")
            
        except Exception as e:
            print(f"[MLD] ✗ solve_heightfill failed: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, "Height solve failed (check UV and height maps).")
            return {'CANCELLED'}

        # STEP 6: Write displacement to carrier
        try:
            success = _write_displacement_to_carrier(obj, carrier, work_mesh, displacement_result)
            if not success:
                raise Exception("Failed to write displacement to carrier")
            print("[MLD] ✓ Displacement written to carrier")
            
        except Exception as e:
            print(f"[MLD] ✗ Carrier write failed: {e}")
            return {'CANCELLED'}

        # STEP 7: Setup GN modifier to read from carrier
        print("[MLD] Setting up Geometry Nodes...")
        try:
            gn_ok = _ensure_gn_modifier(obj)
            if not gn_ok:
                raise Exception("Failed to create GN modifier")
            
            # Убедимся что GN после subdivision
            if subdiv_md:
                gn_md = obj.modifiers.get(GN_MOD_NAME)
                subdiv_idx = obj.modifiers.find(SUBDIV_MOD_NAME)
                gn_idx = obj.modifiers.find(GN_MOD_NAME)
                
                while gn_idx <= subdiv_idx and gn_idx < len(obj.modifiers) - 1:
                    bpy.ops.object.modifier_move_down(modifier=GN_MOD_NAME)
                    gn_idx += 1
                print("[MLD] ✓ GN positioned after subdivision")
            
            print("[MLD] ✓ Geometry Nodes displacement ready")
            
        except Exception as e:
            print(f"[MLD] ✗ GN setup failed: {e}")
            self.report({'ERROR'}, f"GN setup failed: {e}")
            return {'CANCELLED'}

        # STEP 8: Setup decimate
        try:
            decimate_md = _ensure_decimate(obj, s)
            if decimate_md:
                print(f"[MLD] ✓ Decimate: {decimate_md.ratio} ratio")
                
                # ВАЖНО: Принудительное обновление после decimate
                try:
                    context.view_layer.update()
                    print("[MLD] ✓ Dependency graph updated after decimate")
                except Exception as e:
                    print(f"[MLD] Warning: decimate depsgraph update failed: {e}")
            else:
                print("[MLD] ○ Decimate: disabled")
        except Exception as e:
            print(f"[MLD] ✗ Decimate setup failed: {e}")

        # STEP 9: Auto-assign materials
        try:
            if getattr(s, "auto_assign_materials", False):
                print("[MLD] Auto-assigning materials...")
                # Для carrier-based нужно использовать carrier данные
                # bpy.ops.mld.assign_materials_from_disp()
                print("[MLD] ○ Material assignment skipped (needs carrier support)")
        except Exception as e:
            print(f"[MLD] ✗ Auto assign failed: {e}")

        # STEP 10: Build preview material
        try:
            if getattr(s, "preview_enable", False):
                print("[MLD] Building preview material...")
                build_heightlerp_preview_shader(
                    obj, s,
                    preview_influence=getattr(s, "preview_mask_influence", 1.0),
                    preview_contrast=getattr(s, "preview_contrast", 1.0),
                )
                print("[MLD] ✓ Preview material built")
        except Exception as e:
            print(f"[MLD] ✗ Preview build failed: {e}")

        # STEP 11: Cleanup
        if subdivided_mesh:
            try:
                bpy.data.meshes.remove(subdivided_mesh, do_unlink=True)
                print("[MLD] ✓ Cleaned up subdivided mesh")
            except Exception:
                pass

        # Final polycount reporting with decimate info
        try:
            from .utils import polycount, get_evaluated_polycount, get_polycount_up_to_modifier, format_polycount
            
            print("\n[MLD] === POLYCOUNT SUMMARY ===")
            
            # Original mesh
            orig_v, orig_f, orig_t = polycount(obj.data)
            print(f"[MLD] Original mesh: {format_polycount(orig_v, orig_f, orig_t)}")
            
            # After subdivision (if enabled)
            if subdiv_md:
                subdiv_v, subdiv_f, subdiv_t = get_polycount_up_to_modifier(obj, GN_MOD_NAME, context)
                print(f"[MLD] After subdivision: {format_polycount(subdiv_v, subdiv_f, subdiv_t)} ({subdiv_t/orig_t:.1f}x)")
            
            # After displacement (before decimate)
            if decimate_md:
                before_decimate_v, before_decimate_f, before_decimate_t = get_polycount_up_to_modifier(obj, DECIMATE_MOD_NAME, context)
                print(f"[MLD] Before decimate: {format_polycount(before_decimate_v, before_decimate_f, before_decimate_t)}")
            
            # Final result (all modifiers)
            final_v, final_f, final_t = get_evaluated_polycount(obj, context)
            print(f"[MLD] Final result: {format_polycount(final_v, final_f, final_t)}")
            
            if decimate_md:
                reduction = (1.0 - final_t/before_decimate_t) * 100
                print(f"[MLD] Decimate reduction: {reduction:.1f}% ({before_decimate_t:,} → {final_t:,} tris)")
            
            # Update settings with latest polycount for UI
            try:
                s.last_poly_v, s.last_poly_f, s.last_poly_t = final_v, final_f, final_t
            except Exception:
                pass
                
            print("[MLD] === END POLYCOUNT ===\n")
            
        except Exception as e:
            print(f"[MLD] Polycount reporting failed: {e}")

        # Final modifier stack
        try:
            mod_names = [f"{m.name}({m.type})" for m in obj.modifiers]
            print(f"[MLD] Final modifier stack: {' → '.join(mod_names)}")
        except Exception:
            pass

        # Force final viewport update and polycount refresh
        try:
            # Final depsgraph update to ensure all changes are applied
            context.view_layer.update()
            
            # Force UI refresh
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                elif area.type == 'PROPERTIES':
                    area.tag_redraw()
        except Exception:
            pass

        print("[MLD] === CARRIER-BASED RECALCULATE COMPLETE ===")
        self.report({'INFO'}, "Displacement calculated on subdivided mesh via carrier.")
        return {'FINISHED'}


def solve_heightfill_for_carrier(obj: bpy.types.Object, s, context, work_mesh: bpy.types.Mesh):
    """
    Heightfill variant that returns per-vertex displacement values for carrier.
    """
    try:
        from .sampling import (
            make_sampler, find_image_and_uv_from_displacement,
            active_uv_layer_name, sample_height_at_loop,
        )
        from .attrs import point_red, loop_red, color_attr_exists
        
        # UV layer
        uv_name = active_uv_layer_name(work_mesh)
        if not uv_name:
            uv_name = active_uv_layer_name(obj.data)
        if not uv_name:
            print("[MLD] Error: No UV layer found")
            return None

        # samplers per layer
        samplers = []
        for L in s.layers:
            if not (L.enabled and L.material):
                samplers.append(None)
                continue
            img, _ = find_image_and_uv_from_displacement(L.material)
            samplers.append(make_sampler(img))

        if not any(samplers):
            print("[MLD] Error: No valid samplers found")
            return None

        n_layers = len(s.layers)
        vcount = len(work_mesh.vertices)
        
        # Displacement accumulator
        per_vertex_displacement = [0.0] * vcount
        
        print(f"[MLD] Processing {len(work_mesh.polygons)} polygons for carrier...")

        # Process each polygon
        for poly in work_mesh.polygons:
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                vi = work_mesh.loops[li].vertex_index

                # Collect per-layer heights and masks
                h_layer = [0.0] * n_layers
                m_layer = [0.0] * n_layers
                
                for i, L in enumerate(s.layers):
                    if not L.enabled:
                        continue
                    
                    # Mask from original mesh
                    m = 0.0
                    if L.mask_name and color_attr_exists(obj.data, L.mask_name):
                        orig_li = li % len(obj.data.loops) if len(obj.data.loops) > 0 else 0
                        orig_li = min(orig_li, len(obj.data.loops) - 1)
                        
                        m = loop_red(obj.data, L.mask_name, orig_li)
                        if m is None:
                            orig_vi = vi % len(obj.data.vertices) if len(obj.data.vertices) > 0 else 0
                            orig_vi = min(orig_vi, len(obj.data.vertices) - 1)
                            m = point_red(obj.data, L.mask_name, orig_vi) or 0.0
                    m_layer[i] = m

                    # Height from work mesh
                    smp = samplers[i]
                    if smp is None:
                        continue
                    h = sample_height_at_loop(work_mesh, uv_name, li, max(1e-8, L.tiling), smp)
                    h = h * L.multiplier + L.bias
                    h_layer[i] = h

                # HeightFill blend
                filled_h = 0.0
                remain = 1.0
                
                for i, L in enumerate(s.layers):
                    m = m_layer[i]
                    if m <= 0.0:
                        continue
                    if m >= 0.9999:
                        filled_h = h_layer[i]
                        remain = 0.0
                    else:
                        contrib = max(0.0, h_layer[i] - filled_h)
                        gain = contrib * m * s.fill_power
                        if gain > 0.0:
                            filled_h = filled_h + gain
                            remain = max(0.0, 1.0 - remain)

                # Add to vertex displacement
                displacement = (filled_h - s.midlevel) * s.strength
                per_vertex_displacement[vi] += displacement

        # Average by vertex valence
        valence = [0] * vcount
        for p in work_mesh.polygons:
            for li in range(p.loop_start, p.loop_start + p.loop_total):
                vi = work_mesh.loops[li].vertex_index
                valence[vi] += 1

        for vi in range(vcount):
            d = max(1, valence[vi])
            per_vertex_displacement[vi] /= d

        print(f"[MLD] ✓ Carrier heightfill completed on {vcount} vertices")
        return per_vertex_displacement

    except Exception as e:
        print(f"[MLD] Carrier heightfill failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# Register
classes = (MLD_OT_recalculate,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)