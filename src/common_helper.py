import os
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from rasterio.features import rasterize
from rasterio.transform import from_bounds

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'geospatial')
RESULTS_DIR = os.path.join(PROJECT_ROOT, 'results')
NAIROBI_UTM_EPSG = 21037

# --- Colour palettes ---
PROXIMITY_CMAP = LinearSegmentedColormap.from_list(
    'proximity',
    ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#66bd63', '#1a9850']
)

COMPOSITE_CMAP = LinearSegmentedColormap.from_list(
    'composite',
    ['#67001f', '#b2182b', '#d6604d', '#f4a582', '#fddbc7',
     '#d1e5f0', '#92c5de', '#4393c3', '#2166ac', '#053061']
)

# --- Data Loading ---
def load_boundary(path=None):
    if path is None:
        path = os.path.join(DATA_DIR, 'nairobi_boundary.geojson')
    return gpd.read_file(path)

def load_geojson(filename):
    path = os.path.join(DATA_DIR, filename)
    # Backward-compat: the data folders were renamed with numeric prefixes
    # (exposure->1_exposure, sensitivity->2_sensitivity, adaptivity->3_adaptivity).
    # If the legacy path is missing, retry the renamed folder so old notebooks
    # keep working without editing every call site.
    if not os.path.exists(path):
        legacy = {'exposure': '1_exposure', 'sensitivity': '2_sensitivity',
                  'adaptivity': '3_adaptivity'}
        head = filename.split('/', 1)[0].split(os.sep, 1)[0]
        if head in legacy:
            alt = os.path.join(DATA_DIR, filename.replace(head, legacy[head], 1))
            if os.path.exists(alt):
                path = alt
    gdf = gpd.read_file(path)
    print(f"  Loaded {filename}: {len(gdf)} features")
    return gdf

# --- Grid Creation ---
def create_analysis_grid(boundary_gdf, resolution_m=50):
    boundary_utm = boundary_gdf.to_crs(epsg=NAIROBI_UTM_EPSG)
    minx, miny, maxx, maxy = boundary_utm.total_bounds
    minx -= resolution_m
    miny -= resolution_m
    maxx += resolution_m
    maxy += resolution_m
    ncols = int(np.ceil((maxx - minx) / resolution_m))
    nrows = int(np.ceil((maxy - miny) / resolution_m))
    transform = from_bounds(minx, miny, maxx, maxy, ncols, nrows)
    mask = rasterize(
        [(geom, 1) for geom in boundary_utm.geometry],
        out_shape=(nrows, ncols),
        transform=transform,
        fill=0,
        dtype='uint8'
    ).astype(bool)
    print(f"  Grid created: {nrows} x {ncols} cells ({resolution_m} m resolution)")
    return {
        'nrows': nrows, 'ncols': ncols,
        'transform': transform, 'mask': mask,
        'bounds': (minx, miny, maxx, maxy),
        'resolution': resolution_m,
        'crs': boundary_utm.crs,
        'boundary_utm': boundary_utm,
    }

def _rasterize_points(gdf, grid):
    gdf_utm = gdf.to_crs(grid['crs'])
    if len(gdf_utm) == 0:
        return np.zeros((grid['nrows'], grid['ncols']), dtype='uint8')
    return rasterize(
        [(geom, 1) for geom in gdf_utm.geometry if geom is not None],
        out_shape=(grid['nrows'], grid['ncols']),
        transform=grid['transform'],
        fill=0, dtype='uint8'
    )

# --- Plotting ---
def plot_layer(raster, grid, title, cmap=None, ax=None, show_colorbar=True, cbar_label='Adaptive Capacity Score', vmin=0, vmax=1):
    if cmap is None: cmap = PROXIMITY_CMAP
    if ax is None: fig, ax = plt.subplots(figsize=(10, 9))
    minx, miny, maxx, maxy = grid['bounds']
    extent = [minx, maxx, miny, maxy]
    im = ax.imshow(raster, origin='upper', extent=extent, cmap=cmap, vmin=vmin, vmax=vmax, interpolation='nearest')
    for geom in grid['boundary_utm'].geometry:
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            ax.plot(x, y, color='black', linewidth=1.2)
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                ax.plot(x, y, color='black', linewidth=1.2)
    ax.set_title(title, fontsize=14, fontweight='bold', pad=12)
    ax.set_xlabel('Easting (m)')
    ax.set_ylabel('Northing (m)')
    ax.set_aspect('equal')
    ax.set_facecolor('#f0f0f0')
    if show_colorbar:
        cbar = plt.colorbar(im, ax=ax, fraction=0.035, pad=0.04)
        cbar.set_label(cbar_label, fontsize=10)
    return ax

def plot_points_overlay(gdf, grid, ax, color='white', size=8, label=None):
    gdf_utm = gdf.to_crs(grid['crs'])
    centroids = gdf_utm.geometry.centroid
    ax.scatter(centroids.x, centroids.y, c=color, s=size, edgecolors='black', linewidths=0.3, alpha=0.7, zorder=5, label=label)
    if label: ax.legend(loc='upper right', fontsize=9)

def plot_all_layers(layers_dict, grid):
    names = list(layers_dict.keys())
    n = len(names)
    ncols_fig = 3
    nrows_fig = int(np.ceil(n / ncols_fig))
    fig, axes = plt.subplots(nrows_fig, ncols_fig, figsize=(7 * ncols_fig, 7 * nrows_fig))
    axes = axes.flatten()
    for i, name in enumerate(names):
        plot_layer(layers_dict[name], grid, name, ax=axes[i], show_colorbar=True)
    for j in range(n, len(axes)):
        axes[j].set_visible(False)
    plt.tight_layout()
    plt.show()
    return fig
