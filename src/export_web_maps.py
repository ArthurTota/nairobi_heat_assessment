import os
import json
import numpy as np
import matplotlib.pyplot as plt
from pyproj import Transformer
from src.adaptive_capacity_helper import PROXIMITY_CMAP, RESULTS_DIR, PROJECT_ROOT

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

def export_raw_for_web(raster, name, output_dir=None):
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


def export_grid_data(raster, grid, name, output_dir=None):
    """
    Save a 2D analysis-grid array as a georeferenced float32 GeoTIFF so other
    notebooks (e.g. 4_statistics_analysis) can REUSE the exact computed layer
    instead of recomputing it from raw data.

    Unlike the PNG exports (which are colour-mapped / 8-bit and lossy), this keeps
    the real numeric values. Written to <output_dir or results/web>/data/<name>.tif
    with the grid's transform and CRS; NaNs are preserved as nodata.
    """
    import rasterio

    if output_dir is None:
        output_dir = os.path.join(RESULTS_DIR, 'web')
    data_dir = os.path.join(output_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    arr = np.asarray(raster, dtype='float32')
    tif_path = os.path.join(data_dir, f"{name}.tif")
    with rasterio.open(
        tif_path, 'w', driver='GTiff',
        height=arr.shape[0], width=arr.shape[1],
        count=1, dtype='float32',
        crs=grid['crs'], transform=grid['transform'],
        nodata=float('nan'),
    ) as dst:
        dst.write(arr, 1)

    print(f"Saved grid data '{name}' -> {tif_path}")
    return tif_path


def load_grid_data(name, grid=None, output_dir=None):
    """
    Load a grid GeoTIFF saved by export_grid_data() back into a numpy array.

    If `grid` is given, the raster is reprojected onto that analysis grid and
    masked to grid['mask'] (so it always lines up with the caller's grid even if
    resolutions ever diverge). If `grid` is None, the array is returned as stored.
    Returns None if the file does not exist.
    """
    import rasterio
    from rasterio.warp import reproject
    from rasterio.enums import Resampling

    if output_dir is None:
        output_dir = os.path.join(RESULTS_DIR, 'web')
    tif_path = os.path.join(output_dir, 'data', f"{name}.tif")
    if not os.path.exists(tif_path):
        return None

    with rasterio.open(tif_path) as src:
        if grid is None:
            return src.read(1).astype('float32')
        dst = np.full((grid['nrows'], grid['ncols']), np.nan, dtype='float32')
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=grid['transform'], dst_crs=grid['crs'],
            resampling=Resampling.bilinear,
        )
        if 'mask' in grid:
            dst[~grid['mask']] = np.nan
        return dst
