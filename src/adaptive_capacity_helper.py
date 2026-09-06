import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from scipy.ndimage import distance_transform_edt, gaussian_filter
from rasterio.features import rasterize

from .common_helper import *
# `import *` skips underscore-prefixed names, so import the private helper explicitly.
from .common_helper import _rasterize_points

def compute_proximity(gdf, grid, max_distance_m=None):
    binary = _rasterize_points(gdf, grid)
    dist = distance_transform_edt(binary == 0) * grid['resolution']
    if max_distance_m is not None:
        dist = np.minimum(dist, max_distance_m)
    max_dist = dist[grid['mask']].max() if grid['mask'].any() else 1.0
    max_dist = max(max_dist, 1.0)
    proximity = 1.0 - (dist / max_dist)
    result = np.full_like(proximity, np.nan)
    result[grid['mask']] = proximity[grid['mask']]
    return result

def compute_distance(gdf, grid):
    """Euclidean distance in METRES from every grid cell to the nearest feature.

    Same EDT as compute_proximity but returns the raw distance (not the 0-1
    score), so the statistics notebook can report 'mean distance to nearest
    health facility' etc. in real units.
    """
    binary = _rasterize_points(gdf, grid)
    dist = distance_transform_edt(binary == 0) * grid['resolution']
    result = np.full_like(dist, np.nan, dtype='float32')
    result[grid['mask']] = dist[grid['mask']]
    return result

def compute_road_density(roads_gdf, grid, bandwidth_m=500):
    roads_utm = roads_gdf.to_crs(grid['crs'])
    burned = rasterize(
        [(geom, 1) for geom in roads_utm.geometry if geom is not None],
        out_shape=(grid['nrows'], grid['ncols']),
        transform=grid['transform'],
        fill=0, dtype='float32'
    )
    sigma = bandwidth_m / grid['resolution']
    density = gaussian_filter(burned.astype(float), sigma=sigma)
    vals = density[grid['mask']]
    vmin, vmax = vals.min(), vals.max()
    if vmax - vmin > 0:
        density = (density - vmin) / (vmax - vmin)
    else:
        density = np.zeros_like(density)
    result = np.full_like(density, np.nan)
    result[grid['mask']] = density[grid['mask']]
    return result

def compute_composite(layers, weights=None):
    n = len(layers)
    if weights is None:
        weights = [1.0 / n] * n
    composite = np.zeros_like(layers[0])
    count = np.zeros_like(layers[0])
    for layer, w in zip(layers, weights):
        valid = ~np.isnan(layer)
        composite[valid] += w * layer[valid]
        count[valid] += w
    count[count == 0] = np.nan
    composite = composite / count
    vals = composite[~np.isnan(composite)]
    if len(vals) > 0 and vals.max() > vals.min():
        composite[~np.isnan(composite)] = (
            (composite[~np.isnan(composite)] - vals.min())
            / (vals.max() - vals.min())
        )
    return composite
