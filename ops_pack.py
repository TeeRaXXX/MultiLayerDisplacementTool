# Pack selected layers' masks into a single Vertex Color (R/G/B/A)
import bpy
from bpy.types import Operator
from .utils import active_obj
from .attrs import (
    ensure_color_attr, color_attr_exists, loop_red
)
from .constants import PACK_ATTR

class MLD_OT_pack_vcols(Operator):
    bl_idname = "mld.pack_vcols"
    bl_label = "Pack Vertex Colors"
    bl_description = "Pack per-layer mask (vertex-averaged) into VC channels R/G/B/A"

    def execute(self, context):
        obj=active_obj(context)
        if not obj or obj.type!='MESH': return {'CANCELLED'}
        s=obj.mld_settings
        me=obj.data

        # ensure target VC
        ensure_color_attr(me, PACK_ATTR)
        # build loop arrays per channel
        Ls=list(s.layers)
        chan_map={'R':None,'G':None,'B':None,'A':None}
        for i,L in enumerate(Ls):
            ch=L.vc_channel
            if ch in chan_map and chan_map[ch] is None:
                chan_map[ch]=i

        # average loop→vertex per channel
        nv=len(me.vertices); nloops=len(me.loops)
        per_loop={'R':[0.0]*nloops, 'G':[0.0]*nloops, 'B':[0.0]*nloops, 'A':[0.0]*nloops}
        for ch, idx in chan_map.items():
            if idx is None:  # fill zeros if not assigned
                continue
            L=Ls[idx]
            if not L.mask_name or not color_attr_exists(me, L.mask_name):
                continue
            for li in range(nloops):
                per_loop[ch][li]=loop_red(me, L.mask_name, li)

        # write into PACK_ATTR (corner domain)
        if hasattr(me, "color_attributes"):
            attr = me.color_attributes.get(PACK_ATTR)
            for li in range(nloops):
                r=per_loop['R'][li]; g=per_loop['G'][li]; b=per_loop['B'][li]; a=per_loop['A'][li]
                attr.data[li].color=(r,g,b,a if a>0.0 else 1.0)
        else:
            vcol = me.vertex_colors.get(PACK_ATTR)
            for li in range(nloops):
                r=per_loop['R'][li]; g=per_loop['G'][li]; b=per_loop['B'][li]; a=per_loop['A'][li]
                vcol.data[li].color=(r,g,b,a if a>0.0 else 1.0)

        me.update()
        s.vc_packed=True
        self.report({'INFO'},"Packed to VC.")
        return {'FINISHED'}

classes=(MLD_OT_pack_vcols,)
def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
