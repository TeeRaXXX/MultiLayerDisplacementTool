# Constants for names and attribute keys

# Modifier names
GN_MOD_NAME = "MLD_DisplaceGN"
SUBDIV_MOD_NAME = "MLD_RefineSubdiv"
DECIMATE_MOD_NAME = "MLD_Decimate"

# Mesh attribute names
PACK_ATTR = "MLD_Pack"       # vertex color for packed channels
OFFS_ATTR = "MLD_Offs"       # point-vector offset on carrier
ALPHA_PREFIX = "MLD_A_"      # per-layer alpha (point-float) on carrier

# Misc
EPS = 1e-8

# =============================================================================
# DEFAULT SETTINGS VALUES
# =============================================================================

# Main settings defaults
DEFAULT_ACTIVE_INDEX = 0
DEFAULT_PAINTING = False
DEFAULT_VC_PACKED = False

# Global displacement parameters defaults
DEFAULT_STRENGTH = 1.0
DEFAULT_MIDLEVEL = 0.50
DEFAULT_FILL_POWER = 1.0

# Subdivision settings defaults
DEFAULT_SUBDIV_ENABLE = False
DEFAULT_SUBDIV_TYPE = 'SIMPLE'
DEFAULT_SUBDIV_VIEW = 1
DEFAULT_SUBDIV_RENDER = 1

# Material assignment settings defaults
DEFAULT_AUTO_ASSIGN_MATERIALS = False
DEFAULT_MASK_THRESHOLD = 0.05
DEFAULT_ASSIGN_THRESHOLD = 0.05

# Preview settings defaults
DEFAULT_PREVIEW_ENABLE = True
DEFAULT_PREVIEW_BLEND = False
DEFAULT_PREVIEW_MASK_INFLUENCE = 1.0
DEFAULT_PREVIEW_CONTRAST = 2.0

# Decimate settings defaults
DEFAULT_DECIMATE_ENABLE = False
DEFAULT_DECIMATE_RATIO = 0.1

# Vertex color packing settings defaults
DEFAULT_FILL_EMPTY_VC_WHITE = False
DEFAULT_VC_ATTRIBUTE_NAME = "Color"

# Polycount tracking defaults
DEFAULT_LAST_POLY_V = 0
DEFAULT_LAST_POLY_F = 0
DEFAULT_LAST_POLY_T = 0

# Layer defaults
DEFAULT_LAYER_ENABLED = True
DEFAULT_LAYER_NAME = "New Layer"
DEFAULT_LAYER_MULTIPLIER = 1.0
DEFAULT_LAYER_BIAS = 0.0
DEFAULT_LAYER_TILING = 1.0
DEFAULT_LAYER_MASK_NAME = ""
DEFAULT_LAYER_VC_CHANNEL = 'NONE'
