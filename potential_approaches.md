# Approaches for generating polygon data from lat/long decimals
See https://en.wikipedia.org/wiki/Shapefile for the Shapefile format

## General Overview
-   Doing this in MYSQL does not seem viable
-   Using GDAL would probably be fastest
    - Mild inconvenience of having to manually ensure polygon is closed (last point = first)
    - Need to ensure polygons are clockwise
- Practically Geopandas+Shapely seems like the best appoach


## Creating polygons within python

For this approach it's best to leave the sql data alone as concatination seems to convert into text.

However, for use with Geopandas, we could use the non-standard MYSQL function "Point" to convert lat/long into a geometry column. This would allow us to directly import the data into a GeoDataFrame, saving one copy operation.

## Using Geopandas with Shapely

### Advantages
- Seems shapely automatically closes polygons
- also potentially forces them to have clockwise orientation (this needs testing)
- Fast operations with the dataframes

### Problems
- Lots of copying - though it turns out this doesn't seem too much of a problem - can happily process a cluster on my laptop in seconds

## Using pyshp
https://github.com/GeospatialPython/pyshp

### How to use
1. Specify fields
2. Create entries
    1. Add a geometry
    2. Write a "record" which contains field attributes

NB The geometries and records are matched in sequential order

### Advantages
- directly write polygons one line at a time
- avoid extra overhead of writing GeoJSON, write attributes based on position
- automatically closes polygon

### Problems
- apparently writes to file every time you enter a geometry or record (slow)
- Need to write points clockwise (as per shapefile standard)

## Using Fiona
https://fiona.readthedocs.io/en/stable/manual.html#introduction

https://fiona.readthedocs.io/en/stable/manual.html#writing-new-files-from-scratch



### Problems
- "Rules of thumb" suggest using other libraries such as SQLAlchemy, GeoAlchemy or ogr2agr
- Everything is done using GeoJSON format which increases memory use (have to write attribute headers for every entry)

## Using GDAL/OGR
This will probably run fastest

https://pcjericks.github.io/py-gdalogr-cookbook/geometry.html#create-a-polygon

https://pcjericks.github.io/py-gdalogr-cookbook/vector_layers.html#create-a-new-shapefile-and-add-data

See "setfield" at https://gdal.org/api/python/osgeo.ogr.html

### Advantages
- SetField seems to accept int id for attribute field, avoiding overhead of using the name as in GeoJSON


### Problems 
- write attributes using field title = similar overhead to using GeoJSON (so may as well use more convenient library eg Fiona)
- Need to manually ensure polygon is closed (last point = first point)
- Need to ensure points are clockwise



## Convert within MYSQL

The idea of this approach would be to run MYSQL code to convert the latitude/longitude decimals into Geometry types.

I did try using concat to get a single row per track 

There are two options: 

1. concatinate the lat/long into a big string and use the MYSQL function ST_GeomFromText() 
    - see https://dba.stackexchange.com/questions/206746/use-group-concat-to-generate-polygons-in-mysql
    - note in particular that group_concat_max_len will need to be increased


2. use the functions Point, LineString, Polygon
    - see https://dev.mysql.com/doc/refman/8.0/en/gis-mysql-specific-functions.html#function_point

I dislike option 1 because formatting into a string in order to reformat into a geospatial type is hacky

### Advantages
- Super fast
- Makes python code much simpler (just grab one already formed polygon at a time)

### Problems
- Huge headache to select the rows we want and feed them into the Polygon function



