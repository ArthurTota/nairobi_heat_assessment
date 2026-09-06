import ee
import geemap
import matplotlib.pyplot as plt
import urllib.request
from io import BytesIO
import matplotlib.image as mpimg

#-----------------------------------1 - LST----------------------------------------------
def mask_clouds_landsat8(image):
    """
    Identifies and removes clouds/shadows from Landsat 8 Level 2 imagery.
    
    Args:
        image (ee.Image): The raw Landsat 8 C2 L2 image.
    Returns:
        ee.Image: The image with cloud-affected pixels masked out.
    """
    # QA_PIXEL contains the quality assessment bits
    qa = image.select('QA_PIXEL')
    
    # Bitmask for Cloud (bit 3) and Cloud Shadow (bit 4)
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    
    return image.updateMask(mask)

def calculate_lst_celsius(image: ee.Image):
    """
    Calculates Land Surface Temperature in Celsius for Landsat 8 Collection 2 Level 2.
    Missing data points (holes) are interpolated using a local mean.
    """
    thermal_band = image.select('ST_B10')
    # Official NASA Scale Factors for Collection 2
    lst = thermal_band.multiply(0.00341802).add(149.0).subtract(273.15)
    
    interpolated_lst = lst
    # Iteratively interpolate using small, lightweight neighborhoods. 
    # Looping a 6-pixel radius 4 times reaches into the middle of big holes 
    # but calculates drastically faster than a massive 30-pixel kernel block.
    for _ in range(4):
        fast_fill = interpolated_lst.focal_mean(radius=6, units='pixels')
        interpolated_lst = interpolated_lst.unmask(fast_fill)
        
    return interpolated_lst.rename('LST_Celsius')

def load_landsat(_from_: int, _to_: int, _ROI_):
    """
    Load Landsat 8 imagery for a given time period and region of interest.
    
    Args:
        _from_ (int): The start year.
        _to_ (int): The end year.
        _ROI_ (ee.Geometry): The region of interest.
    Returns:
        ee.Image: The median composite of the Landsat 8 imagery.
    """
    # the landsat take a picture of location every 16 days, thus we have approximatly 22 images per year 
    # we decide arbitrarly to take the top 80% with the less cloud cover. Therefore the top 18*nb_year
    if _from_ > _to_:
        raise ValueError("Start year must be less than or equal to end year")
    nb_year = _to_ - _from_ + 1
    return ee.ImageCollection("LANDSAT/LC08/C02/T1_L2") \
            .filterBounds(_ROI_) \
            .filterDate(str(_from_) + '-01-01', str(_to_) + '-12-31') \
            .sort('CLOUD_COVER') \
            .limit(18*nb_year) \
            .map(mask_clouds_landsat8) \
            .median()

def visualize_data(image, region, ax=None, label='', vis_params=None, opacity=1.0):
    """
    Creates a static plot over a white background and adds the image layer.
    
    Args:
        image (ee.Image): The image to visualize.
        region (ee.Geometry|ee.FeatureCollection): The region of interest/boundary.
        ax (matplotlib.axes.Axes, optional): The axes to plot on.
        label (str): Title for the plot.
        vis_params (dict, optional): Visualization parameters.
        opacity (float, optional): Opacity of the image layer. Defaults to 1.0.
    """
    if vis_params is None:
        # Blue -> red heat scale (no green), matching the dashboard LST legend
        vis_params = {
            'min': 20,
            'max': 40,
            'palette': ['053061', '2166ac', '92c5de', 'd1e5f0',
                        'fddbc7', 'f4a582', 'd6604d', 'b2182b', '67001f']
        }
        
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 8))
        
    try:
        # Get bounds
        boundsInfo = region.geometry().bounds().getInfo()['coordinates'][0]
        lons = [p[0] for p in boundsInfo]
        lats = [p[1] for p in boundsInfo]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        
        # Get image thumbnail
        vis_image = image.visualize(**vis_params)
        url = vis_image.getThumbURL({
            'dimensions': 1024,
            'region': region.geometry(),
            'format': 'png'
        })
        
        # Render image
        response = urllib.request.urlopen(url)
        img_data = response.read()
        img = mpimg.imread(BytesIO(img_data), format='png')
        
        extent = [min_lon, max_lon, min_lat, max_lat]
        ax.imshow(img, extent=extent, alpha=opacity)
        
        # Draw region outlines
        geojson = region.getInfo()
        if 'features' in geojson:
            for feature in geojson['features']:
                geom = feature['geometry']
                if geom['type'] == 'Polygon':
                    for ring in geom['coordinates']:
                        rlons, rlats = zip(*ring)
                        ax.plot(rlons, rlats, color='black', linewidth=1)
                elif geom['type'] == 'MultiPolygon':
                    for poly in geom['coordinates']:
                        for ring in poly:
                            rlons, rlats = zip(*ring)
                            ax.plot(rlons, rlats, color='black', linewidth=1)
                            
        ax.set_title(label, fontsize=12)
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_aspect('equal')
        ax.set_facecolor('white')
        
    except Exception as e:
        print(f"Visualization error for {label}: {e}")
        
    return ax


def heatmap_overyears_of(ROI, years):
    """
    Generates subplots of LST heatmaps for multiple years and explicitly 
    downloads the data as local GeoTIFFs to maintain a clean local pipeline.
    
    Args:
        ROI (ee.FeatureCollection): The region of interest.
        years (list of int): List of years to visualize.
    """
    n_years = len(years)
    fig, axes = plt.subplots(1, n_years, figsize=(6 * n_years, 8))
    
    # Handle single year case
    if n_years == 1: axes = [axes]
    
    import os
    out_dir = os.path.join("../results", "lst_geotiffs")
    os.makedirs(out_dir, exist_ok=True)
        
    for i, year in enumerate(years):
        ax = axes[i]
        try:
            print(f"Processing LST for {year}...")
            # load landsat 8 data
            landsat = load_landsat(year, year, ROI)
            # calculate LST in Celsius and properly clip to city boundary AFTER interpolation
            image_to_plot = calculate_lst_celsius(landsat).clip(ROI)
            label = f"Nairobi LST ({year})"
            
            # Plot the map
            visualize_data(image_to_plot, ROI, ax=ax, label=label, vis_params=None)
            
            # Download to local GeoTIFF
            filename = os.path.join(out_dir, f"LST_{year}.tif")
            print(f"Downloading GeoTIFF for {year}...")
            geemap.ee_export_image(
                image_to_plot, 
                filename=filename, 
                scale=30, 
                region=ROI.geometry()
            )
            print(f"Saved: {filename}")
            
        except Exception as e:
            print(f"Error processing year {year}: {e}")
            ax.set_title(f"Error: {year}")
            ax.axis('off')
            
    plt.tight_layout()
    plt.show()
    return fig


