# On-the-fly validation (no writes during draw)
import bpy
from .utils import active_obj
from .sampling import find_image_and_uv_from_displacement

def collect_validation(obj: bpy.types.Object):
    """
    Return list of tuples (kind, text) where kind is 'ERROR' or 'WARN'.
    Pure function: does not modify ID data, safe to call from UI draw.
    """
    msgs=[]
    if not obj or obj.type!='MESH':
        return msgs

    s=obj.mld_settings
    if not obj.data.uv_layers:
        msgs.append(('ERROR', "No UV map on mesh. Add a UV layer."))
    if len(s.layers)==0:
        msgs.append(('WARN', "No layers. Add at least one layer to proceed."))

    # Per-layer checks (top to bottom for clarity)
    for i,L in enumerate(s.layers):
        prefix=f"Layer {i+1} / {L.name}: "
        if not L.enabled:
            msgs.append(('WARN', prefix+"Layer disabled."))
            continue
        if not L.material:
            msgs.append(('WARN', prefix+"No material selected."))
        else:
            img, uv = find_image_and_uv_from_displacement(L.material)
            if img is None:
                msgs.append(('ERROR', prefix+"Material has no Displacement texture wired to Material Output > Displacement."))
        if not L.mask_name:
            msgs.append(('WARN', prefix+"No mask attribute set. Use Create/Activate to create one."))
        else:
            # not error if attribute missing; user может создать позже
            pass

    return msgs
