# Nairobi Heat Vulnerability Assessment

**A semester project for the [EPFL ETHOS Lab](https://www.epfl.ch/labs/ethos/).**

## Project Overview
This project aims to assess the heat vulnerability of Nairobi. It addresses the tension between rising cooling demands, thermal stress in vulnerable neighborhoods, and climate mitigation objectives through comprehensive geospatial analysis.

The assessment is structured around three core pillars of vulnerability:
1. **Exposure**: Thermal exposure derived from Land Surface Temperature (LST) and classification of formal vs. informal settlements.
2. **Sensitivity**: Demographic factors, particularly analyzing high-resolution population density, including vulnerable age groups (elderly and children).
3. **Adaptive Capacity**: The ability of neighborhoods to cope with heat, measured through spatial proximity to resources like healthcare, water sources, green spaces, road networks, retail, and potential cooling centers.

## Project Structure

```text
Nairobi_Heat_Vulnerability_Assessment/
│
├── data/                    # Geospatial data, satellite imagery, and shapefiles
├── notebooks/               # Core analytical pipelines
│   ├── 1_1_heatmap.ipynb                 # LST and thermal exposure mapping
│   ├── 1_2_settlement_classification.ipynb # Formal/Informal settlement detection
│   ├── 2_1_sensitivity.ipynb             # Population demographic processing
│   └── 3_1_adaptive_capacity.ipynb       # Accessibility and infrastructure proximity
│
├── src/                     # Python helper modules for spatial analysis and data processing
│   ├── adaptive_capacity_helper.py
│   ├── sensitivity_helper.py
│   ├── settlement_classifier.py
│   └── ...
│
├── webapp/                  # Interactive webapp to visualize the results
├── results/                 # Generated maps for the webapp
├── docs/                    # Additional documentation and literature
├── requirements.txt         # Python environment dependencies
└── README.md                # This project overview
```

## Getting Started

### 1. Python Data Pipeline
The core data processing pipeline is built using Python, Jupyter Notebooks, and geospatial libraries like `geopandas`, `rasterio`, and the google eart engine API `gee`.

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Notebooks**: Navigate to the `notebooks/` directory and execute them in order (1.x -> 2.x -> 3.x) to generate the map layers and data. The scripts export processed web-ready map tiles into the `webapp/public/maps/` directory.

### 2. Interactive Web Dashboard
A Nuxt 4 / MapLibre GL based web application allows for an interactive exploration of the generated datasets, with features like layer opacity toggling to perform visual comparative analysis.

1. Navigate to the webapp:
   ```bash
   cd webapp
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
   Access the dashboard at `http://localhost:3000`.

## Current Status & Progress
- **Exposure**: The LST heatmap pipeline is well-established. The settlement classification model is functional but has room for improvement in training data.
- **Sensitivity**: General, elderly, and youth demographic profiles are integrated and mapped to the city grid. 
> We still have to present the population evolution and the income by neighbourhood.
- **Adaptive Capacity**: Proximity indices for key infrastructure (health, water, retail, green spaces, roads) have been successfully mapped using spatial distance algorithms.

## Acknowledgements
This work is conducted as part of an EPFL ETHOS Lab semester project under the supervision of Vasantha Ramani.
