# ops_pipeline.py — recalc pipeline with guaranteed GN creation

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill
from .materials import build_heightlerp_preview_shader
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

def _find_mod(obj: bpy.types.Object, name: str):
    for m in obj.modifiers:
        if m.name == name:
            return m
    return None

def _ensure_gn_modifier(obj: bpy.types.Object):
    """Ensure GN modifier exists and is properly configured."""
    try:
        from .gn import ensure_gn
        md = ensure_gn(obj)
        return md is not None
    except Exception as e:
        print(f"[MLD] Failed to create GN modifier: {e}")
        return False

def _ensure_subdiv(obj: bpy.types.Object, s):
    md = obj.modifiers.get(SUBDIV_MOD_NAME)
    if getattr(s, "subdiv_enable", True):
        if not md or md.type != 'SUBSURF':
            md = obj.modifiers.new(SUBDIV_MOD_NAME, 'SUBSURF')
        md.subdivision_type = 'SIMPLE' if getattr(s, "subdiv_type", 'SIMPLE') == 'SIMPLE' else 'CATMULL_CLARK'
        md.levels = int(getattr(s, "subdiv_view", 1))
        md.render_levels = int(getattr(s, "subdiv_render", 1))
        md.use_limit_surface = False
        
        # Move subdiv before GN if it exists
        try:
            gn = obj.modifiers.get(GN_MOD_NAME)
            if gn:
                gn_idx = obj.modifiers.find(gn.name)
                subdiv_idx = obj.modifiers.find(SUBDIV_MOD_NAME)
                if subdiv_idx > gn_idx:
                    obj.modifiers.move(subdiv_idx, gn_idx)
        except Exception:
            pass
        return md
    else:
        if md:
            try: 
                obj.modifiers.remove(md)
            except Exception: 
                pass
        return None

def _ensure_decimate(obj: bpy.types.Object, s):
    md = obj.modifiers.get(DECIMATE_MOD_NAME)
    if getattr(s, "decimate_enable", False):
        if not md or md.type != 'DECIMATE':
            md = obj.modifiers.new(DECIMATE_MOD_NAME, 'DECIMATE')
        md.decimate_type = 'COLLAPSE'
        md.ratio = float(getattr(s, "decimate_ratio", 0.5))
        md.use_collapse_triangulate = False
        
        # Move decimate after GN if it exists
        try:
            gn = obj.modifiers.get(GN_MOD_NAME)
            if gn:
                gn_idx = obj.modifiers.find(gn.name)
                decimate_idx = obj.modifiers.find(DECIMATE_MOD_NAME)
                if decimate_idx < gn_idx:
                    obj.modifiers.move(decimate_idx, gn_idx + 1)
        except Exception:
            pass
        return md
    else:
        if md:
            try: 
                obj.modifiers.remove(md)
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

        # Check basic requirements
        if len(s.layers) == 0:
            self.report({'WARNING'}, "No layers to process.")
            return {'CANCELLED'}

        # 1) Compute heightfill → writes OFFS + ALPHA_i attributes
        try:
            ok = solve_heightfill(obj, s)
        except Exception as e:
            print(f"[MLD] solve_heightfill failed: {e}")
            ok = False

        if not ok:
            self.report({'ERROR'}, "Height solve failed (check UV and height maps).")
            return {'CANCELLED'}

        # 2) ENSURE GN modifier exists (this was missing!)
        gn_ok = _ensure_gn_modifier(obj)
        if not gn_ok:
            self.report({'ERROR'}, "Failed to create Geometry Nodes modifier.")
            return {'CANCELLED'}

        # 3) Setup subdivision
        try:
            _ensure_subdiv(obj, s)
        except Exception as e:
            print(f"[MLD] Subdiv setup failed: {e}")

        # 4) Setup decimate
        try:
            _ensure_decimate(obj, s)
        except Exception as e:
            print(f"[MLD] Decimate setup failed: {e}")

        # 5) Auto-assign materials
        try:
            if getattr(s, "auto_assign_materials", False):
                bpy.ops.mld.assign_materials_from_disp()
        except Exception as e:
            print(f"[MLD] Auto assign failed: {e}")

        # 6) Build preview material
        try:
            if getattr(s, "preview_enable", False):
                build_heightlerp_preview_shader(
                    obj, s,
                    preview_influence=getattr(s, "preview_mask_influence", 1.0),
                    preview_contrast=getattr(s, "preview_contrast", 1.0),
                )
        except Exception as e:
            print(f"[MLD] Preview build failed: {e}")

        # Force viewport update
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        except Exception:
            pass

        self.report({'INFO'}, "Displacement recalculated successfully.")
        return {'FINISHED'}

# Register ---------------------------------------------------------------------

classes = (
    MLD_OT_recalculate,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)