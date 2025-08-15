bl_info = {
    "name": "Multi Layer Displacement Tool",
    "author": "Igor Tikhomirov",
    "version": (1, 0, 0),  # Увеличена версия
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > MLD Tool",
    "description": "Height-fill multi-layer displacement tool (modular).",
    "category": "Object",
}

import bpy, importlib, traceback

_SUBMODULES = [
    ".constants",".utils",".attrs",".sampling",".materials",".heightfill",".gn",".gn_subdiv",".gn_multires",
    ".settings",".ops_layers",".ops_masks",".ops_materials",".ops_assign_from_disp",
    ".ops_pipeline",".ops_reset_all",".ops_reset",".ops_bake",".ops_pack",
    ".ops_settings_io",".ops_vc_channels",".ui",
]

_loaded = []

def _attach_pointer():
    try:
        from .settings import MLD_Settings
        if not hasattr(bpy.types.Object, "mld_settings"):
            bpy.types.Object.mld_settings = bpy.props.PointerProperty(type=MLD_Settings)
    except Exception as e:
        print("[MLD] attach pointer failed:", e); traceback.print_exc()

def register():
    global _loaded; _loaded = []
    for name in _SUBMODULES:
        try:
            m = importlib.import_module(__name__ + name)
            importlib.reload(m)
            if hasattr(m, "register"): m.register()
            _loaded.append(m)
        except Exception as e:
            print(f"[MLD] Register error in {name}: {e}"); traceback.print_exc()
    _attach_pointer()

def unregister():
    try:
        if hasattr(bpy.types.Object, "mld_settings"):
            del bpy.types.Object.mld_settings
    except Exception: pass
    for m in reversed(_loaded):
        try:
            if hasattr(m, "unregister"): m.unregister()
        except Exception as e:
            print(f"[MLD] Unregister error in {getattr(m, '__name__', m)}: {e}"); traceback.print_exc()
    _loaded.clear()