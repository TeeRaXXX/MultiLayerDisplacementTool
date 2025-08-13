# settings.py — property groups for Multi Layer Displacement Tool (OPTIMIZED)
from __future__ import annotations
import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    BoolProperty, IntProperty, FloatProperty, StringProperty,
    EnumProperty, PointerProperty, CollectionProperty,
)
from .constants import (
    # Default values
    DEFAULT_ACTIVE_INDEX, DEFAULT_PAINTING, DEFAULT_VC_PACKED,
    DEFAULT_STRENGTH, DEFAULT_MIDLEVEL, DEFAULT_FILL_POWER,
    DEFAULT_SUBDIV_ENABLE, DEFAULT_SUBDIV_TYPE, DEFAULT_SUBDIV_VIEW, DEFAULT_SUBDIV_RENDER,
    DEFAULT_AUTO_ASSIGN_MATERIALS, DEFAULT_MASK_THRESHOLD, DEFAULT_ASSIGN_THRESHOLD,
    DEFAULT_PREVIEW_ENABLE, DEFAULT_PREVIEW_BLEND, DEFAULT_PREVIEW_MASK_INFLUENCE, DEFAULT_PREVIEW_CONTRAST,
    DEFAULT_DECIMATE_ENABLE, DEFAULT_DECIMATE_RATIO,
    DEFAULT_FILL_EMPTY_VC_WHITE, DEFAULT_VC_ATTRIBUTE_NAME,
    DEFAULT_LAST_POLY_V, DEFAULT_LAST_POLY_F, DEFAULT_LAST_POLY_T,
    DEFAULT_LAYER_ENABLED, DEFAULT_LAYER_NAME, DEFAULT_LAYER_MULTIPLIER, 
    DEFAULT_LAYER_BIAS, DEFAULT_LAYER_TILING, DEFAULT_LAYER_MASK_NAME, DEFAULT_LAYER_VC_CHANNEL
)

# ------------------------------------------------------------------------------
# Preview callbacks (ONLY build/remove preview material; do NOT touch displacement)
# ------------------------------------------------------------------------------

def _preview_rebuild(obj: bpy.types.Object, s: "MLD_Settings"):
    try:
        from .materials import build_heightlerp_preview_shader, remove_preview_material
    except Exception:
        return
    if not obj or obj.type != 'MESH':
        return
    if getattr(s, "preview_enable", False):
        try:
            build_heightlerp_preview_shader(
                obj, s,
                preview_influence=getattr(s, "preview_mask_influence", 1.0),
                preview_contrast=getattr(s, "preview_contrast", 1.0),
            )
        except Exception as e:
            print("[MLD] Preview rebuild failed:", e)
    else:
        remove_preview_material(obj)

def _on_toggle_preview(self, context):
    _preview_rebuild(context.object, self)

def _on_preview_param(self, context):
    if getattr(self, "preview_enable", False):
        _preview_rebuild(context.object, self)

# ------------------------------------------------------------------------------
# Layer switching callback (OPTIMIZED)
# ------------------------------------------------------------------------------

def _on_active_layer_change(self, context):
    """Fast layer switching callback - minimal operations."""
    try:
        # Быстрое переключение только если в режиме рисования
        obj = context.object
        if obj and obj.type == 'MESH' and getattr(self, 'painting', False):
            # Используем быструю версию переключения
            from .ops_masks import switch_to_active_mask_fast
            switch_to_active_mask_fast(obj, self)
            
            # Ensure mask name is set (without creating mask)
            try:
                ai = _get_active_layer_index(self)
                if 0 <= ai < len(self.layers):
                    L = self.layers[ai]
                    if not getattr(L, "mask_name", ""):
                        L.mask_name = f"MLD_Mask_{ai+1}"
            except Exception:
                pass
        # Если не в режиме рисования - не делаем ничего (экономим время)
    except Exception as e:
        print("[MLD] Fast layer switch failed:", e)

def remove_mld_materials(obj):
    """Remove MLD-generated materials from object."""
    if not obj or obj.type != 'MESH':
        return []
        
    removed = []
    materials_to_remove = []
    
    # Find MLD materials in object slots
    for i, mat in enumerate(obj.data.materials):
        if mat and mat.name.startswith("MLD_Preview::"):
            materials_to_remove.append((i, mat))
            
    # Remove from slots (in reverse order to maintain indices)
    for i, mat in reversed(materials_to_remove):
        try:
            obj.data.materials.pop(index=i)
            removed.append(mat.name)
        except Exception:
            pass
    
    # Remove unused MLD materials from data
    mld_materials = [mat for mat in bpy.data.materials 
                     if mat.name.startswith("MLD_Preview::") and mat.users == 0]
    
    for mat in mld_materials:
        try:
            bpy.data.materials.remove(mat, do_unlink=True)
            if mat.name not in removed:
                removed.append(mat.name)
        except Exception:
            pass
            
    return removed

# ------------------------------------------------------------------------------
# Per-layer settings
# ------------------------------------------------------------------------------

VC_ENUM = [
    ('NONE', "—", "No channel"),
    ('R', 'R', "Red"),
    ('G', 'G', "Green"),
    ('B', 'B', "Blue"),
    
]

class MLD_Layer(PropertyGroup):
    enabled: BoolProperty(
        name="Enabled", default=DEFAULT_LAYER_ENABLED,
        description="Enable this layer in displacement and preview",
    )
    name: StringProperty(
        name="Layer Name", default=DEFAULT_LAYER_NAME,
        description="Display name (UI). Will be replaced by Material name when set",
    )
    def _update_name_from_mat(self, context):
        if self.material and self.material.name:
            self.name = self.material.name
    material: PointerProperty(
        name="Material", type=bpy.types.Material,
        description="Material used for this layer (BaseColor for preview, Displacement->Height for height sampling)",
        update=_update_name_from_mat,
    )
    multiplier: FloatProperty(
        name="Multiplier", default=DEFAULT_LAYER_MULTIPLIER, soft_min=-8.0, soft_max=8.0,
        description="Multiply sampled height (per-layer)",
    )
    bias: FloatProperty(
        name="Bias", default=DEFAULT_LAYER_BIAS, soft_min=-1.0, soft_max=1.0,
        description="Add to sampled height (per-layer)",
    )
    tiling: FloatProperty(
        name="Tiling", default=DEFAULT_LAYER_TILING, min=1e-6, soft_min=0.01, soft_max=32.0,
        description="UV scale for this layer",
    )
    mask_name: StringProperty(
        name="Mask Attribute", default=DEFAULT_LAYER_MASK_NAME,
        description="Vertex Color attribute name used as a mask (Red channel)",
    )
    vc_channel: EnumProperty(
        name="VC Channel", items=VC_ENUM, default=DEFAULT_LAYER_VC_CHANNEL,
        description="Pack this layer into chosen vertex color channel on Pack VC",
    )

# ------------------------------------------------------------------------------
# Main settings (per object)
# ------------------------------------------------------------------------------

SUBDIV_TYPES = [
    ('SIMPLE', "Simple", "Simple (no smoothing)"),
    ('CATMULL_CLARK', "Catmull-Clark", "Smoothed subdivision"),
]

# ---- compatibility getters/setters (OPTIMIZED) ------------------------------

def _get_is_painting(self): 
    return bool(getattr(self, "painting", False))

def _set_is_painting(self, v): 
    self["painting"] = bool(v)

def _get_active_layer_index(self): 
    return int(getattr(self, "active_index", 0))

def _set_active_layer_index(self, v): 
    old_val = self.get("active_index", 0)
    new_val = int(v)
    self["active_index"] = new_val
    # Trigger mask switch ONLY if value actually changed AND we're painting
    if old_val != new_val and getattr(self, "painting", False):
        _on_active_layer_change(self, bpy.context)

def _get_auto_assign_on_recalc(self): 
    return bool(getattr(self, "auto_assign_materials", False))

def _set_auto_assign_on_recalc(self, v): 
    self["auto_assign_materials"] = bool(v)

def _get_subdiv_viewport_levels(self): 
    return int(getattr(self, "subdiv_view", 1))

def _set_subdiv_viewport_levels(self, v): 
    self["subdiv_view"] = int(v)

def _get_subdiv_render_levels(self): 
    return int(getattr(self, "subdiv_render", 1))

def _set_subdiv_render_levels(self, v): 
    self["subdiv_render"] = int(v)

def _get_fill_empty_vc_channels_with_white(self): 
    return bool(getattr(self, "fill_empty_vc_white", False))

def _set_fill_empty_vc_channels_with_white(self, v): 
    self["fill_empty_vc_white"] = bool(v)

def _get_refine_enable(self): 
    return bool(getattr(self, "subdiv_enable", False))

def _set_refine_enable(self, v): 
    self["subdiv_enable"] = bool(v)

def _get_subdiv_levels_view(self): 
    return int(getattr(self, "subdiv_view", 1))

def _set_subdiv_levels_view(self, v): 
    self["subdiv_view"] = int(v)

def _get_subdiv_levels_render(self): 
    return int(getattr(self, "subdiv_render", 1))

def _set_subdiv_levels_render(self, v): 
    self["subdiv_render"] = int(v)

def _get_preview_blend(self): 
    return bool(getattr(self, "preview_enable", False))

def _set_preview_blend(self, v): 
    self["preview_enable"] = bool(v)

def _get_mat_assign_threshold(self): 
    return float(getattr(self, "mask_threshold", 0.05))

def _set_mat_assign_threshold(self, v): 
    self["mask_threshold"] = float(v)

# ------------------------------------------------------------------------------
class MLD_Settings(PropertyGroup):
    # UI / runtime with OPTIMIZED layer change callback
    active_index: IntProperty(
        name="Active Layer", default=DEFAULT_ACTIVE_INDEX, min=0,
        update=_on_active_layer_change
    )
    painting: BoolProperty(name="Painting Mode", default=DEFAULT_PAINTING)

    # Global displacement parameters
    strength: FloatProperty(
        name="Global Strength", default=DEFAULT_STRENGTH, soft_min=-5.0, soft_max=5.0,
        description="Overall displacement strength applied to the height result",
    )
    midlevel: FloatProperty(
        name="Midlevel", default=DEFAULT_MIDLEVEL, min=0.0, max=1.0,
        description="Reference midlevel (subtracted from blended height before strength)",
    )
    fill_power: FloatProperty(
        name="Fill Power", default=DEFAULT_FILL_POWER, min=0.0, soft_max=4.0,
        description="Controls how aggressively higher layers 'fill' over lower layers",
    )

    # Layers
    layers: CollectionProperty(type=MLD_Layer)
    def _layers_len(self):  # convenience accessor
        return len(self.layers)

    # Subdivision refine (preview helper)
    subdiv_enable: BoolProperty(
        name="Enable Subdivision Refine", default=DEFAULT_SUBDIV_ENABLE,
        description="Enable Subdivision modifier (preview helper) - applied on Recalculate",
        # НЕТ update callback - изменения применяются только при Recalculate
    )
    subdiv_type: EnumProperty(
        name="Type", items=SUBDIV_TYPES, default=DEFAULT_SUBDIV_TYPE,
        description="Subdivision type for refine step",
        # НЕТ update callback
    )
    subdiv_view: IntProperty(
        name="Viewport Levels", default=DEFAULT_SUBDIV_VIEW, min=0, soft_max=4,
        description="Subdivision levels in viewport",
        # НЕТ update callback
    )
    subdiv_render: IntProperty(
        name="Render Levels", default=DEFAULT_SUBDIV_RENDER, min=0, soft_max=4,
        description="Subdivision levels in render",
        # НЕТ update callback
    )

    # Materials auto-assign after recalc
    auto_assign_materials: BoolProperty(
        name="Auto assign on Recalculate", default=DEFAULT_AUTO_ASSIGN_MATERIALS,
        description="Assign object polygons to layer materials using displacement result after Recalculate",
    )
    # Thresholds (two names kept for cross-module compatibility)
    mask_threshold: FloatProperty(
        name="Mask Threshold", default=DEFAULT_MASK_THRESHOLD, min=0.0, max=1.0,
        description="Minimum visible contribution to assign a polygon to layer's material",
    )
    assign_threshold: FloatProperty(
        name="Assign Threshold (compat)", default=DEFAULT_ASSIGN_THRESHOLD, min=0.0, max=1.0,
        description="Compatibility alias for modules that read a different property name",
    )

    # Preview (materials) — HeightLerp style
    preview_enable: BoolProperty(
        name="Preview blend (materials)", default=DEFAULT_PREVIEW_ENABLE,
        description="Build and assign a HeightLerp-like preview material for the object (applied on Recalculate)",
        update=_on_toggle_preview,  # Только toggle - включение/выключение
    )
    preview_blend: BoolProperty(
        name="Simple Blend Mode", default=DEFAULT_PREVIEW_BLEND,
        description="Use simple additive blend instead of HeightLerp (all layers visible)",
        update=_on_preview_param,  # Перестраиваем превью при изменении
    )
    preview_mask_influence: FloatProperty(
        name="Preview Mask Influence", default=DEFAULT_PREVIEW_MASK_INFLUENCE, min=0.0, soft_max=2.0,
        description="How strongly paint mask affects preview blend",
        # НЕТ update callback - применяется при Recalculate
    )
    preview_contrast: FloatProperty(
        name="Preview Contrast", default=DEFAULT_PREVIEW_CONTRAST, min=0.0, soft_max=8.0,
        description="How strongly height difference sharpens preview blend",
        # НЕТ update callback - применяется при Recalculate
    )

    # Decimate (preview)
    decimate_enable: BoolProperty(
        name="Enable", default=DEFAULT_DECIMATE_ENABLE,
        description="Enable decimate for preview (applied on Recalculate only)",
        # НЕТ update callback - изменения применяются только при Recalculate
    )
    decimate_ratio: FloatProperty(
        name="Ratio", default=DEFAULT_DECIMATE_RATIO, min=0.0, max=1.0,
        description="Decimation ratio for preview mesh (smaller = stronger reduction)",
        # НЕТ update callback
    )

    # Pack Vertex Colors (moved to bake section)
    fill_empty_vc_white: BoolProperty(
        name="Fill empty VC channels with white", default=DEFAULT_FILL_EMPTY_VC_WHITE,
        description="When packing VC, fill unassigned channels with white (1.0). If all channels are used, this is ignored",
    )
    vc_attribute_name: StringProperty(
        name="VC Attribute Name", default=DEFAULT_VC_ATTRIBUTE_NAME,
        description="Name of the vertex color attribute to pack into (e.g., 'Col', 'Color', 'VertexColor')",
    )
    
    # Bake options
    bake_pack_vc: BoolProperty(
        name="Pack to Vertex Colors", default=False,
        description="Pack layer masks to vertex colors during bake operation",
    )
    bake_vc_attribute_name: StringProperty(
        name="Bake VC Attribute Name", default=DEFAULT_VC_ATTRIBUTE_NAME,
        description="Name of the vertex color attribute to pack into during bake (e.g., 'Col', 'Color', 'VertexColor')",
    )
    
    # Polycount tracking (for UI display)
    last_poly_v: IntProperty(
        name="Last Vertex Count", default=DEFAULT_LAST_POLY_V,
        description="Last calculated vertex count (for UI display)",
    )
    last_poly_f: IntProperty(
        name="Last Face Count", default=DEFAULT_LAST_POLY_F,
        description="Last calculated face count (for UI display)", 
    )
    last_poly_t: IntProperty(
        name="Last Triangle Count", default=DEFAULT_LAST_POLY_T,
        description="Last calculated triangle count (for UI display)",
    )

    # helper to mirror thresholds if needed
    def sync_thresholds(self):
        try:
            self.assign_threshold = self.mask_threshold
        except Exception:
            pass

    # ---------------- Aliases for backward compatibility (OPTIMIZED) -----------
    is_painting: BoolProperty(
        name="Painting (alias)",
        get=_get_is_painting, set=_set_is_painting,
        description="Alias of 'painting' for older UI code",
    )
    active_layer_index: IntProperty(
        name="Active Layer (alias)",
        get=_get_active_layer_index, set=_set_active_layer_index,
        description="Alias of 'active_index' for older UI code",
    )
    auto_assign_on_recalc: BoolProperty(
        name="Auto assign on Recalculate (alias)",
        get=_get_auto_assign_on_recalc, set=_set_auto_assign_on_recalc,
        description="Alias of 'auto_assign_materials' for older UI code",
    )
    subdiv_viewport_levels: IntProperty(
        name="Viewport Levels (alias)", min=0, soft_max=4,
        get=_get_subdiv_viewport_levels, set=_set_subdiv_viewport_levels,
        description="Alias of 'subdiv_view' for older UI code",
    )
    subdiv_render_levels: IntProperty(
        name="Render Levels (alias)", min=0, soft_max=4,
        get=_get_subdiv_render_levels, set=_set_subdiv_render_levels,
        description="Alias of 'subdiv_render' for older UI code",
    )
    fill_empty_vc_channels_with_white: BoolProperty(
        name="Fill empty VC channels with white (alias)",
        get=_get_fill_empty_vc_channels_with_white,
        set=_set_fill_empty_vc_channels_with_white,
        description="Alias of 'fill_empty_vc_white' for older UI code",
    )
    # Current UI aliases:
    refine_enable: BoolProperty(
        name="Refine enable (alias)",
        get=_get_refine_enable, set=_set_refine_enable,
        description="Alias of 'subdiv_enable' for current UI",
    )
    subdiv_levels_view: IntProperty(
        name="Viewport Levels (alias)",
        min=0, soft_max=4,
        get=_get_subdiv_levels_view, set=_set_subdiv_levels_view,
        description="Alias of 'subdiv_view' for current UI",
    )
    subdiv_levels_render: IntProperty(
        name="Render Levels (alias)",
        min=0, soft_max=4,
        get=_get_subdiv_levels_render, set=_set_subdiv_levels_render,
        description="Alias of 'subdiv_render' for current UI",
    )
    preview_blend: BoolProperty(
        name="Preview blend (alias)",
        get=_get_preview_blend, set=_set_preview_blend,
        description="Alias of 'preview_enable' for current UI",
    )
    mat_assign_threshold: FloatProperty(
        name="Mask Threshold (alias)",
        min=0.0, max=1.0,
        get=_get_mat_assign_threshold, set=_set_mat_assign_threshold,
        description="Alias of 'mask_threshold' for current UI",
    )

# ------------------------------------------------------------------------------
# Registration helpers
# ------------------------------------------------------------------------------

classes = (
    MLD_Layer,
    MLD_Settings,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    # Per-object settings (primary)
    bpy.types.Object.mld_settings = PointerProperty(type=MLD_Settings)
    # Optional scene-level settings (fallback for some ops)
    if not hasattr(bpy.types.Scene, "mld_settings"):
        bpy.types.Scene.mld_settings = PointerProperty(type=MLD_Settings)

def unregister():
    # Remove pointers first
    if hasattr(bpy.types.Object, "mld_settings"):
        del bpy.types.Object.mld_settings
    if hasattr(bpy.types.Scene, "mld_settings"):
        del bpy.types.Scene.mld_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


# --- Compatibility aliases expected by operators ---
try:
    def _mld_get_active_layer_index(self):
        return int(getattr(self, "active_index", 0))
    def _mld_set_active_layer_index(self, v):
        setattr(self, "active_index", int(v))
    MLD_Settings.active_layer_index = property(_mld_get_active_layer_index, _mld_set_active_layer_index)
except Exception:
    pass
try:
    def _mld_get_is_painting(self):
        return bool(getattr(self, "painting", False))
    def _mld_set_is_painting(self, v):
        setattr(self, "painting", bool(v))
    MLD_Settings.is_painting = property(_mld_get_is_painting, _mld_set_is_painting)
except Exception:
    pass