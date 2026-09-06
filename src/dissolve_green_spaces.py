import geopandas as gpd
import os

print("Loading green spaces...")
input_path = 'webapp/public/maps/green_spaces.geojson'
if not os.path.exists(input_path):
    print("Error: Could not find green_spaces.geojson")
    exit(1)

# Read the geojson
gdf = gpd.read_file(input_path)

print(f"Original green spaces count: {len(gdf)}")

# We add a dummy column so we can dissolve everything into unified multi-polygons.
# If we want to dissolve by a property (like 'natural' or 'landuse'), we can do so
gdf['dissolve_field'] = 1

print("Dissolving overlapping polygons (this may take a moment)...")
dissolved_gdf = gdf.dissolve(by='dissolve_field')

# We set generic names
dissolved_gdf['name'] = 'Green Space Zone'
dissolved_gdf['natural'] = 'wood/park'
dissolved_gdf = dissolved_gdf.reset_index(drop=True)

print(f"Dissolved green spaces count: {len(dissolved_gdf)}")

# Save back to geojson
output_path = 'webapp/public/maps/green_spaces.geojson'
dissolved_gdf.to_file(output_path, driver='GeoJSON')
print(f"Successfully saved dissolved green spaces to {output_path}")
