# gn.py — Geometry Nodes граф для чтения displacement из carrier mesh

from __future__ import annotations
import bpy
from .constants import OFFS_ATTR, GN_MOD_NAME

def _make_group_interface_45(ng: bpy.types.NodeTree):
    iface = ng.interface
    iface.new_socket(name="Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
    iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

def _build_carrier_reader_graph(ng: bpy.types.NodeTree, obj: bpy.types.Object):
    """Build GN graph that reads displacement from carrier mesh."""
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    # Input/Output
    n_in  = nodes.new("NodeGroupInput");        n_in.location  = (-800,   0)
    n_out = nodes.new("NodeGroupOutput");       n_out.location = ( 800,   0)

    # Object Info node to read carrier mesh
    n_obj_info = nodes.new("GeometryNodeObjectInfo"); n_obj_info.location = (-600, -200)
    n_obj_info.transform_space = 'ORIGINAL'
    
    # Set carrier object
    carrier_name = f"MLD_Carrier::{obj.name}"
    carrier_obj = bpy.data.objects.get(carrier_name)
    if carrier_obj:
        n_obj_info.inputs["Object"].default_value = carrier_obj
        print(f"[MLD] GN linked to carrier: {carrier_name}")

    # Sample Index node to transfer vertex data
    n_sample_index = nodes.new("GeometryNodeSampleIndex"); n_sample_index.location = (-400, 0)
    n_sample_index.data_type = 'FLOAT_VECTOR'
    n_sample_index.domain = 'POINT'

    # Named attribute for OFFS on carrier
    n_named = nodes.new("GeometryNodeInputNamedAttribute"); n_named.location = (-600, -400)
    n_named.data_type = 'FLOAT_VECTOR'
    n_named.inputs["Name"].default_value = OFFS_ATTR

    # Index node for vertex indices
    n_index = nodes.new("GeometryNodeInputIndex"); n_index.location = (-600, -100)

    # Separate XYZ to get Z component (scalar displacement)
    n_sep = nodes.new("ShaderNodeSeparateXYZ"); n_sep.location = (-200, 0)

    # Normal input
    n_normal = nodes.new("GeometryNodeInputNormal"); n_normal.location = (-200, 200)

    # Vector Math to scale normal by displacement
    n_vmath = nodes.new("ShaderNodeVectorMath"); n_vmath.location = (0, 100)
    n_vmath.operation = 'SCALE'

    # Set Position to apply displacement
    n_set = nodes.new("GeometryNodeSetPosition"); n_set.location = (400, 0)

    # Connections
    links.new(n_in.outputs["Geometry"], n_set.inputs["Geometry"])
    links.new(n_in.outputs["Geometry"], n_sample_index.inputs["Geometry"])
    
    # Connect carrier geometry and attributes
    links.new(n_obj_info.outputs["Geometry"], n_sample_index.inputs["Geometry"])
    links.new(n_named.outputs["Attribute"], n_sample_index.inputs["Value"])
    links.new(n_index.outputs["Index"], n_sample_index.inputs["Index"])
    
    # Process displacement
    links.new(n_sample_index.outputs["Value"], n_sep.inputs["Vector"])
    links.new(n_sep.outputs["Z"], n_vmath.inputs["Scale"])
    links.new(n_normal.outputs["Normal"], n_vmath.inputs["Vector"])
    links.new(n_vmath.outputs["Vector"], n_set.inputs["Offset"])
    
    # Output
    links.new(n_set.outputs["Geometry"], n_out.inputs["Geometry"])

def _build_simple_graph(ng: bpy.types.NodeTree):
    """Fallback simple graph if carrier not available."""
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    n_in  = nodes.new("NodeGroupInput");        n_in.location  = (-600,   0)
    n_out = nodes.new("NodeGroupOutput");       n_out.location = ( 500,   0)

    # Named attribute with OFFS from object itself
    n_named = nodes.new("GeometryNodeInputNamedAttribute"); n_named.location = (-380, -140)
    n_named.data_type = 'FLOAT_VECTOR'
    n_named.inputs["Name"].default_value = OFFS_ATTR

    # Separate XYZ
    n_sep = nodes.new("ShaderNodeSeparateXYZ"); n_sep.location = (-160, -140)

    # Normal → scale by OFFS.z
    n_normal = nodes.new("GeometryNodeInputNormal"); n_normal.location = (-160, 0)
    n_vmath  = nodes.new("ShaderNodeVectorMath");    n_vmath.location  = (  80, 0)
    n_vmath.operation = 'SCALE'

    # Apply offset
    n_set = nodes.new("GeometryNodeSetPosition"); n_set.location = ( 280, 0)

    # Connections
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
    
    # Try carrier-based approach first
    carrier_name = f"MLD_Carrier::{obj.name}"
    carrier_obj = bpy.data.objects.get(carrier_name)
    
    if carrier_obj:
        print(f"[MLD] Building carrier-based GN graph")
        _build_carrier_reader_graph(ng, obj)
    else:
        print(f"[MLD] Building simple GN graph (no carrier)")
        _build_simple_graph(ng)
    
    return ng

def _ensure_gn_group_for_obj(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    name = f"MLD_DisplaceGN::{obj.name}"
    ng = bpy.data.node_groups.get(name)
    
    if ng and ng.bl_idname != 'GeometryNodeTree':
        try: 
            bpy.data.node_groups.remove(ng, do_unlink=True)
        except Exception: 
            pass
        ng = None
    
    if ng is None:
        ng = _create_group(obj)
    else:
        # Rebuild graph to update carrier reference
        carrier_name = f"MLD_Carrier::{obj.name}"
        carrier_obj = bpy.data.objects.get(carrier_name)
        
        # Check if we need to switch between carrier/simple modes
        has_obj_info = any(n.bl_idname == "GeometryNodeObjectInfo" for n in ng.nodes)
        
        if carrier_obj and not has_obj_info:
            print(f"[MLD] Rebuilding GN graph for carrier mode")
            _build_carrier_reader_graph(ng, obj)
        elif not carrier_obj and has_obj_info:
            print(f"[MLD] Rebuilding GN graph for simple mode")
            _build_simple_graph(ng)
        elif carrier_obj and has_obj_info:
            # Update carrier object reference
            for node in ng.nodes:
                if node.bl_idname == "GeometryNodeObjectInfo":
                    node.inputs["Object"].default_value = carrier_obj
                    print(f"[MLD] Updated GN carrier reference")
                    break
    
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
        try: 
            obj.modifiers.remove(md)
        except Exception: 
            pass# Диагностика проблемы с выдавливанием
# Добавить в gn.py в функцию ensure_gn():

def ensure_gn(obj: bpy.types.Object) -> bpy.types.NodesModifier:
    ng = _ensure_gn_group_for_obj(obj)
    md = obj.modifiers.get(GN_MOD_NAME)
    if not md or md.type != 'NODES':
        md = obj.modifiers.new(GN_MOD_NAME, 'NODES')
    md.node_group = ng
    
    # ДИАГНОСТИКА: проверим что carrier существует и имеет данные
    carrier_name = f"MLD_Carrier::{obj.name}"
    carrier_obj = bpy.data.objects.get(carrier_name)
    
    if carrier_obj:
        print(f"[MLD] Carrier found: {carrier_name}")
        carrier_mesh = carrier_obj.data
        offs_attr = carrier_mesh.attributes.get(OFFS_ATTR)
        
        if offs_attr:
            # Проверим есть ли реальные данные в carrier
            non_zero_count = 0
            for data in offs_attr.data:
                if abs(data.vector.z) > 0.001:  # Z component is displacement
                    non_zero_count += 1
            
            print(f"[MLD] Carrier has {non_zero_count}/{len(offs_attr.data)} non-zero displacement values")
            
            if non_zero_count > 0:
                # Sample first few values
                sample_values = []
                for i in range(min(5, len(offs_attr.data))):
                    sample_values.append(offs_attr.data[i].vector.z)
                print(f"[MLD] Sample displacement values: {sample_values}")
            else:
                print(f"[MLD] ⚠ WARNING: Carrier has no displacement data!")
        else:
            print(f"[MLD] ⚠ WARNING: Carrier missing {OFFS_ATTR} attribute!")
    else:
        print(f"[MLD] ⚠ WARNING: Carrier object not found: {carrier_name}")
    
    return md

# Также добавить проверку в _build_carrier_reader_graph():

def _build_carrier_reader_graph(ng: bpy.types.NodeTree, obj: bpy.types.Object):
    """Build GN graph that reads displacement from carrier mesh."""
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    # Input/Output
    n_in  = nodes.new("NodeGroupInput");        n_in.location  = (-800,   0)
    n_out = nodes.new("NodeGroupOutput");       n_out.location = ( 800,   0)

    # Object Info node to read carrier mesh
    n_obj_info = nodes.new("GeometryNodeObjectInfo"); n_obj_info.location = (-600, -200)
    n_obj_info.transform_space = 'ORIGINAL'
    
    # Set carrier object
    carrier_name = f"MLD_Carrier::{obj.name}"
    carrier_obj = bpy.data.objects.get(carrier_name)
    if carrier_obj:
        n_obj_info.inputs["Object"].default_value = carrier_obj
        print(f"[MLD] GN linked to carrier: {carrier_name}")
        
        # ДИАГНОСТИКА: проверим что у carrier есть данные
        carrier_mesh = carrier_obj.data
        offs_attr = carrier_mesh.attributes.get(OFFS_ATTR)
        if offs_attr:
            non_zero = sum(1 for d in offs_attr.data if abs(d.vector.z) > 0.001)
            print(f"[MLD] Carrier in GN setup has {non_zero} non-zero displacements")
        else:
            print(f"[MLD] ⚠ Carrier in GN setup missing displacement attribute!")
    else:
        print(f"[MLD] ⚠ Carrier not found for GN: {carrier_name}")

    # Sample Index node to transfer vertex data
    n_sample_index = nodes.new("GeometryNodeSampleIndex"); n_sample_index.location = (-400, 0)
    n_sample_index.data_type = 'FLOAT_VECTOR'
    n_sample_index.domain = 'POINT'

    # Named attribute for OFFS on carrier
    n_named = nodes.new("GeometryNodeInputNamedAttribute"); n_named.location = (-600, -400)
    n_named.data_type = 'FLOAT_VECTOR'
    n_named.inputs["Name"].default_value = OFFS_ATTR

    # Index node for vertex indices
    n_index = nodes.new("GeometryNodeInputIndex"); n_index.location = (-600, -100)

    # Separate XYZ to get Z component (scalar displacement)
    n_sep = nodes.new("ShaderNodeSeparateXYZ"); n_sep.location = (-200, 0)

    # Normal input
    n_normal = nodes.new("GeometryNodeInputNormal"); n_normal.location = (-200, 200)

    # Vector Math to scale normal by displacement
    n_vmath = nodes.new("ShaderNodeVectorMath"); n_vmath.location = (0, 100)
    n_vmath.operation = 'SCALE'

    # Set Position to apply displacement
    n_set = nodes.new("GeometryNodeSetPosition"); n_set.location = (400, 0)

    # Connections
    links.new(n_in.outputs["Geometry"], n_set.inputs["Geometry"])
    links.new(n_in.outputs["Geometry"], n_sample_index.inputs["Geometry"])
    
    # Connect carrier geometry and attributes
    links.new(n_obj_info.outputs["Geometry"], n_sample_index.inputs["Geometry"])
    links.new(n_named.outputs["Attribute"], n_sample_index.inputs["Value"])
    links.new(n_index.outputs["Index"], n_sample_index.inputs["Index"])
    
    # Process displacement
    links.new(n_sample_index.outputs["Value"], n_sep.inputs["Vector"])
    links.new(n_sep.outputs["Z"], n_vmath.inputs["Scale"])
    links.new(n_normal.outputs["Normal"], n_vmath.inputs["Vector"])
    links.new(n_vmath.outputs["Vector"], n_set.inputs["Offset"])
    
    # Output
    links.new(n_set.outputs["Geometry"], n_out.inputs["Geometry"])
    
    print(f"[MLD] ✓ Carrier reader graph built with diagnostics")