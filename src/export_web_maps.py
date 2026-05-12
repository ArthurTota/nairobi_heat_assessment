import os
import json
import numpy as np
import matplotlib.pyplot as plt
from pyproj import Transformer
from src.adaptive_capacity_helper import PROXIMITY_CMAP, RESULTS_DIR

def export_raster_for_web(raster, grid, name, cmap=None, vmin=0, vmax=1, output_dir=None):
    """
    Exports a 2D numpy array (raster) as a transparent PNG image and generates 
    a metadata.json with lat/lon coordinates for MapLibre/Mapbox GL JS image overlay.
    """
    if cmap is None:
        cmap = PROXIMITY_CMAP
        
    if output_dir is None:
        output_dir = os.path.join(RESULTS_DIR, 'web')
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Export the PNG image
    cmap_copy = cmap(np.arange(cmap.N))
    cmap_copy = plt.matplotlib.colors.ListedColormap(cmap_copy)
    cmap_copy.set_bad(color='white', alpha=0.0)
    
    png_path = os.path.join(output_dir, f"{name}.png")
    plt.imsave(png_path, raster, cmap=cmap_copy, vmin=vmin, vmax=vmax, origin='upper', format='png')
    
    # 2. Compute the 4 corners in EPSG:4326
    minx, miny, maxx, maxy = grid['bounds']
    utm_corners = [(minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny)]
    
    transformer = Transformer.from_crs(grid['crs'], "EPSG:4326", always_xy=True)
    latlon_corners = [transformer.transform(x, y) for x, y in utm_corners]
        
    # 3. Save metadata.json
    metadata_path = os.path.join(output_dir, "metadata.json")
    metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            try:
                metadata = json.load(f)
            except json.JSONDecodeError:
                pass
                
    metadata[name] = {
        "coordinates": latlon_corners,
        "image_file": f"{name}.png"
    }
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)
        
    print(f"Exported '{name}' to {output_dir}")

def export_raw_for_web(raster, grid, name, output_dir=None):
    """
    Exports a 2D numpy array as a raw data PNG where the Red channel encodes the 
    normalized values (0-255) and Alpha channel handles transparency (NaNs).
    This is used by the Nuxt web app to compute dynamic composite maps live!
    """
    if output_dir is None:
        output_dir = os.path.join(RESULTS_DIR, 'web')
    os.makedirs(output_dir, exist_ok=True)
    
    # Create RGBA array
    rgba = np.zeros((*raster.shape, 4), dtype=np.uint8)
    valid = ~np.isnan(raster)
    
    # Scale 0.0-1.0 float to 0-255 uint8
    scaled = np.clip(raster[valid] * 255, 0, 255).astype(np.uint8)
    
    rgba[valid, 0] = scaled # Red channel = data value
    rgba[valid, 3] = 255    # Alpha channel = opaque (255)
    
    png_path = os.path.join(output_dir, f"{name}_raw.png")
    
    # Save image
    plt.imsave(png_path, rgba, origin='upper', format='png')
    
    print(f"Exported raw data for '{name}' to {png_path}")
