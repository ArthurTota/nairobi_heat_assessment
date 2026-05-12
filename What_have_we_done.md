# Exposure 
## 1 - Heat map 
We have a pleasant and quite complete interface to make complete heat maps of Nairobi. Easely reproducilble for other towns. Land surface temperature.
## 2 - Formal/Informal settlement classification 
Heavy model missing some training data.
Ressources:
[text](https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php) for the built-up area of 2023. Worldwide so re-usable for every town 
What we are looking for is a dataset with formal and informal settlement already mapped.
Here are the road map:
[text](https://hub.tumidata.org/en/dataset/base-dataset-nairobi-kenya/resource/b51ae898-08f8-491c-8417-26c77279d7d7)

- Amelioration of the settlement classification:
1. Provide Better Training Polygons: The polygons defined in training_zones_template.geojson are probably grabbing too much bare soil inside the "Informal" class. I need to painfully and carefully draw precise polygons.
2. Train per Year (or Harmonize): Instead of training only on 2022, I should train separate Random Forests for 2020, 2022, and 2024, each using their own yearly composite.
3. Use a Dry-Season Filter: Instead of taking the median of the whole year ("2022-01-01" to "2022-12-31"), filter the images strictly to a dry month (e.g., only January to February) so that the vegetation levels are identical across all three years.

# Sensitivity 
## 1 - Population density 
## 2 - Population evolution 

# Adaptive Capacity 
## 1 - Income of the neighborhood 
## 2 - How close is the nearest hospital 
[Dataset hub](https://hub.tumidata.org/en/dataset/health_facilities_in_kenya_nairobi) where we found this map of [hospitals in Nairobi](https://hub.arcgis.com/datasets/Esri-EA::health-facilities-in-kenya/explore?location=-1.287668%2C36.834311%2C12).