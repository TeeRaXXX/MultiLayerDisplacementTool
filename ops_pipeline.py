# ops_pipeline.py — recalc pipeline + preview build hook

from __future__ import annotations
import bpy

from .heightfill import solve_heightfill          # computes OFFS + ALPHA_i attributes
from .materials import build_heightlerp_preview_shader
from .constants import GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME
try:
    from .gn import ensure_gn as _ensure_gn_full
except Exception:
    _ensure_gn_full = None
# Если у тебя есть свой модуль для GN — оставь импорт:
# from .gn import ensure_gn_modifier
# В этом примере покажем безопасный доступ к уже существующему модификатору по имени:
GN_MOD_NAME = "MLD_DisplaceGN"
SUBDIV_MOD_NAME = "MLD_RefineSubdiv"


def _find_mod(obj: bpy.types.Object, name: str):
    for m in obj.modifiers:
        if m.name == name:
            return m
    return None


def _apply_subdiv_settings(obj: bpy.types.Object, s):
    """Optional: apply viewport/render levels from settings if the subdiv mod exists."""
    md = _find_mod(obj, SUBDIV_MOD_NAME)
    if not md or md.type != 'SUBSURF':
        return
    md.subdivision_type = 'SIMPLE' if getattr(s, "subdiv_type", 'SIMPLE') == 'SIMPLE' else 'CATMULL_CLARK'
    md.levels = int(getattr(s, "subdiv_view", 1))
    md.render_levels = int(getattr(s, "subdiv_render", 1))
    md.use_limit_surface = False


def _ensure_gn_exists(obj: bpy.types.Object):
    md = obj.modifiers.get(GN_MOD_NAME)
    if md and md.type == 'NODES':
        return True
    if _ensure_gn_full is not None:
        try:
            _ensure_gn_full(obj)
            return True
        except Exception:
            pass
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
        return md
    else:
        if md:
            try: obj.modifiers.remove(md)
            except Exception: pass
        return None

def _ensure_decimate(obj: bpy.types.Object, s):
    md = obj.modifiers.get(DECIMATE_MOD_NAME)
    if getattr(s, "decimate_enable", False):
        if not md or md.type != 'DECIMATE':
            md = obj.modifiers.new(DECIMATE_MOD_NAME, 'DECIMATE')
        md.decimate_type = 'COLLAPSE'
        md.ratio = float(getattr(s, "decimate_ratio", 0.5))
        md.use_collapse_triangulate = False
        try:
            gn = obj.modifiers.get(GN_MOD_NAME)
            if gn:
                obj.modifiers.move(obj.modifiers.find(DECIMATE_MOD_NAME), obj.modifiers.find(gn.name)+1)
        except Exception:
            pass
        return md
    else:
        if md:
            try: obj.modifiers.remove(md)
            except Exception: pass
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

        s = getattr(obj, "mld_settings", None) or getattr(context.scene, "mld_settings", None)
        if s is None:
            self.report({'ERROR'}, "No MLD settings found.")
            return {'CANCELLED'}

        # 1) compute heightfill → writes OFFS + ALPHA_i attributes
        ok = False
        try:
            ok = solve_heightfill(obj, s)
        except Exception as e:
            print("[MLD] solve_heightfill failed:", e)
            ok = False

        if not ok:
            self.report({'ERROR'}, "Height solve failed (check UV and height maps).")
            return {'CANCELLED'}

        # 2) make sure GN exists (do not build here, just check)
        if not _ensure_gn_exists(obj):
            # мягкое предупреждение, GN может быть создан другим шагом пайплайна
            print("[MLD] Warning: GN modifier not found. Displacement may be invisible until it is added.")

        # 3) optional: refine subdiv settings
        try:
            _apply_subdiv_settings(obj, s)
        except Exception as e:
            print("[MLD] Subdiv update skipped:", e)

        # 4) Decimate (preview helper)
        try:
            _ensure_decimate(obj, s)
        except Exception as e:
            print("[MLD] Decimate update skipped:", e)

        # 4.5) Auto-assign materials
        try:
            if getattr(s, "auto_assign_materials", False):
                bpy.ops.mld.assign_materials_from_disp()
        except Exception as e:
            print("[MLD] Auto assign failed:", e)

        # 5) PREVIEW BUILD — собрать/назначить HeightLerp превью,
        # если включён чекбокс preview_enable
        try:
            if getattr(s, "preview_enable", False):
                build_heightlerp_preview_shader(
                    obj, s,
                    preview_influence=getattr(s, "preview_mask_influence", 1.0),
                    preview_contrast=getattr(s, "preview_contrast", 1.0),
                )
        except Exception as e:
            print("[MLD] Preview build failed:", e)

        self.report({'INFO'}, "Displacement updated.")
        try:
            if getattr(s, 'preview_enable', False):
                from .materials import build_heightlerp_preview_shader
                build_heightlerp_preview_shader(obj, s)
        except Exception as e:
            print('[MLD] Preview build failed at finalize:', e)
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
