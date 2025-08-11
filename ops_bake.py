# Bake mesh: apply GN/Subdiv/Decimate, optionally pack VC, cleanup layer attrs
import bpy
from bpy.types import Operator
from .utils import active_obj, polycount, safe_mode
from .attrs import ensure_color_attr, color_attr_exists, loop_red
from .constants import PACK_ATTR, ALPHA_PREFIX, GN_MOD_NAME, SUBDIV_MOD_NAME, DECIMATE_MOD_NAME

def _any_channel_assigned(s):
    return any(L.vc_channel in {'R','G','B','A'} for L in s.layers)

def _pack_vc_now(obj, s):
    """Pack selected channels per-loop into PACK_ATTR; fill empty channels with white if option set."""
    me=obj.data
    ensure_color_attr(me, PACK_ATTR)
    nloops=len(me.loops)
    # build loop arrays per channel
    per_loop={'R':[0.0]*nloops, 'G':[0.0]*nloops, 'B':[0.0]*nloops, 'A':[1.0]*nloops}
    # default fill for unassigned
    default_zero = 1.0 if s.fill_empty_vc_white else 0.0
    per_loop['R'] = [default_zero]*nloops
    per_loop['G'] = [default_zero]*nloops
    per_loop['B'] = [default_zero]*nloops
    per_loop['A'] = [1.0]*nloops  # alpha default keep 1

    chan_map={'R':None,'G':None,'B':None,'A':None}
    for i,L in enumerate(s.layers):
        ch=L.vc_channel
        if ch in chan_map and chan_map[ch] is None:
            chan_map[ch]=i

    for ch, idx in chan_map.items():
        if idx is None:  # leave default
            continue
        L=s.layers[idx]
        if not L.mask_name or not color_attr_exists(me, L.mask_name):
            continue
        for li in range(nloops):
            per_loop[ch][li]=loop_red(me, L.mask_name, li)

    # write
    if hasattr(me, "color_attributes"):
        attr = me.color_attributes.get(PACK_ATTR)
        for li in range(nloops):
            attr.data[li].color = (per_loop['R'][li], per_loop['G'][li], per_loop['B'][li], per_loop['A'][li])
    else:
        vcol = me.vertex_colors.get(PACK_ATTR)
        for li in range(nloops):
            vcol.data[li].color = (per_loop['R'][li], per_loop['G'][li], per_loop['B'][li], per_loop['A'][li])
    me.update()
    s.vc_packed=True

def _cleanup_after_bake(obj):
    me=obj.data
    # remove MLD mask attributes
    if hasattr(me, "color_attributes"):
        for a in list(me.color_attributes):
            if a.name.startswith("MLD_Mask_"):
                try: me.color_attributes.remove(a)
                except Exception: pass
    elif hasattr(me, "vertex_colors"):
        for a in list(me.vertex_colors):
            if a.name.startswith("MLD_Mask_"):
                try: me.vertex_colors.remove(a)
                except Exception: pass
    # remove alpha attrs (if somehow present on object)
    if hasattr(me, "attributes"):
        for a in list(me.attributes):
            if a.name.startswith(ALPHA_PREFIX):
                try: me.attributes.remove(a)
                except Exception: pass
    me.update()

class MLD_OT_bake_mesh(Operator):
    bl_idname = "mld.bake_mesh"
    bl_label = "Bake Mesh"
    bl_description = "Apply Subdiv/GN/Decimate, pack VC if channels chosen, remove layer attributes and carrier, clear settings"

    def execute(self, context):
        obj=active_obj(context)
        if not obj or obj.type!='MESH': return {'CANCELLED'}
        s=obj.mld_settings

        # pack VC if any channel assigned
        if _any_channel_assigned(s):
            _pack_vc_now(obj, s)

        prev = safe_mode(obj, 'OBJECT')

        # apply modifiers in order: Subdiv -> GN -> Decimate
        for name in (SUBDIV_MOD_NAME, GN_MOD_NAME, DECIMATE_MOD_NAME):
            md = obj.modifiers.get(name)
            if md:
                try:
                    bpy.ops.object.modifier_apply(modifier=name)
                except Exception:
                    pass

        # remove carrier object
        cname=f"MLD_Carrier::{obj.name}"
        carr=bpy.data.objects.get(cname)
        if carr:
            try:
                me=carr.data
                bpy.data.objects.remove(carr, do_unlink=True)
                if me and me.users==0:
                    bpy.data.meshes.remove(me, do_unlink=True)
            except Exception: pass

        _cleanup_after_bake(obj)

        # clear settings (layers etc.)
        s.layers.clear()
        s.is_painting=False
        s.vc_packed=False

        # refresh stats
        v,f,t = polycount(obj.data)
        s.last_poly_v, s.last_poly_f, s.last_poly_t = v,f,t

        safe_mode(obj, prev)
        self.report({'INFO'},"Baked mesh.")
        return {'FINISHED'}

classes=(MLD_OT_bake_mesh,)
def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
