# Nairobi HeatMap: Heat Vulnerability Assessment

## Project Overview
This project aims to assess the heat vulnerability of the built environment, focusing on thermal exposure and building performance, with a case study on Nairobi. 

Rising temperatures and rapid urbanization are significantly increasing cooling needs, often amplifying the Urban Heat Island (UHI) effect. This project addresses the tension between rising cooling demands, thermal stress in vulnerable neighborhoods, and climate mitigation objectives by exploring building performance, policy enforcement, and occupant behavior.

## Key Objectives
1. **Geospatial Analysis:** Estimate spatial patterns of heat exposure, cooling needs, and energy demand using thermal satellite data and high-resolution imagery.

## Proposed Project Structure

```text
Nairobi_HeatMap/
│
├── data/
│   ├── raw/                 # Raw datasets (satellite imagery, surveys, policy docs)
│   ├── processed/           # Cleaned and preprocessed data
│   └── geospatial/          # GIS data, shapefiles, thermal maps
│
├── notebooks/               # Jupyter notebooks for data exploration and analysis
│   ├── 01_data_preprocessing.ipynb
│   └── 02_geospatial_analysis.ipynb
│
├── src/                     # Source code for the assessment tool and data processing
│   ├── data_loader.py       # Scripts to fetch and load data
│   └── geospatial.py        # Geospatial processing functions
|
├── docs/                    # Documentation, literature review, and policy reports
│   └── literature_review.md
│
├── results/                 # Generated figures, tables, and maps for the final report
│   ├── figures/
│   └── outputs/
│
├── requirements.txt         # Python dependencies
└── README.md                # Project overview and instructions
```

## Getting Started
We first made a project decomposition in stages:
1. Exposure:
    - Heat Map: Not so easy but much more sourced and easy to reproduce than settlements classification. 
    - Settlements classification: Much harder than what imagined. The training data is hard to get right. Poor result:
        - Way of improvement: Make better training data. Train only on one season this way the vegetation and everything still the same. The model seems alright but maybe better models.
2. Sensitivity: The population density and evolution, more people there is 
3. Adaptor capacity: Income of the neighbourhood, how close from an hospital, 

## Expected Outcomes
- High-resolution spatial maps of heat exposure in Nairobi.
