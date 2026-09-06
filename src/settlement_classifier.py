"""
Supervised settlement classification pipeline for Nairobi using Google Earth Engine.

METHODOLOGY
-----------
This module implements a Random Forest (RF) classifier to map land cover in
Nairobi with a focus on distinguishing informal from formal settlements.

The approach combines two families of features:

  1. Spectral features - Raw reflectance bands and normalised-difference
     indices computed from Sentinel-2 imagery (10 m resolution).

  2. Texture features - Grey-Level Co-occurrence Matrix (GLCM) statistics
     that capture the spatial arrangement of pixels, which is critical for
     separating the dense, heterogeneous roofscapes of informal settlements
     from the more regular structures of formal areas.

Why texture matters:
    Spectral values alone cannot reliably distinguish settlement types because
    both formal and informal areas are "built-up". Texture features like
    contrast, entropy and homogeneity encode the local spatial pattern
    and are consistently cited as the most discriminative features for informal
    settlement mapping (see Kuffer et al., 2016; Engstrom et al., 2015).

TRAINING DATA
-------------
Training data are polygons (not individual points). Each polygon covers a
small, homogeneous area of a known class. Pixels inside each polygon are
sampled to build the training set. This yields hundreds of diverse training
pixels per polygon - far more than the single pixel you get from a point.

There are 3 land-cover classes (simplified from 5 for better accuracy):

  +----------+----------------------------------------------------------+
  |  Label   | Description                                              |
  +----------+----------------------------------------------------------+
  | 0        | Informal settlement (slum / unplanned)                   |
  | 1        | Formal settlement (planned / structured)                 |
  | 2        | Other (vegetation, park, road, bare soil, water, etc.)   |
  +----------+----------------------------------------------------------+

TRAIN-ONCE -> CLASSIFY-MANY-YEARS
---------------------------------
The pipeline is designed so you train the classifier on ONE year's composite
and then apply it to composites from any year. As long as the feature
engineering is identical (same bands + indices + texture), the trained model
is directly transferable.

Typical usage in a notebook:

    >>> from src.settlement_classifier import *
    >>> # 1. Build composite for training year
    >>> composite_2022 = build_feature_composite(roi, 2022)
    >>> # 2. Get training zones (default known areas or your GeoJSON)
    >>> zones = get_default_training_zones()
    >>> # zones = load_training_zones("data/geospatial/my_zones.geojson")
    >>> # 3. Sample, split, train, evaluate
    >>> train, test = sample_and_split(composite_2022, zones)
    >>> clf = train_classifier(train)
    >>> metrics = evaluate_accuracy(test, clf)
    >>> # 4. Classify training year
    >>> classified_2022 = classify_image(composite_2022, clf)
    >>> # 5. Classify other years with the SAME trained classifier
    >>> classified_2020 = classify_image(build_feature_composite(roi, 2020), clf)
    >>> # 6. Visualise side-by-side
    >>> visualize_multi_year({2020: classified_2020, 2022: classified_2022}, roi)

"""

import ee
import json
import urllib.request
from io import BytesIO

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.image as mpimg
import numpy as np


# -----------------------------------------------------------------------------
# 1.  CONFIGURATION & CONSTANTS
# -----------------------------------------------------------------------------

# --- Class definitions ---------------------------------------------------
#
# The integer label is stored as the 'label' property of every training
# feature.  The same label ends up in the classified image band.
#
# We use 3 classes (not 5) because:
#   - Fewer classes -> more training data per class -> better accuracy
#   - "other" absorbs vegetation, water, bare soil, roads, parks, etc.
#   - The hard problem (informal vs formal) gets the model's full focus

CLASS_NAMES  = ["informal", "not-informal"]
CLASS_LABELS = [0,          1             ]
CLASS_COLORS = ["#e74c3c",  "#2ecc71"     ]
#  informal  = red       not-informal = green
NUM_CLASSES  = len(CLASS_NAMES)

# Map from human-readable name -> integer label (used when loading GeoJSON)
CLASS_MAP = {
    "informal": 0,
    "formal":   1,
    "other":    1,
    "vegetation": 1,  
    "water":      1,  
}

# --- Feature bands -------------------------------------------------------
#
# These are the band names that will exist in the composite after
# build_feature_composite().  Every band listed here is fed into the
# Random Forest.  Order does not matter for the classifier, but keeping
# a consistent list ensures training and classification use the same set.
#
# Raw Sentinel-2 bands (6):
#   B2  (Blue,  490 nm, 10 m)   - helps separate water from land
#   B3  (Green, 560 nm, 10 m)   - used in several indices
#   B4  (Red,   665 nm, 10 m)   - strong chlorophyll absorption
#   B8  (NIR,   842 nm, 10 m)   - vegetation & built-up response
#   B11 (SWIR1, 1610 nm, 20 m)  - sensitive to moisture & built-up
#   B12 (SWIR2, 2190 nm, 20 m)  - bare soil / built-up
#
# Spectral indices (7):
#   NDVI  = (B8 - B4)  / (B8 + B4)           - vegetation vigour
#   NDBI  = (B11 - B8) / (B11 + B8)          - built-up intensity
#   NDWI  = (B3 - B8)  / (B3 + B8)           - water detection
#   MNDWI = (B3 - B11) / (B3 + B11)          - improved water detection
#   BSI   = (B11+B4-B8-B2)/(B11+B4+B8+B2)    - bare soil
#   SAVI  = 1.5*(B8-B4)/(B8+B4+0.5)          - soil-adjusted veg index
#   EVI   = 2.5*(B8-B4)/(B8+6*B4-7.5*B2+1)   - enhanced veg index
#
# GLCM texture features (5, computed on Red band B4):
#   B4_asm      - Angular Second Moment (uniformity/energy)
#                  High in homogeneous areas (formal settlements, water)
#   B4_contrast - Contrast (local intensity variation)
#                  High in heterogeneous areas (informal settlements)
#   B4_ent      - Entropy (disorder / randomness)
#                  High when pixel intensities are diverse (slums)
#   B4_idm      - Inverse Difference Moment (homogeneity)
#                  High when neighbouring pixels are similar (formal)
#   B4_corr     - Correlation (linear dependency between neighbours)
#
# Total: 6 + 7 + 5 = 18 features

FEATURE_BANDS = [
    # Raw spectral bands
    "B2", "B3", "B4", "B8", "B11", "B12",
    # Spectral indices
    "NDVI", "NDBI", "NDWI", "MNDWI", "BSI", "SAVI", "EVI",
    # GLCM texture (on B4 = Red, 10 m)
    "B4_asm", "B4_contrast", "B4_ent", "B4_idm", "B4_corr",
]

# --- Classifier defaults -------------------------------------------------
DEFAULT_N_TREES        = 500    # number of trees in Random Forest
DEFAULT_TRAIN_FRACTION = 0.8    # 80 % train / 20 % test
DEFAULT_SEED           = 42     # reproducibility seed
DEFAULT_SCALE          = 10     # Sentinel-2 resolution in metres
DEFAULT_CLOUD_PCT      = 20     # max cloud cover for filtering S2 collection
LABEL_PROPERTY         = "label"


# -----------------------------------------------------------------------------
# 2.  SENTINEL-2  LOADING  &  FEATURE  ENGINEERING
# -----------------------------------------------------------------------------

def mask_s2_clouds(image):
    """
    Mask clouds and cirrus in Sentinel-2 Surface Reflectance imagery.

    Uses the QA60 bitmask band:
      - Bit 10 → opaque cloud
      - Bit 11 → cirrus cloud

    After masking, reflectance values are divided by 10 000 so they fall in
    the physical range [0, 1].

    Args:
        image (ee.Image): Raw Sentinel-2 SR image.

    Returns:
        ee.Image: Cloud-masked image with reflectance in [0, 1].
    """
    qa = image.select("QA60")
    cloud_bit  = 1 << 10
    cirrus_bit = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit).eq(0).And(
        qa.bitwiseAnd(cirrus_bit).eq(0)
    )
    return image.updateMask(mask).divide(10000)


def compute_spectral_indices(image):
    """
    Add spectral indices as new bands to a Sentinel-2 image.

    Indices computed
    ----------------
    NDVI  - Normalized Difference Vegetation Index
            (B8 - B4) / (B8 + B4)
            Range [-1, 1].  High values -> dense vegetation.

    NDBI  - Normalized Difference Built-up Index
            (B11 - B8) / (B11 + B8)
            Range [-1, 1].  Positive -> built-up surfaces.

    NDWI  - Normalized Difference Water Index (McFeeters, 1996)
            (B3 - B8) / (B3 + B8)
            Positive -> water bodies.

    MNDWI - Modified NDWI (Xu, 2006)
            (B3 - B11) / (B3 + B11)
            Better at suppressing built-up noise than NDWI.

    BSI   - Bare Soil Index (Rikimaru et al., 2002)
            (B11 + B4 - B8 - B2) / (B11 + B4 + B8 + B2)
            Highlights exposed soil.

    SAVI  - Soil-Adjusted Vegetation Index (Huete, 1988)
            1.5 * (B8 - B4) / (B8 + B4 + 0.5)
            Like NDVI but reduces soil background effects.
            The factor L = 0.5 is standard for moderate veg. cover.

    EVI   - Enhanced Vegetation Index (Huete et al., 2002)
            2.5 * (B8 - B4) / (B8 + 6*B4 - 7.5*B2 + 1)
            Improved sensitivity in high-biomass regions and
            reduced atmospheric influence.

    Args:
        image (ee.Image): Must contain bands B2, B3, B4, B8, B11.

    Returns:
        ee.Image: Original image with 7 new bands appended.
    """
    ndvi  = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndbi  = image.normalizedDifference(["B11", "B8"]).rename("NDBI")
    ndwi  = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
    mndwi = image.normalizedDifference(["B3", "B11"]).rename("MNDWI")

    # BSI = (B11+B4 - B8-B2) / (B11+B4 + B8+B2)
    bsi = (
        image.select("B11").add(image.select("B4"))
        .subtract(image.select("B8").add(image.select("B2")))
        .divide(
            image.select("B11").add(image.select("B4"))
            .add(image.select("B8")).add(image.select("B2"))
        )
    ).rename("BSI")

    # SAVI = 1.5 * (B8-B4) / (B8+B4+0.5)
    savi = (
        image.select("B8").subtract(image.select("B4"))
        .multiply(1.5)
        .divide(image.select("B8").add(image.select("B4")).add(0.5))
    ).rename("SAVI")

    # EVI = 2.5 * (B8-B4) / (B8 + 6*B4 - 7.5*B2 + 1)
    evi = (
        image.select("B8").subtract(image.select("B4"))
        .multiply(2.5)
        .divide(
            image.select("B8")
            .add(image.select("B4").multiply(6))
            .subtract(image.select("B2").multiply(7.5))
            .add(1)
        )
    ).rename("EVI")

    return image.addBands([ndvi, ndbi, ndwi, mndwi, bsi, savi, evi])


def compute_glcm_texture(image, band="B4", size=3):
    """
    Compute GLCM (Grey-Level Co-occurrence Matrix) texture statistics.

    BACKGROUND
    ----------
    GLCM captures how *pairs* of neighbouring pixel intensities are
    distributed.  It produces metrics that describe the spatial "texture"
    of the image — something spectral bands alone cannot.

    For settlement classification, texture is crucial:
      * Informal settlements have high contrast / entropy because roofing
        materials vary greatly and building layouts are irregular.
      * Formal settlements have high homogeneity (IDM) and low entropy
        because structures are more uniform and regularly spaced.

    IMPORTANT: GEE's glcmTexture() requires INTEGER input values.
    Since our S2 reflectance is in [0, 1] after cloud-masking, we first
    multiply by 10 000 and cast to Int32.

    The `size` parameter is the radius of the kernel (neighbourhood).
    size=3 → 7x7 pixel window ≈ 70 m x 70 m at 10 m resolution.

    Metrics selected (out of the many GLCM produces):
      B4_asm      - Angular Second Moment (energy/uniformity)
      B4_contrast - Contrast   (local variation of grey levels)
      B4_ent      - Entropy    (randomness / disorder)
      B4_idm      - Inverse Difference Moment (homogeneity)
      B4_corr     - Correlation (linear dependency)

    Reference:
      Haralick, R.M. et al. (1973). "Textural Features for Image
      Classification." IEEE Trans. Systems, Man, and Cybernetics.

    Args:
        image  (ee.Image): Must contain the specified band.
        band   (str):      Band name for GLCM computation (default "B4").
        size   (int):      Kernel radius in pixels (default 3 → 7x7 window).

    Returns:
        ee.Image: Original image with 5 texture bands appended.
    """
    # 1. Rescale to integer (required by glcmTexture)
    grey = image.select(band).multiply(10000).toInt32()

    # 2. Compute all GLCM metrics
    glcm = grey.glcmTexture(size=size)

    # 3. Select the most discriminative ones
    texture = glcm.select([
        f"{band}_asm",       # uniformity
        f"{band}_contrast",  # local variation   - high in slums
        f"{band}_ent",       # entropy           - high in slums
        f"{band}_idm",       # homogeneity       - high in formal
        f"{band}_corr",      # correlation
    ])

    return image.addBands(texture)


def build_feature_composite(roi, year, cloud_pct=DEFAULT_CLOUD_PCT):
    """
    Build a multi-band Sentinel-2 composite with all features for one year.

    Steps:
      1. Filter Sentinel-2 SR collection to the ROI & calendar year.
      2. Filter out images with cloud cover > cloud_pct.
      3. Apply cloud masking to each image.
      4. Take the per-pixel MEDIAN across the year (removes remaining noise).
      5. Clip to the ROI geometry.
      6. Compute spectral indices (NDVI, NDBI, etc.).
      7. Compute GLCM texture features on the Red band (B4).

    The resulting image has all bands listed in FEATURE_BANDS.

    IMPORTANT: This function produces an IDENTICAL feature stack regardless
    of the year, so a classifier trained on one year's composite can be
    applied to another year's composite without modification.

    Args:
        roi       (ee.Geometry | ee.FeatureCollection): Region of interest.
        year      (int):  Calendar year (e.g. 2022).
        cloud_pct (int):  Max CLOUDY_PIXEL_PERCENTAGE for pre-filtering.

    Returns:
        ee.Image: Composite image with all FEATURE_BANDS.
    """
    # Extract geometry if a FeatureCollection is passed
    geometry = roi.geometry() if hasattr(roi, 'geometry') else roi

    print(f"  [Loading Sentinel-2 composite for {year}]")
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(f"{year}-06-01", f"{year}-09-30")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
        .map(mask_s2_clouds)
        .median()
        .clip(geometry)
    )

    print(f"  [Computing spectral indices]")
    s2 = compute_spectral_indices(s2)

    print(f"  [Computing GLCM texture features]")
    s2 = compute_glcm_texture(s2)

    return s2


# -----------------------------------------------------------------------------
# 3.  TRAINING  DATA
# -----------------------------------------------------------------------------

def load_training_zones(geojson_path):
    """
    Load user-annotated training polygons from a local GeoJSON file.

    The GeoJSON must have standard Feature objects with a "class" property
    whose value is one of: "informal", "formal", "other".
    ("vegetation" and "water" are accepted as aliases for "other".)

    Example GeoJSON feature:
    {
        "type": "Feature",
        "properties": {
            "class": "informal",
            "name": "My custom zone"
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[lon1,lat1],[lon2,lat2],etc.,[lon1,lat1]]]
        }
    }

    Args:
        geojson_path (str): Path to a local .geojson file.

    Returns:
        ee.FeatureCollection: Training polygons with integer 'label' property.
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = []
    for feat in data.get("features", []):
        props  = feat.get("properties", {})
        geom   = feat.get("geometry", {})
        cls_name = props.get("class", "").lower().strip()

        if cls_name not in CLASS_MAP:
            print(f"  [Skipping feature with unknown class '{cls_name}']")
            continue

        label = CLASS_MAP[cls_name]
        name  = props.get("name", cls_name)
        ee_geom = ee.Geometry(geom)
        features.append(ee.Feature(ee_geom, {LABEL_PROPERTY: label, "name": name}))

    print(f"  [Loaded {len(features)} training zone(s) from {geojson_path}]")
    return ee.FeatureCollection(features)


def sample_and_split(composite, training_zones,
                     scale=30,
                     train_fraction=DEFAULT_TRAIN_FRACTION,
                     max_samples=5000,
                     seed=DEFAULT_SEED):
    """
    Sample pixels from training polygons and split into train / test sets.

    HOW IT WORKS
    1. Select only the FEATURE_BANDS from the composite.
    2. Use sampleRegions() at 30 m scale (not 10 m!) to reduce pixel count
       by approx 9x.  The 30 m sampling still captures the spectral/textural
       signature perfectly - we just skip some pixels.
    3. Limit total samples to max_samples to prevent GEE memory overflow.
    4. Add a random column and split into train / test.

    WHY 30 m INSTEAD OF 10 m?
    At 10 m, a single 1 km x 1 km polygon contains approx 10 000 pixels.
    20 polygons -> 200 000 pixels -> GEE runs out of memory.
    At 30 m, the same polygon contains approx 1 100 pixels - still plenty
    for training, and well within GEE free-tier limits.

    Args:
        composite       (ee.Image):             Feature composite.
        training_zones  (ee.FeatureCollection): Polygons with 'label'.
        scale           (int):                  Sampling resolution (default 30 m).
        train_fraction  (float):                Train fraction (default 0.7).
        max_samples     (int):                  Max total samples (default 5000).
        seed            (int):                  Random seed (default 42).

    Returns:
        tuple: (train_samples, test_samples) - both ee.FeatureCollection.
    """
    print(f"  [Sampling pixels from training zones (scale={scale}m, max={max_samples})]")

    # 1. Sample pixels inside training polygons at coarser resolution
    all_samples = (
        composite.select(FEATURE_BANDS)
        .sampleRegions(
            collection=training_zones,
            properties=[LABEL_PROPERTY],
            scale=scale,
            tileScale=8,      # helps avoid memory/timeout for large areas
            geometries=False, # don't return pixel geometries (saves memory)
        )
    )

    # 2. Add a random column for shuffling + splitting
    all_samples = all_samples.randomColumn("random", seed)

    # 3. Cap total samples to prevent memory overflow
    all_samples = all_samples.sort("random").limit(max_samples)

    # 4. Split
    train = all_samples.filter(ee.Filter.lt("random", train_fraction))
    test  = all_samples.filter(ee.Filter.gte("random", train_fraction))

    # 5. Print statistics (triggers a server call)
    n_total = all_samples.size().getInfo()
    n_train = train.size().getInfo()
    n_test  = test.size().getInfo()
    print(f"  [Total samples: {n_total} | Train: {n_train} | Test: {n_test}]")

    return train, test


# -----------------------------------------------------------------------------
# 4.  TRAINING  &  CLASSIFICATION
# -----------------------------------------------------------------------------

def train_classifier(train_samples, n_trees=DEFAULT_N_TREES):
    """
    Train a GEE Random Forest classifier on the training samples.

    ABOUT RANDOM FOREST
    -------------------
    ee.Classifier.smileRandomForest builds an ensemble of decision trees.
    Each tree is trained on a random subset of features and samples
    (bagging + feature randomness).  The final prediction is the majority
    vote across all trees.

    The main hyper-parameter is n_trees (numberOfTrees):
      * More trees -> better accuracy but slower.
      * 200 trees is a good default for most GEE workflows.

    Args:
        train_samples (ee.FeatureCollection): Training data with FEATURE_BANDS
                                              + 'label' property.
        n_trees       (int):                  Number of decision trees (default 200).

    Returns:
        ee.Classifier: Trained Random Forest classifier.
    """
    print(f"  [Training Random Forest with {n_trees} trees]")

    classifier = (
        ee.Classifier.smileRandomForest(numberOfTrees=n_trees)
        .train(
            features=train_samples,
            classProperty=LABEL_PROPERTY,
            inputProperties=FEATURE_BANDS,
        )
    )

    print("  [Classifier trained successfully]")
    return classifier


def classify_image(composite, classifier, smooth_radius=1):
    """
    Apply a trained classifier to a feature composite and smooth the output.

    Args:
        composite     (ee.Image):      Must contain all FEATURE_BANDS.
        classifier    (ee.Classifier): Trained classifier from train_classifier().
        smooth_radius (int):           Radius for majority voting (smoothing).
                                        radius=1 -> 3x3 window (removes isolated noise)
                                        radius=2 -> 5x5 window (stronger smoothing)
                                        Set to 0 to disable smoothing.

    Returns:
        ee.Image: Single-band image named 'classification' with integer class labels.
    """
    classified = composite.select(FEATURE_BANDS).classify(classifier).rename("classification")
    
    if smooth_radius > 0:
        # Focal mode acts as a majority filter. It looks at the neighbourhood
        # around the pixel and assigns the most common class.
        # This fixes the issue of isolated (disparate) pixels and ensures spatial logic.
        classified = classified.focalMode(radius=smooth_radius, kernelType='square', units='pixels')
        
    return classified


# -----------------------------------------------------------------------------
# 5.  ACCURACY  ASSESSMENT
# -----------------------------------------------------------------------------

def evaluate_accuracy(test_samples, classifier):
    """
    Evaluate the classifier on the held-out TEST set (not resubstitution).

    Metrics returned:
      - confusion_matrix : 2-D Python list (rows = actual, cols = predicted)
      - overall_accuracy : float in [0, 1]
      - kappa            : Cohen's kappa coefficient
      - producers_accuracy: per-class recall (1 - omission error)
      - consumers_accuracy: per-class precision (1 - commission error)

    NOTE
    ----
    All values are retrieved via getInfo() - this triggers a server-side
    computation.  For large test sets this may take a few seconds.

    Args:
        test_samples (ee.FeatureCollection): Test data (from sample_and_split).
        classifier   (ee.Classifier):        Trained classifier.

    Returns:
        dict: Dictionary with accuracy metrics.
    """
    print("  [Evaluating model on test set]")

    classified_test = test_samples.classify(classifier)
    cm = classified_test.errorMatrix(LABEL_PROPERTY, "classification")

    metrics = {
        "confusion_matrix":    cm.getInfo(),
        "overall_accuracy":    cm.accuracy().getInfo(),
        "kappa":               cm.kappa().getInfo(),
        "producers_accuracy":  cm.producersAccuracy().getInfo(),
        "consumers_accuracy":  cm.consumersAccuracy().getInfo(),
    }

    oa = metrics["overall_accuracy"]
    k  = metrics["kappa"]
    print(f"  [Overall Accuracy: {oa:.3f} | Kappa: {k:.3f}]")

    return metrics


def k_fold_cross_validation(composite, training_zones,
                             n_trees=DEFAULT_N_TREES,
                             k=5,
                             scale=DEFAULT_SCALE,
                             seed=DEFAULT_SEED):
    """
    Server-side k-fold cross-validation.

    Splits samples into k equal folds using a random column, then for each
    fold trains on the other k-1 folds and evaluates on the held-out fold.
    Returns the mean accuracy across all k folds.

    This runs entirely on GEE servers - only one getInfo() call at the end.

    Args:
        composite      (ee.Image):             Feature composite.
        training_zones (ee.FeatureCollection): Training polygons.
        n_trees        (int):                  Number of RF trees.
        k              (int):                  Number of folds (default 5).
        scale          (int):                  Sampling scale.
        seed           (int):                  Random seed.

    Returns:
        float: Mean overall accuracy across k folds.
    """
    print(f"  [Running {k}-fold cross-validation]")

    samples = (
        composite.select(FEATURE_BANDS)
        .sampleRegions(
            collection=training_zones,
            properties=[LABEL_PROPERTY],
            scale=scale,
            tileScale=4,
        )
        .randomColumn("fold_rand", seed)
    )

    def fold_accuracy(fold_idx):
        fold_idx  = ee.Number(fold_idx)
        fold_size = ee.Number(1).divide(k)
        lo = fold_idx.multiply(fold_size)
        hi = lo.add(fold_size)

        val_set  = samples.filter(
            ee.Filter.And(ee.Filter.gte("fold_rand", lo),
                          ee.Filter.lt("fold_rand", hi))
        )
        train_set = samples.filter(
            ee.Filter.Or(ee.Filter.lt("fold_rand", lo),
                         ee.Filter.gte("fold_rand", hi))
        )

        clf = ee.Classifier.smileRandomForest(n_trees).train(
            features=train_set,
            classProperty=LABEL_PROPERTY,
            inputProperties=FEATURE_BANDS,
        )
        cm = val_set.classify(clf).errorMatrix(LABEL_PROPERTY, "classification")
        return cm.accuracy()

    fold_accs = ee.List.sequence(0, k - 1).map(fold_accuracy)
    mean_acc  = ee.Array(fold_accs).reduce(ee.Reducer.mean(), [0]).get([0])

    result = mean_acc.getInfo()
    print(f"  [Mean {k}-fold CV accuracy: {result:.3f}]")
    return result


# -----------------------------------------------------------------------------
# 6.  VISUALIZATION
# -----------------------------------------------------------------------------

def _get_thumb(ee_image, roi, vis_params, dimensions=1024):
    """
    Internal: download a GEE thumbnail as a numpy array.

    Args:
        ee_image   (ee.Image):      Image to visualise.
        roi        (ee.Geometry | ee.FeatureCollection): Region.
        vis_params (dict):          Visualisation parameters for ee.Image.visualize().
        dimensions (int):           Max dimension in pixels.

    Returns:
        numpy.ndarray: RGB image array.
    """
    geometry = roi.geometry() if hasattr(roi, "geometry") else roi
    vis = ee_image.visualize(**vis_params)
    url = vis.getThumbURL({
        "dimensions": dimensions,
        "region": geometry,
        "format": "png",
    })
    resp = urllib.request.urlopen(url)
    return mpimg.imread(BytesIO(resp.read()), format="png")


def _get_extent(roi):
    """Internal: return [min_lon, max_lon, min_lat, max_lat] for imshow()."""
    geometry = roi.geometry() if hasattr(roi, "geometry") else roi
    bounds = geometry.bounds().getInfo()["coordinates"][0]
    lons = [p[0] for p in bounds]
    lats = [p[1] for p in bounds]
    return [min(lons), max(lons), min(lats), max(lats)]


def _draw_boundary(ax, roi, color="black", linewidth=1):
    """Internal: overlay the ROI boundary polyline on a matplotlib axes."""
    geojson = roi.getInfo() if not isinstance(roi, dict) else roi
    features = geojson.get("features", [geojson])
    for feat in features:
        geom = feat.get("geometry", feat)
        gtype = geom.get("type", "")
        if gtype == "Polygon":
            for ring in geom["coordinates"]:
                xs, ys = zip(*ring)
                ax.plot(xs, ys, color=color, linewidth=linewidth)
        elif gtype == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly:
                    xs, ys = zip(*ring)
                    ax.plot(xs, ys, color=color, linewidth=linewidth)


def _draw_roads(ax, roads_path, color="white", linewidth=0.8, alpha=0.7):
    """Internal: overlay roads from a GeoJSON file using geopandas."""
    try:
        import geopandas as gpd
        roads = gpd.read_file(roads_path)
        roads.plot(ax=ax, color=color, linewidth=linewidth, alpha=alpha)
    except Exception as e:
        print(f"Failed to plot roads: {e}")



def _make_legend():
    """Internal: create legend patches for the 5 classes."""
    return [
        mpatches.Patch(color=c, label=f"{n} ({l})")
        for c, n, l in zip(CLASS_COLORS, CLASS_NAMES, CLASS_LABELS)
    ]


def visualize_classification(classified, roi, ax=None, year=None, title=None, roads_path=None):
    """
    Render a classified map with a colour legend and optional roads overlay.

    Args:
        classified (ee.Image):      Classified image (single band 'classification').
        roi        (ee.FeatureCollection | ee.Geometry): Region.
        ax         (plt.Axes):      Optional matplotlib axes.
        year       (int):           Optional year label for the title.
        title      (str):           Optional custom title (overrides year).
        roads_path (str):           Optional path to roads GeoJSON.

    Returns:
        plt.Axes: The matplotlib axes with the rendered map.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 8))

    vis_params = {
        "min": 0,
        "max": NUM_CLASSES - 1,
        "palette": CLASS_COLORS,
    }

    try:
        img = _get_thumb(classified, roi, vis_params)
        extent = _get_extent(roi)
        ax.imshow(img, extent=extent, alpha=0.85)
        _draw_boundary(ax, roi)

        if roads_path:
            _draw_roads(ax, roads_path)

        ax.legend(handles=_make_legend(), loc="lower right", fontsize=8)

        if title:
            ax.set_title(title, fontsize=12)
        elif year:
            ax.set_title(f"Settlement Classification ({year})", fontsize=12)
        else:
            ax.set_title("Settlement Classification", fontsize=12)

        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_aspect("equal")
        ax.set_facecolor("white")

    except Exception as e:
        print(f"Visualisation error: {e}")

    return ax


def visualize_feature_importance(classifier, ax=None):
    """
    Bar chart of Random Forest feature importances (normalised to %).

    This shows which features contribute most to the classification.
    Texture features often rank high for settlement mapping.

    Args:
        classifier (ee.Classifier): Trained RF classifier.
        ax         (plt.Axes):      Optional axes.

    Returns:
        plt.Axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 5))

    importances = classifier.explain().get("importance").getInfo()
    values = [importances.get(b, 0) for b in FEATURE_BANDS]
    total  = sum(values) or 1
    pct    = [v / total * 100 for v in values]

    # Sort descending
    pairs  = sorted(zip(pct, FEATURE_BANDS), reverse=True)
    vals, names = zip(*pairs)

    colors = ["#e74c3c" if v > 10 else "#3498db" for v in vals]
    ax.barh(names[::-1], vals[::-1], color=colors[::-1])
    ax.set_xlabel("Importance (%)")
    ax.set_title("Random Forest — Feature Importance")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()

    return ax


def visualize_confusion_matrix(metrics, ax=None):
    """
    Plot the confusion matrix as a colour-coded heatmap.

    Args:
        metrics (dict): Output of evaluate_accuracy().
        ax      (plt.Axes): Optional axes.

    Returns:
        plt.Axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    cm = np.array(metrics["confusion_matrix"])
    im = ax.imshow(cm, cmap="Blues")
    plt.colorbar(im, ax=ax, shrink=0.8)

    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(int(cm[i, j])),
                    ha="center", va="center",
                    color="white" if cm[i, j] > cm.max()/2 else "black",
                    fontsize=9)

    ax.set_xticks(range(NUM_CLASSES))
    ax.set_yticks(range(NUM_CLASSES))
    ax.set_xticklabels(CLASS_NAMES, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(CLASS_NAMES, fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion Matrix (Test Set)")
    plt.tight_layout()

    return ax


def visualize_multi_year(results, roi, figsize_per_map=(8, 7), roads_path=None):
    """
    Display classified maps for multiple years side-by-side.

    This is the payoff of the "train once → classify many years" design.

    Args:
        results         (dict): {year: classified_ee_image, …} e.g. {2020: img, 2022: img}
        roi             (ee.FeatureCollection | ee.Geometry): Region boundary.
        figsize_per_map (tuple): (width, height) per subplot.
        roads_path      (str): Optional path to roads GeoJSON.

    Returns:
        plt.Figure
    """
    years = sorted(results.keys())
    n = len(years)
    fig, axes = plt.subplots(1, n,
                             figsize=(figsize_per_map[0] * n, figsize_per_map[1]))
    if n == 1:
        axes = [axes]

    for ax, yr in zip(axes, years):
        visualize_classification(results[yr], roi, ax=ax, year=yr, roads_path=roads_path)

    plt.tight_layout()
    plt.show()
    return fig


# ════════════════════════════════════════════════════════════════════════════
# 7.  PIPELINE  —  END-TO-END  CONVENIENCE  FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def run_pipeline(roi,
                 training_year,
                 target_years=None,
                 geojson_path=None,
                 roads_path=None,
                 n_trees=DEFAULT_N_TREES,
                 cloud_pct=DEFAULT_CLOUD_PCT,
                 train_fraction=DEFAULT_TRAIN_FRACTION,
                 seed=DEFAULT_SEED,
                 show_plots=True):
    """
    Complete classification pipeline: train once → classify many years.

    This function orchestrates the full workflow:

    1.  Build the feature composite for the training year.
    2.  Load training zones (from GeoJSON or defaults).
    3.  Sample pixels and split into train / test.
    4.  Train a Random Forest classifier.
    5.  Evaluate on the test set.
    6.  Classify the training year.
    7.  Classify each additional target year (reusing the same classifier).
    8.  Optionally visualise results.

    Args:
        roi            (ee.FeatureCollection): Study area boundary.
        training_year  (int):                  Year to train on (e.g. 2022).
        target_years   (list of int | None):   Additional years to classify.
                                                If None, only training_year is classified.
        geojson_path   (str | None):           Path to custom training GeoJSON.
                                                If None, uses default Nairobi zones.
        n_trees        (int):                  RF trees.
        cloud_pct      (int):                  Max cloud cover %.
        train_fraction (float):                Train/test split fraction.
        seed           (int):                  Random seed.
        show_plots     (bool):                 If True, display maps & charts.

    Returns:
        dict: {
            "classifier":           ee.Classifier,
            "metrics":              dict (accuracy metrics),
            "classified":           {year: ee.Image, …},
            "composites":           {year: ee.Image, …},
            "train_samples":        ee.FeatureCollection,
            "test_samples":         ee.FeatureCollection,
        }
    """
    # Determine all years to classify
    all_years = [training_year]
    if target_years:
        for y in target_years:
            if y not in all_years:
                all_years.append(y)
    all_years.sort()

    print("=" * 60)
    print(f"Settlement Classification Pipeline")
    print(f"Training year : {training_year}")
    print(f"Target years  : {all_years}")
    print("=" * 60)

    # ── STEP 1: Build training composite ──────────────────────────────────
    print(f"\n[1/{4 + len(all_years)}]  Building feature composite for training year {training_year}…")
    train_composite = build_feature_composite(roi, training_year, cloud_pct)

    # ── STEP 2: Load training zones ───────────────────────────────────────
    print(f"\n[2/{4 + len(all_years)}]  Loading training zones…")
    if geojson_path:
        zones = load_training_zones(geojson_path)
    else:
        print("Using DEFAULT Nairobi training zones.")
        zones = get_default_training_zones()

    # ── STEP 3: Sample & split ────────────────────────────────────────────
    print(f"\n[3/{4 + len(all_years)}]  Sampling & splitting data…")
    train_samples, test_samples = sample_and_split(
        train_composite, zones, train_fraction=train_fraction, seed=seed
    )

    # ── STEP 4: Train ────────────────────────────────────────────────────
    print(f"\n[4/{4 + len(all_years)}]  Training classifier…")
    classifier = train_classifier(train_samples, n_trees=n_trees)

    # ── STEP 5: Evaluate ─────────────────────────────────────────────────
    print(f"\n[5/{4 + len(all_years)}]  Evaluating accuracy…")
    metrics = evaluate_accuracy(test_samples, classifier)

    # ── STEP 6+: Classify each year ──────────────────────────────────────
    composites = {}
    classified = {}
    for i, yr in enumerate(all_years):
        step = 6 + i
        print(f"\n[{step}/{4 + len(all_years)}]  Classifying year {yr}…")
        if yr == training_year:
            comp = train_composite
        else:
            comp = build_feature_composite(roi, yr, cloud_pct)
        composites[yr] = comp
        classified[yr] = classify_image(comp, classifier).clip(roi)

    # ── Visualisation ────────────────────────────────────────────────────
    if show_plots:
        print("\nGenerating visualisations…")

        # 1. Feature importance + confusion matrix
        fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        visualize_feature_importance(classifier, ax=ax1)
        visualize_confusion_matrix(metrics, ax=ax2)
        plt.tight_layout()
        plt.show()

        # 2. Multi-year maps
        visualize_multi_year(classified, roi, roads_path=roads_path)

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)

    return {
        "classifier":    classifier,
        "metrics":       metrics,
        "classified":    classified,
        "composites":    composites,
        "train_samples": train_samples,
        "test_samples":  test_samples,
    }
