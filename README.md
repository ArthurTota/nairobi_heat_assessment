# Nairobi Heat Vulnerability Assessment

**A semester project for the [EPFL ETHOS Lab](https://www.epfl.ch/labs/ethos/).**

## Project Overview
This project aims to assess the heat vulnerability of Nairobi. It addresses the tension between rising cooling demands, thermal stress in vulnerable neighborhoods, and climate mitigation objectives through comprehensive geospatial analysis.

The assessment is structured around three core pillars of vulnerability:
1. **Exposure**: Evaluating the physical heat stress. This is modeled using Land Surface Temperature (LST) focused strictly on the **dry season (June to September)** to avoid cloud-cover interference and capture peak heat. This axis also includes identifying settlements, particularly distinguishing informal (unplanned, highly exposed) vs. formal settlements.
2. **Sensitivity**: Assessing who is impacted. This relies on demographic data: population density and its evolution over time, as well as socioeconomic markers like income levels, and sensitive age groups (elderly and children).
3. **Adaptive Capacity**: The ability of neighborhoods to cope with and adapt to heat. This is measured through spatial proximity to critical cooling and coping resources such as hospitals, water sources, green spaces, road networks, and retail.

## Project Structure

```text
Nairobi_Heat_Vulnerability_Assessment/
│
├── data/                    # Geospatial data, satellite imagery, and shapefiles
|   ├── geospatial/
|   ├── images/
|   └── nairobi_geo_basedata/               # Too heavy to be pushed to Git, request acces if needed
├── notebooks/                              # Core analytical pipelines
│   ├── 1_1_heatmap.ipynb                   # LST and thermal exposure mapping
│   ├── 1_2_settlement_classification.ipynb # Binary formal/informal settlement detection
│   ├── 2_1_sensitivity.ipynb               # Population demographic processing
│   └── 3_1_adaptive_capacity.ipynb         # Accessibility and infrastructure proximity
│
├── src/                                    # Python helper modules for spatial analysis and data processing
│   ├── adaptive_capacity_helper.py
│   ├── sensitivity_helper.py
│   ├── settlement_classifier.py            # Random Forest ML pipeline for GEE
│   └── ...
│
├── webapp/                  # Interactive Nuxt 4 / MapLibre webapp to visualize results
├── docs/                    # Additional documentation and literature
├── requirements.txt         # Python environment dependencies
└── README.md                # This project overview
```

## Development & Methodology

### 1. Python Data Pipeline (Google Earth Engine & GeoPandas)
The core analytical backend relies on Python, Jupyter Notebooks, and the Google Earth Engine (GEE) API.
- **Exposure**: We use Sentinel-2 imagery combined with MODIS LST data. We specifically filter the temporal range to Nairobi's dry season (June 1st - September 30th) to ensure high-quality, cloud-free optical composite generation.
- **Sensitivity**: [demographic data](https://data.humdata.org/dataset/worldpop-population-counts-for-kenya) and [relative wealth index(sourc:Meta)](https://data.humdata.org/dataset/relative-wealth-index)
- **Adaptive Capacity**: We process local census/demographic datasets and OpenStreetMap (OSM) extractions. Proximity metrics to hospitals and water sources are computed as friction or distance surfaces.

### 2. Interactive Web Dashboard (Nuxt 4)
The visualization frontend is built in Nuxt 4 using MapLibre GL for dynamic rendering. 
The webapp features interactive threshold sliders (e.g., dynamically filtering informal settlements based on their mean LST), day/night modes, and composite toggles to overlay the three vulnerability axes. 

## Difficulties Encountered & Solutions
- **Informal Settlement Classification**: Early attempts used a 5-class model to distinguish different types of land cover. However, due to the spectral similarity of formal and informal "built-up" areas, accuracy was low.
  - *Solution*: We pivoted to a **binary classification system** (informal vs. not-informal) using Random Forest. By merging vegetation, roads, and formal residential into a single background class, the model can dedicate all its capacity to isolating informal settlements. We also incorporated **GLCM texture features**, which capture the chaotic spatial patterns of slums (tin roofs vs. structured formal streets), significantly improving detection.
- **Cloud Cover Interference**: Nairobi experiences significant cloud cover, which corrupted early optical composite processing and LST maps. 
  - *Solution*: We restricted our satellite image median composites exclusively to the dry season (June–September).
- **Nuxt Webapp Layering & Legibility**: With over 15 proximity and exposure datasets, displaying them clearly without overwhelming the user was challenging.
  - *Solution*: We exported raw values into the Alpha and Red channels of PNGs (via `export_web_maps.py`) and use MapLibre GL to apply client-side opacities and gradient mapping dynamically.

## Getting Started

1. **Python Pipeline**:
   ```bash
   pip install -r requirements.txt
   ```
   Navigate to the `notebooks/` directory and execute them sequentially. Make sure your GEE CLI is authenticated (`earthengine authenticate`) and a default project is set.

2. **Interactive Dashboard**:
   ```bash
   cd webapp
   npm install
   npm run dev
   ```
   Access the dashboard at `http://localhost:3000`.

## Acknowledgements
This work is conducted as part of an EPFL ETHOS Lab semester project under the supervision of Vasantha Ramani.
