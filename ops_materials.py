from __future__ import annotations
import bpy
from bpy.types import Operator
from .utils import active_obj
from .constants import ALPHA_PREFIX

# ---------------- helpers ----------------

def _ensure_obj_mode(obj: bpy.types.Object):
    ctx = bpy.context
    if ctx.view_layer.objects.active is not obj:
        ctx.view_layer.objects.active = obj
    if not obj.select_get():
        obj.select_set(True)
    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def _ensure_mat_slot(obj: bpy.types.Object, mat: bpy.types.Material) -> int:
    slots = obj.data.materials
    for i, m in enumerate(slots):
        if m is mat:
            return i
    slots.append(mat)
    return len(slots) - 1

def _poly_alpha(me: bpy.types.Mesh, layer_index: int, poly: bpy.types.MeshPolygon) -> float:
    """Average point-domain ALPHA_i over polygon vertices."""
    attr = me.attributes.get(f"{ALPHA_PREFIX}{layer_index}")
    if not attr:
        return 0.0
    acc = 0.0
    cnt = len(poly.vertices)
    for vi in poly.vertices:
        acc += float(attr.data[vi].value)
    return acc / max(1, cnt)

# ---------------- operator ----------------

class MLD_OT_assign_materials(Operator):
    """Assign materials by actual displacement result (ALPHA winners)."""
    bl_idname  = "mld.assign_materials"
    bl_label   = "Assign Materials"
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        obj = active_obj(context)
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}
        s  = obj.mld_settings
        me = obj.data

        _ensure_obj_mode(obj)

        # material slots for enabled layers
        slot_by_layer = {}
        for i, L in enumerate(s.layers):
            if L.enabled and L.material:
                slot_by_layer[i] = _ensure_mat_slot(obj, L.material)
        if not slot_by_layer:
            self.report({'WARNING'}, "No layers with materials to assign.")
            return {'CANCELLED'}

        thr = float(getattr(s, 'mat_assign_threshold', getattr(s, 'assign_threshold', getattr(s, 'mask_threshold', 0.05))))
        changed = 0

        for poly in me.polygons:
            best_i, best_a = None, 0.0
            for i, L in enumerate(s.layers):
                if i not in slot_by_layer:
                    continue
                a = _poly_alpha(me, i, poly)
                if a > best_a:
                    best_a, best_i = a, i
            if best_i is not None and best_a >= thr:
                si = slot_by_layer[best_i]
                if poly.material_index != si:
                    poly.material_index = si
                    changed += 1

        me.update()
        self.report({'INFO'}, f"Assigned materials. Polygons changed: {changed}")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(MLD_OT_assign_materials)

def unregister():
    bpy.utils.unregister_class(MLD_OT_assign_materials)
