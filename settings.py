# settings.py — ОБНОВЛЕННАЯ ВЕРСИЯ с новыми режимами смешивания
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
    DEFAULT_AUTO_ASSIGN_MATERIALS, DEFAULT_MASK_THRESHOLD, DEFAULT_ASSIGN_THRESHOLD,
    DEFAULT_PREVIEW_ENABLE, DEFAULT_PREVIEW_BLEND, DEFAULT_PREVIEW_MASK_INFLUENCE, DEFAULT_PREVIEW_CONTRAST,
    DEFAULT_DECIMATE_ENABLE, DEFAULT_DECIMATE_RATIO,
    DEFAULT_FILL_EMPTY_VC_WHITE, DEFAULT_VC_ATTRIBUTE_NAME,
    DEFAULT_LAST_POLY_V, DEFAULT_LAST_POLY_F, DEFAULT_LAST_POLY_T,
    DEFAULT_LAYER_ENABLED, DEFAULT_LAYER_NAME, DEFAULT_LAYER_MULTIPLIER, 
    DEFAULT_LAYER_BIAS, DEFAULT_LAYER_TILING, DEFAULT_LAYER_MASK_NAME, DEFAULT_LAYER_VC_CHANNEL,
    DEFAULT_PACK_TO_TEXTURE_MASK, DEFAULT_TEXTURE_MASK_NAME, DEFAULT_TEXTURE_MASK_UV, DEFAULT_TEXTURE_MASK_RESOLUTION,
    TEXTURE_RESOLUTION_OPTIONS
)

# ------------------------------------------------------------------------------
# Preview callbacks
# ------------------------------------------------------------------------------

def _preview_rebuild(obj: bpy.types.Object, s: "MLD_Settings"):
    try:
        from .materials import build_heightlerp_preview_shader_new, remove_preview_material
    except Exception:
        return
    if not obj or obj.type != 'MESH':
        return
    if getattr(s, "preview_enable", False):
        try:
            build_heightlerp_preview_shader_new(
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

# ------------------------------------------------------------------------------
# Per-layer settings (ОБНОВЛЕННЫЕ)
# ------------------------------------------------------------------------------

VC_ENUM = [
    ('NONE', "—", "No channel"),
    ('R', 'R', "Red"),
    ('G', 'G', "Green"),
    ('B', 'B', "Blue"),
    ('A', 'A', "Alpha"),
]

# НОВЫЕ режимы смешивания (добавлен SIMPLE)
BLEND_MODES = [
    ('SIMPLE', "Simple", "Direct mask blending (lerp by mask only)"),
    ('HEIGHT_BLEND', "Height Blend", "Substance Designer style height blending"),
    ('SWITCH', "Switch", "Simple lerp/switch blending"),
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
    
    # ОБНОВЛЕННЫЕ параметры height (переименованы для ясности)
    strength: FloatProperty(
        name="Height Strength", default=DEFAULT_LAYER_MULTIPLIER, soft_min=-8.0, soft_max=8.0,
        description="Multiply height values for this layer (applied before blending)",
    )
    bias: FloatProperty(
        name="Height Bias", default=DEFAULT_LAYER_BIAS, soft_min=-1.0, soft_max=1.0,
        description="Add to height values for this layer (applied before blending)",
    )
    
    # ОБНОВЛЕННЫЕ настройки смешивания (default изменен на SIMPLE)
    blend_mode: EnumProperty(
        name="Blend Mode", items=BLEND_MODES, default='SIMPLE',
        description="How this layer blends with layers below it",
    )
    
    # Height blend specific
    height_offset: FloatProperty(
        name="Height Offset", default=0.5, min=0.0, max=1.0,
        description="Height threshold for blending (0=no blend, 1=full override)",
    )
    
    # Switch blend specific  
    switch_opacity: FloatProperty(
        name="Switch Opacity", default=0.5, min=0.0, max=1.0,
        description="Opacity for switch blending (0=hidden, 1=full)",
    )
    
    # Остальные настройки без изменений
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
    
    # COMPATIBILITY: Keep old property names as aliases
    multiplier: FloatProperty(
        name="Multiplier (deprecated)", default=DEFAULT_LAYER_MULTIPLIER,
        get=lambda self: self.strength,
        set=lambda self, value: setattr(self, 'strength', value),
        description="Deprecated: use 'strength' instead",
    )

# ------------------------------------------------------------------------------
# Main settings (per object) - БЕЗ ИЗМЕНЕНИЙ
# ------------------------------------------------------------------------------



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



def _get_fill_empty_vc_channels_with_white(self): 
    return bool(getattr(self, "fill_empty_vc_white", False))

def _set_fill_empty_vc_channels_with_white(self, v): 
    self["fill_empty_vc_white"] = bool(v)



def _get_preview_blend(self): 
    return bool(getattr(self, "preview_enable", False))

def _set_preview_blend(self, v): 
    self["preview_enable"] = bool(v)

def _get_mat_assign_threshold(self): 
    return float(getattr(self, "mask_threshold", 0.05))

def _set_mat_assign_threshold(self, v): 
    self["mask_threshold"] = float(v)

def _get_uv_layers_items(self, context):
    """Get list of available UV layers for the current object."""
    items = []
    
    obj = context.object
    if obj and obj.type == 'MESH' and obj.data:
        me = obj.data
        if hasattr(me, "uv_layers"):
            for uv in me.uv_layers:
                items.append((uv.name, uv.name, f"UV layer: {uv.name}"))
    
    # If no UV layers found, add default
    if not items:
        items.append(("UVMap", "UVMap", "Default UV layer"))
    
    return items

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
        description="DEPRECATED: no longer used in new blending system",
    )

    # Layers
    layers: CollectionProperty(type=MLD_Layer)
    def _layers_len(self):  # convenience accessor
        return len(self.layers)



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
        update=_on_toggle_preview,
    )
    preview_blend: BoolProperty(
        name="Simple Blend Mode", default=DEFAULT_PREVIEW_BLEND,
        description="Use simple additive blend instead of HeightLerp (all layers visible)",
        update=_on_preview_param,
    )
    preview_mask_influence: FloatProperty(
        name="Preview Mask Influence", default=DEFAULT_PREVIEW_MASK_INFLUENCE, min=0.0, soft_max=2.0,
        description="How strongly paint mask affects preview blend",
    )
    preview_contrast: FloatProperty(
        name="Preview Contrast", default=DEFAULT_PREVIEW_CONTRAST, min=0.0, soft_max=8.0,
        description="How strongly height difference sharpens preview blend",
    )

    # Decimate (preview)
    decimate_enable: BoolProperty(
        name="Enable", default=DEFAULT_DECIMATE_ENABLE,
        description="Enable decimate for preview (applied on Recalculate only)",
    )
    decimate_ratio: FloatProperty(
        name="Ratio", default=DEFAULT_DECIMATE_RATIO, min=0.0, max=1.0,
        description="Decimation ratio for preview mesh (smaller = stronger reduction)",
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
    
    # Pack to Texture Mask options
    pack_to_texture_mask: BoolProperty(
        name="Pack to Texture Mask", default=DEFAULT_PACK_TO_TEXTURE_MASK,
        description="Pack layer masks to texture mask during bake operation",
    )
    texture_mask_name: StringProperty(
        name="Texture Mask Name", default=DEFAULT_TEXTURE_MASK_NAME,
        description="Name of the texture to create for mask packing",
    )
    texture_mask_uv: EnumProperty(
        name="UV Layer", 
        items=_get_uv_layers_items,
        description="UV layer to use for texture mask baking",
    )
    texture_mask_resolution: EnumProperty(
        name="Texture Mask Resolution",
        items=TEXTURE_RESOLUTION_OPTIONS,
        default=DEFAULT_TEXTURE_MASK_RESOLUTION,
        description="Resolution of the texture mask",
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

    # For vc_packed state
    vc_packed: BoolProperty(
        name="VC Packed", default=DEFAULT_VC_PACKED,
        description="Whether vertex colors have been packed",
    )
    
    # For texture_mask_packed state
    texture_mask_packed: BoolProperty(
        name="Texture Mask Packed", default=False,
        description="Whether texture mask has been packed",
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

    fill_empty_vc_channels_with_white: BoolProperty(
        name="Fill empty VC channels with white (alias)",
        get=_get_fill_empty_vc_channels_with_white,
        set=_set_fill_empty_vc_channels_with_white,
        description="Alias of 'fill_empty_vc_white' for older UI code",
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