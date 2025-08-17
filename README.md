# MultiLayerDisplacementTool

The Multi Layer Displacement Tool (MLD) is a sophisticated Blender addon for creating complex displacement effects by blending multiple material layers with mask-based control. It uses a "HeightFill" algorithm to intelligently blend displacement maps from different materials based on painted vertex color masks.

## Features

- **Multi-layer displacement blending** with intelligent height-fill algorithm
- **Vertex color mask painting** for precise layer control
- **Material assignment** from displacement maps
- **Geometry Nodes integration** for real-time displacement preview
- **Decimation tools** for optimization
- **Vertex color packing** for efficient storage
- **Texture mask export** capabilities
- **Polycount tracking** and optimization tools

## Installation

1. Download the addon zip file
2. In Blender, go to **Edit > Preferences > Add-ons**
3. Click **Install** and select the addon folder
4. Enable the addon by checking the box next to "Object: Multi Layer Displacement Tool"

## Quick Start Guide

### 1. Setup Your Object
- Select a mesh object in the 3D viewport
- The MLD panel will appear in the 3D View sidebar (press N if not visible)
- Go to the **MLD Tool** tab

### 2. Create and Connect Materials
- **Create Materials**: Each layer needs a material with displacement maps
- **Connect Height Maps**: The addon automatically detects displacement connections in materials
- **Material Setup**: Use Principled BSDF with displacement input or displacement nodes
- **Height Map Detection**: The addon looks for:
  - Displacement input in Material Output node
  - Displacement or Bump nodes connected to displacement
  - Base Color textures as fallback

### 3. Create Layers
- Click **Add Layer** to create your first displacement layer
- Each layer can have its own material and displacement settings
- Use the layer list to manage multiple layers

### 4. Paint Masks
- Select a layer in the list
- Click **Start Painting** to enter mask painting mode
- Paint on your mesh using vertex colors to control layer influence
- Use the brush settings to adjust painting behavior
- Click **Stop Painting** when finished

### 5. Assign Materials
- Select a layer and click **Assign from Displacement**
- This will automatically assign materials based on displacement values
- Adjust the assignment threshold as needed

### 6. Apply Displacement
- Click **Apply Pipeline** to generate the final displacement
- The addon will create Geometry Nodes modifiers for real-time preview
- Use **Bake** to create final geometry if needed
