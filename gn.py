# gn.py — Geometry Nodes graph: displace ALONG NORMAL using OFFS.z as scalar
from __future__ import annotations
import bpy
from .constants import OFFS_ATTR, GN_MOD_NAME

def _make_group_interface_45(ng: bpy.types.NodeTree):
    iface = ng.interface
    iface.new_socket(name="Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
    iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

def _build_group_nodes_min(ng: bpy.types.NodeTree):
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    n_in  = nodes.new("NodeGroupInput");        n_in.location  = (-600,   0)
    n_out = nodes.new("NodeGroupOutput");       n_out.location = ( 500,   0)

    # Named attribute with our vector OFFS (we store scalar in Z)
    n_named = nodes.new("GeometryNodeInputNamedAttribute"); n_named.location = (-380, -140)
    n_named.data_type = 'FLOAT_VECTOR'
    n_named.inputs["Name"].default_value = OFFS_ATTR

    # Separate OFFS to extract Z scalar
    n_sep = nodes.new("ShaderNodeSeparateXYZ");            n_sep.location   = (-160, -140)

    # Normal → scale by OFFS.z
    n_normal = nodes.new("GeometryNodeInputNormal");       n_normal.location = (-160,   0)
    n_vmath  = nodes.new("ShaderNodeVectorMath");          n_vmath.location  = (  80,   0)
    n_vmath.operation = 'SCALE'  # Vector * Scalar

    # Apply offset
    n_set = nodes.new("GeometryNodeSetPosition");          n_set.location    = ( 280,   0)

    # Wires
    links.new(n_in.outputs["Geometry"],        n_set.inputs["Geometry"])
    links.new(n_named.outputs["Attribute"],    n_sep.inputs["Vector"])
    links.new(n_sep.outputs["Z"],              n_vmath.inputs["Scale"])
    links.new(n_normal.outputs["Normal"],      n_vmath.inputs["Vector"])
    links.new(n_vmath.outputs["Vector"],       n_set.inputs["Offset"])
    links.new(n_set.outputs["Geometry"],       n_out.inputs["Geometry"])

def _create_group(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    name = f"MLD_DisplaceGN::{obj.name}"
    ng = bpy.data.node_groups.new(name=name, type='GeometryNodeTree')
    _make_group_interface_45(ng)
    _build_group_nodes_min(ng)
    return ng

def _ensure_gn_group_for_obj(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    name = f"MLD_DisplaceGN::{obj.name}"
    ng = bpy.data.node_groups.get(name)
    if ng and ng.bl_idname != 'GeometryNodeTree':
        try: bpy.data.node_groups.remove(ng, do_unlink=True)
        except Exception: pass
        ng = None
    if ng is None:
        ng = _create_group(obj)
    else:
        # Rebuild if missing core nodes (на всякий случай)
        if "Group Input" not in ng.nodes or "Group Output" not in ng.nodes:
            _build_group_nodes_min(ng)
        else:
            # Обновим на новый вариант (если была старая простая версия)
            try:
                # проверим, есть ли SeparateXYZ
                if not any(n.bl_idname == "ShaderNodeSeparateXYZ" for n in ng.nodes):
                    _build_group_nodes_min(ng)
            except Exception:
                _build_group_nodes_min(ng)
    return ng

def ensure_gn(obj: bpy.types.Object) -> bpy.types.NodesModifier:
    ng = _ensure_gn_group_for_obj(obj)
    md = obj.modifiers.get(GN_MOD_NAME)
    if not md or md.type != 'NODES':
        md = obj.modifiers.new(GN_MOD_NAME, 'NODES')
    md.node_group = ng
    return md

def remove_gn(obj: bpy.types.Object):
    md = obj.modifiers.get(GN_MOD_NAME)
    if md:
        try: obj.modifiers.remove(md)
        except Exception: pass
