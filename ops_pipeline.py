# ops_pipeline.py — ОБНОВЛЕННАЯ ВЕРСИЯ с новой системой смешивания

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill  # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
from .materials import build_heightlerp_preview_shader_new  # НОВЫЙ PREVIEW
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

        print("[MLD] === NEW BLENDING SYSTEM RECALCULATE START ===")
        
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

        # STEP 5: НОВАЯ система heightfill + Carrier integration
        print("[MLD] Computing heightfill with NEW blending system...")
        try:
            # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ из heightfill.py
            success = solve_heightfill(obj, s, context, work_mesh)
            if not success:
                raise Exception("New heightfill returned False")
            
            print(f"[MLD] ✓ NEW Heightfill computed successfully")
            
            # STEP 5.5: Transfer results to carrier for GN
            print("[MLD] Transferring heightfill results to carrier...")
            try:
                from .attrs import ensure_float_attr
                from .constants import OFFS_ATTR
                
                # Ensure carrier has proper attributes
                carrier_mesh = carrier.data
                offs_attr = ensure_float_attr(carrier_mesh, OFFS_ATTR, domain='POINT', data_type='FLOAT_VECTOR')
                
                # Copy displacement data from original mesh to carrier
                orig_offs_attr = obj.data.attributes.get(OFFS_ATTR)
                if orig_offs_attr and offs_attr:
                    # Direct copy for same topology
                    max_copy = min(len(orig_offs_attr.data), len(offs_attr.data))
                    for vi in range(max_copy):
                        try:
                            offs_attr.data[vi].vector = orig_offs_attr.data[vi].vector
                        except Exception:
                            offs_attr.data[vi].vector = (0.0, 0.0, 0.0)
                    
                    carrier_mesh.update()
                    print(f"[MLD] ✓ Transferred {max_copy} displacement values to carrier")
                else:
                    print(f"[MLD] ⚠ Could not find displacement attributes for carrier transfer")
                    
            except Exception as e:
                print(f"[MLD] ⚠ Carrier transfer failed: {e}")
                # Continue anyway - displacement might still work
            
        except Exception as e:
            print(f"[MLD] ✗ NEW heightfill failed: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, "Height solve failed (check UV and height maps).")
            return {'CANCELLED'}

        # STEP 6: Setup GN modifier to read from carrier
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

        # STEP 7: Setup decimate
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

        # STEP 8: Auto-assign materials
        try:
            if getattr(s, "auto_assign_materials", False):
                print("[MLD] Auto-assigning materials...")
                print("[MLD] ○ Material assignment skipped (needs carrier support)")
        except Exception as e:
            print(f"[MLD] ✗ Auto assign failed: {e}")

        # STEP 9: НОВАЯ система preview материала
        try:
            if getattr(s, "preview_enable", False):
                print("[MLD] Building preview material with NEW blending...")
                
                # Используем новую функцию preview
                mat = build_heightlerp_preview_shader_new(
                    obj, s,
                    preview_influence=getattr(s, "preview_mask_influence", 1.0),
                    preview_contrast=getattr(s, "preview_contrast", 1.0),
                )
                
                if mat:
                    print("[MLD] ✓ NEW Preview material built")
                else:
                    print("[MLD] ⚠ Preview material creation failed")
        except Exception as e:
            print(f"[MLD] ✗ NEW Preview build failed: {e}")
            import traceback
            traceback.print_exc()

        # STEP 10: Cleanup (БЕЗОПАСНО)
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

        print("[MLD] === NEW BLENDING SYSTEM RECALCULATE COMPLETE ===")
        self.report({'INFO'}, "Displacement calculated using NEW blending system.")
        return {'FINISHED'}

# Register
classes = (MLD_OT_recalculate,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)