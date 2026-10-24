from TISTpolygons.lib.utils import polygon_area
from geopandas import GeoDataFrame
from shapely import intersection
from pandas import DataFrame
import logging
logger = logging.getLogger(__name__)


def resolve_overlaps(intersections: DataFrame, polygons: DataFrame, metadata: DataFrame | None = None, dividing_points = [0, 0.2, 0.5, 0.8, 1])->None:
    """Crop or remove polygons. This is done IN PLACE

    interesections must contain columns: trackid_1, trackid_2, locationid_1, locationid_2, geometry where the geometry column contains overlaps


    polygons must be indexed by trackid. If metadata not supplied, polygons must contain valid_start column

    metadata must be indexed by locationid and must have a valid_start column

     
    Resolution is performed by iterating through "intersections" twice:
        In the first pass, any cases which result in a polygon being marked as "removed" are carried out
        In the second pass, any cases which result in a polygon being cut are carried out.

    First, check all cases where one polygon is to be marked as removed.
    Second, check all cases where one polygon is to be cut-up
    """


    intersections['resolved'] = 0  # Kept as int rather than bool so we can count and sanity check

    polygons['removed'] = False

    # propArea is the proportion of area remaining compared to original
    polygons['fracArea'] = 1.0

    def categorise(proportion):
        """bins for classifying the type of overlap
        proportion is calculated as intersect_area/polygon_area"""
        if proportion <= dividing_points[1]: return 1
        elif proportion <= dividing_points[2]: return 2
        elif proportion <= dividing_points[3]: return 3
        elif proportion > dividing_points[3]: return 4 # Sometimes after cuts, the interesction proportion is greater than 1


    def _resolve_removal(row_index, trackid_1, trackid_2, catA, catB, metadataA, metadataB, intersections, polygons):
        if catA == 1 and catB == 2:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave A alone

            # Remove B
            polygons.loc[trackid_2, 'removed'] = True

        if catA == 2 and catB == 1:
            # Polygon B is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave B alone

            # Remove A
            polygons.loc[trackid_1, 'removed'] = True
            
        if catA == 1 and catB == 3:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave A alone

            # Remove B
            polygons.loc[trackid_2, 'removed'] = True

        if catA == 3 and catB == 1:
            # Polygon B is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave B alone

            # Remove A
            polygons.loc[trackid_1, 'removed'] = True

        if catA == 1 and catB == 4:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave A alone

            # Remove B
            polygons.loc[trackid_2, 'removed'] = True

        if catA == 4 and catB == 1:
            # Polygon B is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave B alone

            # Remove A
            polygons.loc[trackid_1, 'removed'] = True

        if catA == 2 and catB == 4:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave A alone

            # Remove B
            polygons.loc[trackid_2, 'removed'] = True

        if catA == 4 and catB == 2:
            # Polygon B is bigger
            intersections.loc[row_index, 'resolved'] += 1

            # Leave B alone

            # Remove A
            polygons.loc[trackid_1, 'removed'] = True

        if catA == 3 and catB == 3:
            intersections.loc[row_index, 'resolved'] += 1

            # Remove younger
            if metadataA['valid_start'] < metadataB['valid_start']:
                # To edit in place, we must 
                polygons.loc[trackid_2, 'removed'] = True
            else:
                polygons.loc[trackid_1, 'removed'] = True


        if catA == 3 and catB == 4:
            intersections.loc[row_index, 'resolved'] += 1

            # Remove younger
            if metadataA['valid_start'] < metadataB['valid_start']:
                # To edit in place, we must 
                polygons.loc[trackid_2, 'removed'] = True
            else:
                polygons.loc[trackid_1, 'removed'] = True

        if catA == 4 and catB == 3:
            intersections.loc[row_index, 'resolved'] += 1

            # Remove younger
            if metadataA['valid_start'] < metadataB['valid_start']:
                # To edit in place, we must 
                polygons.loc[trackid_2, 'removed'] = True
            else:
                polygons.loc[trackid_1, 'removed'] = True

        if catA == 4 and catB == 4:
            intersections.loc[row_index, 'resolved'] += 1

            # Remove younger
            if metadataA['valid_start'] < metadataB['valid_start']:
                # To edit in place, we must 
                polygons.loc[trackid_2, 'removed'] = True
            else:
                polygons.loc[trackid_1, 'removed'] = True

    def _resolve_cut(row_index, trackid_1, trackid_2, polygonA, polygonB, catA, catB, metadataA, metadataB, intersections, polygons):

        if catA == 1 and catB == 1:
            intersections.loc[row_index, 'resolved'] += 1
            if metadataA['valid_start'] < metadataB['valid_start']:
                # To edit in place, we must 
                polygons.loc[trackid_2, 'geometry'] = polygonB - polygonA
            else:
                polygons.loc[trackid_1, 'geometry'] = polygonA - polygonB

        if catA == 2 and catB == 2:
            intersections.loc[row_index, 'resolved'] += 1

            if metadataA['valid_start'] < metadataB['valid_start']:
                # Cut from B, need to multiply B's tree data by (1-overlap)
                polygons.loc[trackid_2, 'geometry'] = polygonB - polygonA
            else:
                # Cut from A, need to multiply A's tree data by (1-overlap)
                polygons.loc[trackid_1, 'geometry'] = polygonA - polygonB

        if catA == 2 and catB == 3:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            if metadataA['valid_start'] < metadataB['valid_start']:
                # Cut from B, need to multiply B's tree data by (1-overlap)
                polygons.loc[trackid_2, 'geometry'] = polygonB - polygonA
            else:
                # Cut from A, need to multiply A's tree data by (1-overlap)
                polygons.loc[trackid_1, 'geometry'] = polygonA - polygonB

        if catA == 3 and catB == 2:
            # Polygon A is bigger
            intersections.loc[row_index, 'resolved'] += 1

            if metadataA['valid_start'] < metadataB['valid_start']:
                # Cut from B, need to multiply B's tree data by (1-overlap)
                polygons.loc[trackid_2, 'geometry'] = polygonB - polygonA
            else:
                # Cut from A, need to multiply A's tree data by (1-overlap)
                polygons.loc[trackid_1, 'geometry'] = polygonA - polygonB


    # First pass - check for cases where a polygon will be discarded
    for row_index, row in intersections.iterrows():
        trackid_1 = row['trackid_1']
        trackid_2 = row['trackid_2']
        locationid_1 = row['locationid_1']
        locationid_2 = row['locationid_2']


        if metadata is None:
            # Assume that polygons already contains the necessary information
            metadataA = polygons.loc[locationid_1]
            metadataB = polygons.loc[locationid_2]
        else:
            metadataA = metadata.loc[locationid_1]
            metadataB = metadata.loc[locationid_2]




        polygonA = polygons.loc[trackid_1, 'geometry'] 
        polygonB = polygons.loc[trackid_2, 'geometry'] 
        areaA = polygon_area(polygonA)
        areaB = polygon_area(polygonB)
        areaX = polygon_area(row.geometry)

        propA = areaX/areaA
        propB = areaX/areaB

        catA = categorise(propA)
        catB = categorise(propB)
        
        _resolve_removal(row_index, trackid_1, trackid_2, catA, catB, metadataA, metadataB, intersections, polygons)


    # Second pass - check for cases where a polygon will be cut. We also need to check if polygons now need to be discard after being cut.
    for row_index, row in intersections.loc[intersections['resolved'] == 0].iterrows():
        trackid_1 = row['trackid_1']
        trackid_2 = row['trackid_2']


        if polygons.loc[trackid_1, 'removed'] == True or polygons.loc[trackid_2, 'removed'] == True:
            intersections.loc[row_index, 'resolved'] += 1
            continue


        locationid_1 = row['locationid_1']
        locationid_2 = row['locationid_2']

        metadataA = metadata.loc[locationid_1]
        metadataB = metadata.loc[locationid_2]

        polygonA = polygons.loc[trackid_1, 'geometry'] 
        polygonB = polygons.loc[trackid_2, 'geometry'] 
        areaA = polygon_area(polygonA)
        areaB = polygon_area(polygonB)

        if (areaA == 0) or (areaB == 0):
            if areaA == 0: polygons.loc[trackid_1, 'removed'] == True
            if areaB == 0: polygons.loc[trackid_2, 'removed'] == True
            intersections.loc[row_index, 'resolved'] += 1
            continue
        
        # Calculate intersection as we go
        intersect = intersection(polygonA, polygonB)
        areaX = polygon_area(intersect)

        if areaX == 0:
            intersections.loc[row_index, 'resolved'] += 1
            continue

        propA = areaX/areaA
        propB = areaX/areaB

        catA = categorise(propA)
        catB = categorise(propB)

        # Cases where a polygon will be cut

        
        _resolve_cut(row_index, trackid_1, trackid_2, polygonA, polygonB, catA, catB, metadataA, metadataB, intersections, polygons)
        _resolve_removal(row_index, trackid_1, trackid_2, catA, catB, metadataA, metadataB, intersections, polygons)

        # The code would run faster if the section below were calculated in _resolve_cut but it saves me typing to do it here
        # Though at the moment, 90% of time is spent just downloading the polygons anyway so not a big deal
        final_polygonA = polygons.loc[trackid_1, 'geometry'] 
        final_polygonB = polygons.loc[trackid_2, 'geometry'] 
        final_areaA = polygon_area(final_polygonA)
        final_areaB = polygon_area(final_polygonB)

        polygons.loc[trackid_1, 'fracArea'] *= final_areaA/areaA
        polygons.loc[trackid_2, 'fracArea'] *= final_areaB/areaB

        if final_areaA == 0: polygons.loc[trackid_1, 'removed'] == True
        if final_areaB == 0: polygons.loc[trackid_2, 'removed'] == True

    if sum(intersections['resolved']==0) > 0: raise Exception(f"Not every conflict was resolved!")

def resolve_superceded_polygons(intersections: GeoDataFrame, dereg_polygons: GeoDataFrame, active_polygons: GeoDataFrame, threshold=0.2):
    """Compare deregistered polygons with active polygons. If a the total proportion of overlap is greater than threshold, 
    mark the deregistered polygon as superceded.  
    I would recommend being harsh with the threshold. During testing about half the degregistered polygons had no overlap...
     and two-thirds had overlap less than 0.1. Above this the distribution was very flat with a small increase at >0.8.
     
    Intersections must have columns: trackid_1, trackid_2, geometry
    dereg_polygons and active polygons must be indexed by trackid"""


    dereg_polygons['total_overlap'] = 0
    dereg_polygons['superceded'] = False



    for row_index, row in intersections.iterrows():
        dereg_trackid = row['trackid_1']
        dereg_polygon = dereg_polygons.loc[dereg_trackid, 'geometry']
        overlap_polygon = row['geometry']
        dereg_area = polygon_area(dereg_polygon)
        overlap_area = polygon_area(overlap_polygon)

        prop_overlap = overlap_area/dereg_area

        dereg_polygons.loc[dereg_trackid, 'total_overlap'] += prop_overlap

    for row_index, row in intersections.iterrows():
        dereg_trackid = row['trackid_1']
        active_trackid = row['trackid_2']

        overlap_polygon = row['geometry']
        dereg_polygon = dereg_polygons.loc[dereg_trackid, 'geometry']
        active_polygon = active_polygons.loc[active_trackid, 'geometry']

        total_overlap = dereg_polygons.loc[dereg_trackid, 'total_overlap']

        if total_overlap < threshold:
            dereg_polygons.loc[dereg_trackid, 'geometry'] = dereg_polygon - active_polygon

        else:
            dereg_polygons.loc[dereg_trackid, 'superceded'] = True


def show_border_overlap(intersections: DataFrame, polygons: DataFrame, dividing_point = 0.3)->None:
    """Helper tool for identifying appropriate border overlap threshols - don't use this"""
    polygons['overlap'] = 0
    intersections['overlap'] = 0
    for row_index, row in intersections.loc[intersections['resolved'] == 0].iterrows():
        trackid_1 = row['trackid_1']
        trackid_2 = row['trackid_2']


        polygonA = polygons.loc[trackid_1, 'geometry'] 
        polygonB = polygons.loc[trackid_2, 'geometry'] 
        areaA = polygon_area(polygonA)
        areaB = polygon_area(polygonB)
        areaX = polygon_area(row.geometry)

        propA = areaX/areaA
        propB = areaX/areaB

        maxprop = max((propA, propB))

        if maxprop <= dividing_point:
            polygons.loc[trackid_1, 'overlap'] = propA
            polygons.loc[trackid_2, 'overlap'] = propB
            intersections[row_index, 'overlap'] = maxprop

def label_overlaps(intersections: DataFrame, metadata: DataFrame, polygons: DataFrame, dividing_points = [0, 0.05, 0.2, 0.8, 1])->None:
    """
    In place adds a label column to the "intersections" dataframe denoting type of overlap. Additionally records overlap fraction in "polygons"

    interesections must contain columns: trackid_1, trackid_2, locationid_1, locationid_2, geometry where the geometry column contains overlaps

    preferably intersections contains additional useful columns eg groupid, clusterid, areaid (_1/_2)

    polygons must be indexed by trackid 
    """


    # Column for labelling overlap type
    intersections['type'] = 0

    # Columns for recording fractional overlap
    intersections['overlap_1'] = 0
    intersections['overlap_2'] = 0

    # Column for recording fractional overlap
    # Somewhat useless as multiple overlaps take random priority
    polygons['overlap'] = 0

    # Should really specify a small dtype for this
    polygons['negligible_overlap'] = 0
    polygons['significant_overlap'] = 0
    polygons['border_overlap'] = 0

    def categorise(proportion):
        """bins for classifying the type of overlap
        proportion is calculated as intersect_area/polygon_area"""
        if proportion <= dividing_points[1]: return 1
        elif proportion <= dividing_points[2]: return 2
        elif proportion <= dividing_points[3]: return 3
        elif proportion > dividing_points[3]: return 4 

    # Overlap types, based on pairs labelled by the above categories
    # There should be 16 pairs (4^2)
    negligible_overlap = [(1,1)]


    border_overlap = [(1,2),
                      (2,1),
                      (2,2)]
    
    significant_overlap = [(1,3),
                           (3,1),
                           (2,3),
                           (3,2),
                           (3,3),
                           ]    
    
    # First entry contains second entry
    contains_overlap = [(1,4),
                        (2,4),
                        (3,4)]
    
    # First entry is contained by second entry
    contained_overlap = [(4,1),
                         (4,2),
                         (4,3)]
    
    total_overlap = [(4,4)]



    for row_index, row in intersections.iterrows():
        trackid_1 = row['trackid_1']
        trackid_2 = row['trackid_2']
        locationid_1 = row['locationid_1']
        locationid_2 = row['locationid_2']


        polygonA = polygons.loc[trackid_1, 'geometry'] 
        polygonB = polygons.loc[trackid_2, 'geometry'] 
        areaA = polygon_area(polygonA)
        areaB = polygon_area(polygonB)
        areaX = polygon_area(row.geometry)

        propA = round(areaX/areaA, 3)
        propB = round(areaX/areaB, 3)

        catA = categorise(propA)
        catB = categorise(propB)
        
        polygons.loc[trackid_1, 'overlap'] = propA
        polygons.loc[trackid_2, 'overlap'] = propB

        intersections.loc[row_index, 'overlap_1'] = propA
        intersections.loc[row_index, 'overlap_2'] = propB

        if (catA, catB) in negligible_overlap:
            overlap_type = 1

        if (catA, catB) in border_overlap:
            overlap_type = 2
        if (catA, catB) in significant_overlap:
            overlap_type = 3
        if (catA, catB) in contains_overlap:
            overlap_type = 4
        if (catA, catB) in contained_overlap:
            overlap_type = 5
        if (catA, catB) in total_overlap:
            overlap_type = 6

        intersections.loc[row_index, 'type'] = overlap_type


        # Could instead keep lists of the trackid's to reduce shapefile size - this is actually a negligible contribution compared to the tracks
        if overlap_type == 1:
            polygons.loc[trackid_1, 'negligible_overlap'] = True
            polygons.loc[trackid_2, 'negligible_overlap'] = True
        
        elif overlap_type == 2:
            polygons.loc[trackid_1, 'border_overlap'] = True
            polygons.loc[trackid_2, 'border_overlap'] = True

        else:
            polygons.loc[trackid_1, 'significant_overlap'] = True
            polygons.loc[trackid_2, 'significant_overlap'] = True






    if sum(intersections['type']==0) > 0: raise Exception(f"Not every conflict was resolved!")           