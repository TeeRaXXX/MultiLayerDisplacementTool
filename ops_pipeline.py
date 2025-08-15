# ops_pipeline.py — БЕЗОПАСНАЯ ВЕРСИЯ (предотвращение зависания)

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill
from .materials import build_heightlerp_preview_shader
from .constants import GN_MOD_NAME, MULTIRES_GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME, OFFS_ATTR
from .carrier import ensure_carrier, sync_carrier_mesh
from .gn_multires import ensure_multires_gn, remove_multires_gn, ensure_modifier_order

def _ensure_multires_new(obj: bpy.types.Object, s):
    """БЕЗОПАСНАЯ реализация multiresolution через Geometry Nodes."""
    
    print(f"[MLD] === _ensure_multires_new DEBUG ===")
    print(f"[MLD] Object: {obj.name}")
    print(f"[MLD] Settings object: {s}")
    print(f"[MLD] subdiv_enable value: {getattr(s, 'subdiv_enable', False)}")
    print(f"[MLD] subdiv_enable type: {type(getattr(s, 'subdiv_enable', False))}")
    print(f"[MLD] ==================================")
    
    if getattr(s, "subdiv_enable", False):
        # ПРОВЕРКА безопасности multiresolution уровней
        subdiv_view = getattr(s, "subdiv_view", 1)
        print(f"[MLD] === OPS_PIPELINE MULTIRESOLUTION DEBUG ===")
        print(f"[MLD] Initial subdiv_view: {subdiv_view}")
        print(f"[MLD] Type of subdiv_view: {type(subdiv_view)}")
        
        if subdiv_view > 4:
            print(f"[MLD] WARNING: Multiresolution level {subdiv_view} is too high! Limiting to 4 to prevent freeze.")
            # Временно изменяем значение в settings для этого расчета
            original_value = s.subdiv_view
            s.subdiv_view = 4
            print(f"[MLD] Temporarily set subdiv_view to 4, original was {original_value}")
        else:
            print(f"[MLD] Multiresolution level {subdiv_view} is within safe limits")
        
        print(f"[MLD] Current subdiv_view after check: {getattr(s, 'subdiv_view', 1)}")
        print(f"[MLD] ==========================================")
        
        # Убедимся что mesh не слишком сложный для multiresolution
        vert_count = len(obj.data.vertices)
        poly_count = len(obj.data.polygons)
        
        if vert_count > 50000 or poly_count > 50000:
            print(f"[MLD] WARNING: Mesh is complex ({vert_count} verts, {poly_count} polys)")
            print(f"[MLD] Consider using lower multiresolution levels or simpler mesh")
        
        # Проверка на слишком сложную геометрию с multiresolution
        estimated_polys = poly_count * (4 ** getattr(s, "subdiv_view", 1))
        if estimated_polys > 2000000:  # 2 миллиона полигонов
            print(f"[MLD] ERROR: Estimated {estimated_polys:,} polygons after multiresolution - TOO MUCH!")
            print(f"[MLD] Disabling multiresolution to prevent freeze")
            return None
        
        # Сначала удаляем все старые multiresolution модификаторы если есть
        multires_modifiers = ["MLD_Multires", "MLD_MultiresGN", SUBDIV_MOD_NAME]  # MLD_Multires в приоритете
        for mod_name in multires_modifiers:
            old_md = obj.modifiers.get(mod_name)
            if old_md:
                try:
                    obj.modifiers.remove(old_md)
                    print(f"[MLD] Removed old multiresolution modifier: {mod_name}")
                except Exception as e:
                    print(f"[MLD] Warning: could not remove {mod_name}: {e}")
        
        print(f"[MLD] Creating multiresolution GN with SAFE parameters:")
        print(f"  - subdiv_enable: {getattr(s, 'subdiv_enable', False)}")
        print(f"  - subdiv_view: {getattr(s, 'subdiv_view', 1)} (safe limit: 4)")
        print(f"  - estimated final polys: {estimated_polys:,}")
        
        # Создаем новый GN multiresolution с дополнительными проверками
        try:
            md = ensure_multires_gn(obj, s)
            if md:
                print(f"[MLD] ✓ Multiresolution GN ready: {getattr(s, 'subdiv_view', 1)} levels")
                
                # ВАЖНО: Принудительное обновление чтобы убедиться что modifier работает
                try:
                    bpy.context.view_layer.update()
                    print(f"[MLD] ✓ Forced depsgraph update after multiresolution GN")
                except Exception as e:
                    print(f"[MLD] Warning: depsgraph update failed: {e}")
                
                # Обеспечить правильный порядок модификаторов
                ensure_modifier_order(obj)
                
                # Восстановить оригинальное значение если изменяли
                if 'original_value' in locals():
                    print(f"[MLD] Restoring original subdiv_view: {original_value}")
                    s.subdiv_view = original_value
                    print(f"[MLD] After restoration, subdiv_view: {getattr(s, 'subdiv_view', 1)}")
                else:
                    print(f"[MLD] No original_value to restore, current subdiv_view: {getattr(s, 'subdiv_view', 1)}")
                
                return md
            else:
                print(f"[MLD] ✗ Failed to create multiresolution GN")
                return None
                
        except Exception as e:
            print(f"[MLD] ✗ Exception in multiresolution GN creation: {e}")
            import traceback
            traceback.print_exc()
            return None
    else:
        # Удаляем все типы multiresolution если отключено
        multires_modifiers = ["MLD_Multires", "MLD_MultiresGN", SUBDIV_MOD_NAME]  # MLD_Multires в приоритете
        for mod_name in multires_modifiers:
            old_md = obj.modifiers.get(mod_name)
            if old_md:
                try:
                    obj.modifiers.remove(old_md)
                    print(f"[MLD] Removed multiresolution modifier: {mod_name}")
                except Exception as e:
                    print(f"[MLD] Warning: could not remove {mod_name}: {e}")
        
        remove_multires_gn(obj)
        print(f"[MLD] ○ Multiresolution: disabled")
    
    return None

def _get_multires_mesh_safe(obj: bpy.types.Object, context) -> bpy.types.Mesh:
    """БЕЗОПАСНОЕ получение multiresolution mesh с проверками."""
    try:
        print(f"[MLD] Getting multiresolution mesh safely...")
        
        # Проверяем все возможные multiresolution модификаторы
        multires_modifiers = ["MLD_Multires", "MLD_MultiresGN", SUBDIV_MOD_NAME]  # MLD_Multires в приоритете
        multires_md = None
        
        for mod_name in multires_modifiers:
            multires_md = obj.modifiers.get(mod_name)
            if multires_md:
                print(f"[MLD] Found multiresolution modifier: {mod_name}")
                break
        
        if not multires_md:
            print(f"[MLD] No multiresolution modifier found")
            return None
        
        if not multires_md.show_viewport:
            print(f"[MLD] Multiresolution modifier is disabled")
            return None
        
        # БЕЗОПАСНОЕ временное отключение других модификаторов
        modifiers_states = []
        for mod in obj.modifiers:
            modifiers_states.append((mod.name, mod.show_viewport))
            # Отключаем все модификаторы кроме найденного multiresolution
            if mod.name != multires_md.name:
                mod.show_viewport = False
        
        # ПРИНУДИТЕЛЬНОЕ обновление dependency graph
        try:
            context.view_layer.update()
        except Exception as e:
            print(f"[MLD] Warning: context update failed: {e}")
        
        # Получаем evaluated mesh с таймаутом защитой (conceptual)
        print(f"[MLD] Evaluating multiresolution mesh...")
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        
        # ПРОВЕРКА результата перед to_mesh
        if not obj_eval or not obj_eval.data:
            raise Exception("Failed to get evaluated object")
        
        mesh_multires = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        
        # ПРОВЕРКА результирующего mesh
        if not mesh_multires:
            raise Exception("to_mesh() returned None")
        
        # Проверка разумности результата
        new_vert_count = len(mesh_multires.vertices)
        original_vert_count = len(obj.data.vertices)
        
        if new_vert_count > original_vert_count * 100:  # Более чем в 100 раз
            print(f"[MLD] WARNING: Multiresolution mesh is extremely large: {new_vert_count} vertices")
            print(f"[MLD] Original had {original_vert_count} vertices")
        
        # Восстанавливаем состояния модификаторов
        for mod_name, show_state in modifiers_states:
            mod = obj.modifiers.get(mod_name)
            if mod:
                mod.show_viewport = show_state
        
        print(f"[MLD] ✓ Got multiresolution mesh: {new_vert_count} verts (from {original_vert_count} original)")
        return mesh_multires
        
    except Exception as e:
        print(f"[MLD] ✗ Failed to get multiresolution mesh: {e}")
        import traceback
        traceback.print_exc()
        
        # Восстанавливаем состояния модификаторов в случае ошибки
        try:
            for mod_name, show_state in modifiers_states:
                mod = obj.modifiers.get(mod_name)
                if mod:
                    mod.show_viewport = show_state
        except Exception:
            pass
        
        return None

def _write_displacement_to_carrier(obj: bpy.types.Object, carrier, multires_mesh, per_vert_displacement):
    """Write displacement data directly to carrier mesh attributes."""
    try:
        # Обновим carrier mesh с multiresolution топологией
        sync_carrier_mesh(carrier, multires_mesh)
        
        # Убедимся что у carrier есть OFFS атрибут
        carrier_mesh = carrier.data
        offs_attr = carrier_mesh.attributes.get(OFFS_ATTR)
        if not offs_attr:
            offs_attr = carrier_mesh.attributes.new(name=OFFS_ATTR, type='FLOAT_VECTOR', domain='POINT')
        
        # БЕЗОПАСНАЯ запись displacement в carrier
        max_writes = min(len(offs_attr.data), len(per_vert_displacement))
        for vi in range(max_writes):
            try:
                displacement = float(per_vert_displacement[vi])
                offs_attr.data[vi].vector = (0.0, 0.0, displacement)  # Z = scalar displacement
            except Exception as e:
                print(f"[MLD] Warning: failed to write displacement for vertex {vi}: {e}")
                continue
        
        carrier_mesh.update()
        print(f"[MLD] Wrote displacement to carrier: {max_writes} values")
        return True
        
    except Exception as e:
        print(f"[MLD] Failed to write displacement to carrier: {e}")
        import traceback
        traceback.print_exc()
        return False

def _ensure_gn_modifier(obj: bpy.types.Object):
    """Ensure GN modifier exists and reads from carrier."""
    try:
        from .gn import ensure_gn
        md = ensure_gn(obj)
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
        
        # Убедимся что decimate в конце стека
        ensure_modifier_order(obj)
        
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

        # ДИАГНОСТИКА настроек
        print(f"[MLD] === SETTINGS DEBUG ===")
        print(f"[MLD] Settings object: {s}")
        print(f"[MLD] Settings type: {type(s)}")
        print(f"[MLD] subdiv_enable: {getattr(s, 'subdiv_enable', 'NOT_FOUND')}")
        print(f"[MLD] subdiv_view: {getattr(s, 'subdiv_view', 'NOT_FOUND')}")
        print(f"[MLD] ======================")

        if len(s.layers) == 0:
            self.report({'WARNING'}, "No layers to process.")
            return {'CANCELLED'}

        # БЕЗОПАСНАЯ проверка сложности меша
        vert_count = len(obj.data.vertices)
        poly_count = len(obj.data.polygons)
        
        print(f"[MLD] Mesh complexity check: {vert_count} verts, {poly_count} polys")
        
        # ПРЕДУПРЕЖДЕНИЕ о сложности
        if vert_count > 100000:
            self.report({'WARNING'}, f"High poly mesh ({vert_count:,} vertices). Consider lower multiresolution levels.")
        
        # Ensure Object mode
        try:
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        print("[MLD] === SAFE MULTIRESOLUTION GN RECALCULATE START ===")
        
        # STEP 1: Setup multiresolution modifier (БЕЗОПАСНАЯ ВЕРСИЯ)
        multires_md = None
        try:
            multires_md = _ensure_multires_new(obj, s)
            if multires_md:
                print(f"[MLD] ✓ Multiresolution GN ready: {getattr(s, 'subdiv_view', 1)} levels")
            else:
                print("[MLD] ○ Multiresolution: disabled or failed")
        except Exception as e:
            print(f"[MLD] ✗ Multires GN setup failed: {e}")
            import traceback
            traceback.print_exc()
            # НЕ возвращаем CANCELLED - продолжаем без multiresolution

        # STEP 2: Force depsgraph update с retry
        for attempt in range(3):
            try:
                context.view_layer.update()
                print(f"[MLD] ✓ Dependency graph updated (attempt {attempt + 1})")
                break
            except Exception as e:
                print(f"[MLD] Warning: depsgraph update failed (attempt {attempt + 1}): {e}")
                if attempt == 2:  # Последняя попытка
                    print(f"[MLD] Continuing without successful depsgraph update")

        # STEP 3: Get multiresolution mesh (БЕЗОПАСНО)
        multires_mesh = None
        if multires_md:
            multires_mesh = _get_multires_mesh_safe(obj, context)
            if not multires_mesh:
                print(f"[MLD] ⚠ Failed to get multiresolution mesh, using original")
        
        # Use multiresolution or original mesh for heightfill
        work_mesh = multires_mesh if multires_mesh else obj.data
        print(f"[MLD] Using work mesh: {len(work_mesh.vertices)} vertices")

        # STEP 4: Create carrier for multiresolution topology
        try:
            carrier = ensure_carrier(obj)
            print(f"[MLD] ✓ Carrier created: {carrier.name}")
        except Exception as e:
            print(f"[MLD] ✗ Carrier creation failed: {e}")
            return {'CANCELLED'}

        # STEP 5: Compute heightfill on work mesh
        print("[MLD] Computing heightfill on work mesh...")
        try:
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
            
            # Убедимся в правильном порядке модификаторов
            ensure_modifier_order(obj)
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
                
                # Принудительное обновление после decimate
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

        # STEP 11: Cleanup (БЕЗОПАСНО)
        if multires_mesh:
            try:
                bpy.data.meshes.remove(multires_mesh, do_unlink=True)
                print("[MLD] ✓ Cleaned up multiresolution mesh")
            except Exception as e:
                print(f"[MLD] Warning: cleanup failed: {e}")

        # Final polycount reporting
        try:
            from .utils import polycount, get_evaluated_polycount, format_polycount
            
            print("\n[MLD] === POLYCOUNT SUMMARY ===")
            
            # Original mesh
            orig_v, orig_f, orig_t = polycount(obj.data)
            print(f"[MLD] Original mesh: {format_polycount(orig_v, orig_f, orig_t)}")
            
            # Final result (all modifiers) - с таймаутом защитой
            try:
                final_v, final_f, final_t = get_evaluated_polycount(obj, context, verbose=True)
                print(f"[MLD] Final result: {format_polycount(final_v, final_f, final_t)}")
                
                # Update settings
                s.last_poly_v, s.last_poly_f, s.last_poly_t = final_v, final_f, final_t
            except Exception as e:
                print(f"[MLD] Could not get final polycount: {e}")
                
            print("[MLD] === END POLYCOUNT ===\n")
            
        except Exception as e:
            print(f"[MLD] Polycount reporting failed: {e}")

        # Final modifier stack
        try:
            mod_names = [f"{m.name}({m.type})" for m in obj.modifiers]
            print(f"[MLD] Final modifier stack: {' → '.join(mod_names)}")
        except Exception:
            pass

        # БЕЗОПАСНОЕ Force final viewport update
        try:
            context.view_layer.update()
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
                elif area.type == 'PROPERTIES':
                    area.tag_redraw()
        except Exception as e:
            print(f"[MLD] Warning: viewport update failed: {e}")

        print("[MLD] === SAFE MULTIRESOLUTION GN RECALCULATE COMPLETE ===")
        self.report({'INFO'}, "Displacement calculated using Multiresolution GN (SAFE MODE).")
        return {'FINISHED'}

def solve_heightfill_for_carrier(obj: bpy.types.Object, s, context, work_mesh: bpy.types.Mesh):
    """БЕЗОПАСНАЯ версия heightfill for carrier."""
    try:
        from .sampling import (
            make_sampler, find_image_and_uv_from_displacement,
            active_uv_layer_name, sample_height_at_loop,
        )
        from .attrs import point_red, loop_red, color_attr_exists
        
        # ПРОВЕРКА входных данных
        if not work_mesh or not work_mesh.vertices:
            print("[MLD] Error: Invalid work mesh")
            return None
        
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
        
        # ПРОВЕРКА разумности размера
        if vcount > 1000000:  # 1 миллион вершин
            print(f"[MLD] Warning: Very high vertex count: {vcount:,}")
        
        # Displacement accumulator
        per_vertex_displacement = [0.0] * vcount
        
        print(f"[MLD] Processing {len(work_mesh.polygons)} polygons for carrier...")

        # БЕЗОПАСНАЯ обработка полигонов с прогрессом
        poly_count = len(work_mesh.polygons)
        progress_step = max(1, poly_count // 20)  # 20 шагов прогресса
        
        for poly_idx, poly in enumerate(work_mesh.polygons):
            # Прогресс лог
            if poly_idx % progress_step == 0:
                progress = (poly_idx / poly_count) * 100
                print(f"[MLD] Processing polygons: {progress:.1f}% ({poly_idx}/{poly_count})")
            
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                try:
                    vi = work_mesh.loops[li].vertex_index
                    
                    # БЕЗОПАСНАЯ проверка индекса
                    if vi >= vcount:
                        print(f"[MLD] Warning: vertex index {vi} out of range")
                        continue

                    # Collect per-layer heights and masks
                    h_layer = [0.0] * n_layers
                    m_layer = [0.0] * n_layers
                    
                    for i, L in enumerate(s.layers):
                        if not L.enabled:
                            continue
                        
                        # Mask from original mesh - proper mapping
                        m = 0.0
                        if L.mask_name and color_attr_exists(obj.data, L.mask_name):
                            # БЕЗОПАСНОЕ mapping work mesh loop to original mesh loop
                            if li < len(obj.data.loops):
                                orig_li = li
                            else:
                                # For subdivided meshes, find closest original loop
                                try:
                                    work_uv = work_mesh.uv_layers[uv_name].data[li].uv
                                    min_dist = float('inf')
                                    orig_li = 0
                                    
                                    # Ограничиваем поиск чтобы не зависнуть
                                    search_limit = min(len(obj.data.loops), 10000)
                                    for orig_loop_idx in range(search_limit):
                                        try:
                                            orig_uv = obj.data.uv_layers[uv_name].data[orig_loop_idx].uv
                                            dist = ((work_uv.x - orig_uv.x) ** 2 + (work_uv.y - orig_uv.y) ** 2) ** 0.5
                                            if dist < min_dist:
                                                min_dist = dist
                                                orig_li = orig_loop_idx
                                        except Exception:
                                            continue
                                except Exception as e:
                                    print(f"[MLD] Warning: UV mapping failed for loop {li}: {e}")
                                    orig_li = min(li, len(obj.data.loops) - 1)
                            
                            m = loop_red(obj.data, L.mask_name, orig_li)
                            if m is None:
                                # Fallback to vertex-based reading
                                if vi < len(obj.data.vertices):
                                    orig_vi = vi
                                else:
                                    # БЕЗОПАСНЫЙ поиск closest original vertex
                                    try:
                                        work_vert = work_mesh.vertices[vi].co
                                        min_dist = float('inf')
                                        orig_vi = 0
                                        
                                        # Ограничиваем поиск
                                        search_limit = min(len(obj.data.vertices), 10000)
                                        for orig_vert_idx in range(search_limit):
                                            orig_vert = obj.data.vertices[orig_vert_idx].co
                                            dist = (work_vert - orig_vert).length
                                            if dist < min_dist:
                                                min_dist = dist
                                                orig_vi = orig_vert_idx
                                    except Exception:
                                        orig_vi = min(vi, len(obj.data.vertices) - 1)
                                
                                m = point_red(obj.data, L.mask_name, orig_vi) or 0.0
                        m_layer[i] = m

                        # Height from work mesh
                        smp = samplers[i]
                        if smp is None:
                            continue
                        
                        try:
                            h = sample_height_at_loop(work_mesh, uv_name, li, max(1e-8, L.tiling), smp)
                            h = h * L.multiplier + L.bias
                            h_layer[i] = h
                        except Exception as e:
                            print(f"[MLD] Warning: height sampling failed for loop {li}: {e}")
                            h_layer[i] = 0.0

                    # HeightFill blend - ЛЕРПИНГ по маскам
                    filled_h = 0.0
                    total_weight = 0.0
                    
                    for i, L in enumerate(s.layers):
                        m = m_layer[i]
                        if m <= 0.0:
                            continue
                        
                        # Простой лерпинг: взвешенная сумма высот по маскам
                        filled_h += h_layer[i] * m
                        total_weight += m
                    
                    # Нормализация если есть веса
                    if total_weight > 0.0:
                        filled_h /= total_weight

                    # Add to vertex displacement (БЕЗОПАСНО)
                    displacement = (filled_h - s.midlevel) * s.strength
                    per_vertex_displacement[vi] += displacement
                    
                except Exception as e:
                    print(f"[MLD] Warning: failed to process loop {li}: {e}")
                    continue

        # Average by vertex valence (БЕЗОПАСНО)
        print(f"[MLD] Averaging by vertex valence...")
        valence = [0] * vcount
        
        for p in work_mesh.polygons:
            for li in range(p.loop_start, p.loop_start + p.loop_total):
                try:
                    vi = work_mesh.loops[li].vertex_index
                    if vi < vcount:
                        valence[vi] += 1
                except Exception:
                    continue

        for vi in range(vcount):
            try:
                d = max(1, valence[vi])
                per_vertex_displacement[vi] /= d
            except Exception:
                per_vertex_displacement[vi] = 0.0

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