import geopandas as gpd
from shapely.geometry import box
import numpy as np
import rasterio
import os
import sys

sys.path.append('.')
from src.common_helper import load_boundary

print("Generating 250m hover grid covering Nairobi...")

boundary = load_boundary()
bounds = boundary.total_bounds
minx, miny, maxx, maxy = bounds

# roughly 250m is 0.00225 degrees. We use 0.0025 for simplicity
step = 0.0025
lons = np.arange(minx, maxx, step)
lats = np.arange(miny, maxy, step)

polys = []
for i in range(len(lons)-1):
    for j in range(len(lats)-1):
        polys.append(box(lons[i], lats[j], lons[i+1], lats[j+1]))

grid = gpd.GeoDataFrame(geometry=polys, crs='EPSG:4326')
# Clip precisely to Nairobi
grid_clipped = gpd.clip(grid, boundary).reset_index(drop=True)

print(f"Created {len(grid_clipped)} grid cells. Now sampling raster data...")

# List of rasters we want to make hoverable
rasters_to_sample = {
    'lst_2020': 'notebooks/results/lst_geotiffs/LST_2020.tif',
    'lst_2022': 'notebooks/results/lst_geotiffs/LST_2022.tif',
    'lst_2024': 'notebooks/results/lst_geotiffs/LST_2024.tif',
    'pop_total': 'data/geospatial/sensitivity/nairobi_general_pop_2020.tif',
    'pop_children': 'data/geospatial/sensitivity/nairobi_children_pop_2020.tif',
    'pop_elderly': 'data/geospatial/sensitivity/nairobi_elderly_pop_2020.tif'
}

# We sample at the centroid of each cell
centroids = [(geom.centroid.x, geom.centroid.y) for geom in grid_clipped.geometry]

for name, path in rasters_to_sample.items():
    if os.path.exists(path):
        print(f"Sampling {name}...")
        with rasterio.open(path) as src:
            # sample returns a generator of arrays
            values = [val[0] for val in src.sample(centroids)]
            
            # handle nodata
            nodata = src.nodata
            clean_values = []
            for v in values:
                if nodata is not None and v == nodata:
                    clean_values.append(None)
                elif np.isnan(v):
                    clean_values.append(None)
                else:
                    # Round for cleaner tooltips
                    clean_values.append(round(float(v), 1))
            
            grid_clipped[name] = clean_values
    else:
        print(f"Warning: {path} not found. Skipping {name}.")

# Save to the webapp public maps folder
output_path = 'webapp/public/maps/hover_grid.geojson'
grid_clipped.to_file(output_path, driver='GeoJSON')

print(f"Successfully generated hover grid with raster data: {output_path}")
