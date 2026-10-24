# Summer UROP 2023 - Carbon Credits

All python code was written by me over 8 weeks in summer 2023. The R code and some comments were written by a collaborator.

The code connects to a remote SQL Database via the config file. This is a private database.


### To get up and running: 

Use "git clone" to get a copy of the project.
Use "pip install ." to install all the necessary packages. 

### All project code is inside mainCode:

#### mainCode/run_pipelines/

This contains the code to run. There are three working files:
- gpkg_from_all_areas.py which creates a geopackage file of all the active polygons globally
- dereg_from_all_areas.py which creates a geopackage file of all deregistered polygons globally. It will also create a file of all active polygons unless an existing file containing active polygons is specified.
- report_overlaps.py creates a CSV listing overlapping polygons and generates
 several gpkg files for visual inspection.

There is also the file "config.py" which is where the information for connecting to Sherwood is stored. This will need to be edited for the appropriate user.

#### mainCode/lib
This contains all the source code for the project.

## Why does the code run on all areas?
Unfortunately the way the polygons are divided into areas/clusters means there is no way of guaranteeing no overlap without checking the whole collection. This probably could be run on a per-country basis but I've optimised the code enough that it can run everything on a laptop.

## Understanding the output of report_overlaps.py
This outputs two CSVs (negligible and significant) and several shape files.
The CSVs give identifying information for pairs of overlapping polygons:
- The overlap_1/2 columns list the overlap area as a proportion of the polygons
- The type column labels the type of overlap:
    - Type 6 means the two totally overlap
    - Type 5 means the first polygon is contained within the second
    - Type 4 means the first polygon contains the second
    - Type 3 means there is a large proportion of overlap
    - Type 2 means the two overlap at a border (up to 20%)
    - Type 1 means the overlap is negligible (less than 5%)
 - The various shapefiles should be opened in QGIS and allows for visual inspection of the polygons. These are named appopriately.

