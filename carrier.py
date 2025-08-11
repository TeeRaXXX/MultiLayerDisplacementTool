# Hidden carrier mesh that stores displacement vectors and per-layer alphas
import bpy
import bmesh
from mathutils import Matrix
from .constants import OFFS_ATTR, ALPHA_PREFIX
from .utils import ensure_visible

def ensure_point_attr(mesh: bpy.types.Mesh, name: str, dtype='FLOAT'):
    try:
        attr = mesh.attributes.get(name)
        if attr is None:
            attr = mesh.attributes.new(name=name, type=dtype, domain='POINT')
        return attr
    except Exception:
        return None

def carrier_name(obj): 
    return f"MLD_Carrier::{obj.name}"

def ensure_carrier(obj: bpy.types.Object):
    """Create (or fetch) hidden child that mirrors evaluated topology."""
    name = carrier_name(obj)
    carr = bpy.data.objects.get(name)
    if carr and carr.type != 'MESH':
        try: bpy.data.objects.remove(carr, do_unlink=True)
        except Exception: pass
        carr = None
    if carr is None:
        me = obj.data.copy()
        carr = bpy.data.objects.new(name=name, object_data=me)
        try:
            coll = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
            coll.objects.link(carr)
        except Exception:
            bpy.context.scene.collection.objects.link(carr)
    try:
        if carr.parent != obj:
            carr.parent = obj
        carr.matrix_parent_inverse = Matrix.Identity(4)
        carr.location = (0,0,0); carr.rotation_euler=(0,0,0); carr.scale=(1,1,1)
        carr.hide_set(True); carr.hide_render = True; carr.display_type = 'WIRE'
    except Exception:
        pass
    return carr

def sync_carrier_mesh(carr: bpy.types.Object, refined_me: bpy.types.Mesh):
    """Replace carrier's mesh datablock with refined topology copy."""
    try:
        old = carr.data
        carr.data = refined_me.copy()
        if old and old.users == 0:
            bpy.data.meshes.remove(old, do_unlink=True)
    except Exception:
        pass
    ensure_point_attr(carr.data, OFFS_ATTR, 'FLOAT_VECTOR')
    carr.data.update()

def write_offs_on_carrier(carr: bpy.types.Object, per_vert_scalar: list, normal_source_mesh: bpy.types.Mesh):
    """Store vector offsets (OFFS_ATTR) = per-vertex scalar * vertex normal."""
    me_c = carr.data
    ensure_point_attr(me_c, OFFS_ATTR, 'FLOAT_VECTOR')
    bm = bmesh.new(); bm.from_mesh(normal_source_mesh); bm.verts.ensure_lookup_table(); bm.normal_update()
    for v in bm.verts:
        d = float(per_vert_scalar[v.index]) if v.index < len(per_vert_scalar) else 0.0
        if d != 0.0:
            n = v.normal.normalized(); vec = (n.x*d, n.y*d, n.z*d)
        else:
            vec = (0.0,0.0,0.0)
        try:
            me_c.attributes[OFFS_ATTR].data[v.index].vector = vec
        except Exception:
            pass
    bm.free(); me_c.update()

def write_alphas_on_carrier(carr: bpy.types.Object, alphas_per_layer: list):
    """Store per-layer alpha weights as point-float attributes on carrier."""
    me = carr.data
    for i, arr in enumerate(alphas_per_layer):
        name = f"{ALPHA_PREFIX}{i}"
        ensure_point_attr(me, name, 'FLOAT')
        data = me.attributes[name].data
        for vi, val in enumerate(arr):
            if vi < len(data):
                data[vi].value = float(val)
    me.update()

def register():
    pass

def unregister():
    pass
