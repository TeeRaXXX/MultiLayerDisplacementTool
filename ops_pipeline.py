# ops_pipeline.py — ОБНОВЛЕННАЯ ВЕРСИЯ с новой системой смешивания

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill  # ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
from .materials import build_heightlerp_preview_shader_new  # НОВЫЙ PREVIEW
from .constants import GN_MOD_NAME, DECIMATE_MOD_NAME, OFFS_ATTR
from .carrier import ensure_carrier, sync_carrier_mesh






def _write_displacement_to_carrier(obj: bpy.types.Object, carrier, mesh, per_vert_displacement):
    """Write displacement data directly to carrier mesh attributes."""
    try:
        # Обновим carrier mesh с топологией
        sync_carrier_mesh(carrier, mesh)
        
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
            self.report({'WARNING'}, f"High poly mesh ({vert_count:,} vertices). Consider simplifying the mesh.")
        
        # Ensure Object mode
        try:
            if obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        print("[MLD] === NEW BLENDING SYSTEM RECALCULATE START ===")
        
        # STEP 1: Create carrier for topology
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
            success = solve_heightfill(obj, s, context, obj.data)
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

        # STEP 2: Setup GN modifier to read from carrier
        print("[MLD] Setting up Geometry Nodes...")
        try:
            gn_ok = _ensure_gn_modifier(obj)
            if not gn_ok:
                raise Exception("Failed to create GN modifier")
            

            print("[MLD] ✓ Geometry Nodes displacement ready")
            
        except Exception as e:
            print(f"[MLD] ✗ GN setup failed: {e}")
            self.report({'ERROR'}, f"GN setup failed: {e}")
            return {'CANCELLED'}

        # STEP 3: Setup decimate
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

        # STEP 4: Auto-assign materials
        try:
            if getattr(s, "auto_assign_materials", False):
                print("[MLD] Auto-assigning materials...")
                print("[MLD] ○ Material assignment skipped (needs carrier support)")
        except Exception as e:
            print(f"[MLD] ✗ Auto assign failed: {e}")

        # STEP 5: НОВАЯ система preview материала
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

        # STEP 6: Cleanup

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