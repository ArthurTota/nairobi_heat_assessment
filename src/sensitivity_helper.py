import os
import numpy as np
import rasterio
from rasterio.mask import mask
import rasterio.warp
from rasterio.enums import Resampling

from .common_helper import *

def clip_raster_to_boundary(input_tif, output_tif, boundary_gdf):
    if not os.path.exists(input_tif):
        print(f"File not found: {input_tif}")
        return
    print(f"Clipping {input_tif}...")
    with rasterio.open(input_tif) as src:
        boundary_crs = boundary_gdf.to_crs(src.crs)
        geoms = [geom for geom in boundary_crs.geometry]
        out_image, out_transform = mask(src, geoms, crop=True)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })
        with rasterio.open(output_tif, "w", **out_meta) as dest:
            dest.write(out_image)
    print(f"Saved clipped raster to {output_tif}")

def resample_to_grid(input_tif, grid, method=Resampling.sum):
    if not os.path.exists(input_tif):
        print(f"File not found: {input_tif}")
        return None
    with rasterio.open(input_tif) as src:
        dst_array = np.zeros((grid['nrows'], grid['ncols']), dtype=np.float32)
        dst_crs = grid['crs']
        dst_transform = grid['transform']
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=dst_array,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=method
        )
        dst_array[~grid['mask']] = np.nan
        return dst_array

def normalize_layer(layer, clip_percentile=99):
    if layer is None: return None
    valid = layer[~np.isnan(layer)]
    if len(valid) == 0 or valid.max() == valid.min():
        return np.zeros_like(layer)
    vmax = np.percentile(valid, clip_percentile)
    vmin = valid.min()
    clipped_layer = np.clip(layer, vmin, vmax)
    return (clipped_layer - vmin) / (vmax - vmin)
