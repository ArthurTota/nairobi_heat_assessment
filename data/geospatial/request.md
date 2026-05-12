
To find those maps I went on [text](https://overpass-turbo.eu/) and looked for the following queries. To get how to use it I used [the official tag catalog](https://wiki.openstreetmap.org/wiki/Map_features) and [the Overpass API documentation](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL)

## To extract retail and food points from OpenStreetMap in Nairobi, use the following Overpass query:

```
[out:json][timeout:60];
(
  node["shop"~"supermarket|convenience|grocery|greengrocer|general"](-1.47,36.65,-1.15,37.12);
  way["shop"~"supermarket|convenience|grocery|greengrocer|general"](-1.47,36.65,-1.15,37.12);
  node["amenity"="marketplace"](-1.47,36.65,-1.15,37.12);
  way["amenity"="marketplace"](-1.47,36.65,-1.15,37.12);
);
out center;
```

## To extract water sources from OpenStreetMap in Nairobi, use the following Overpass query:
The emergency = drinking_water did not exist in Nairobi.
```
[out:json][timeout:60];
(
  node["amenity"="drinking_water"](-1.47,36.65,-1.15,37.12);
  node["amenity"="water_point"](-1.47,36.65,-1.15,37.12);
  node["man_made"="water_well"](-1.47,36.65,-1.15,37.12);
  node["man_made"="water_tap"](-1.47,36.65,-1.15,37.12);
);
out center;
```

## To extract green spaces from OpenStreetMap in Nairobi, use the following Overpass query:
```
[out:json][timeout:120];
(
  way["leisure"~"park|garden|nature_reserve"](-1.47,36.65,-1.15,37.12);
  relation["leisure"~"park|garden|nature_reserve"](-1.47,36.65,-1.15,37.12);
  way["landuse"~"recreation_ground|forest|meadow|grass"](-1.47,36.65,-1.15,37.12); relation["landuse"~"recreation_ground|forest|meadow|grass"](-1.47,36.65,-1.15,37.12);
  
  way["natural"~"grassland|wood"](-1.47,36.65,-1.15,37.12);
  relation["natural"~"grassland|wood"](-1.47,36.65,-1.15,37.12);
);
out geom;
```

## To extract cooling centers from OpenStreetMap in Nairobi, use the following Overpass query:
```
[out:json][timeout:60];
(
  node["amenity"~"library|community_centre|social_facility"](-1.47,36.65,-1.15,37.12);
  way["amenity"~"library|community_centre|social_facility"](-1.47,36.65,-1.15,37.12);
  node["amenity"="place_of_worship"](-1.47,36.65,-1.15,37.12);
  way["amenity"="place_of_worship"](-1.47,36.65,-1.15,37.12);
  node["building"="public"](-1.47,36.65,-1.15,37.12);
  way["building"="public"](-1.47,36.65,-1.15,37.12);
);
out center;
```

