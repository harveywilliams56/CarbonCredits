from mainCode.lib import utils, chunking, fix_polygons

import logging
import numpy as np
import geopandas as gpd
import pandas as pd
from shapely import geometry
from shapely import Polygon, MultiPolygon
from pyproj import Geod
from array import array
import os

logger = logging.getLogger(__name__)

"""Each function reresents the majority of a pipeline. They're called by programs in the run_pipelines folder"""


def gpkg_from_clusters(clusterids, f_metadata_query, f_tracks_query, datafetcher: utils.DataFetcher, filepath, write_mode="w", keep_raw=False)->gpd.GeoDataFrame:
    """Create a filtered and edited shapefile based on SQL queries which give tracks and metadata
    f_metadata_query must be a function which returns a metadata_query given clusterid.
    f_tracks_query must be a function which returns a tracks_query given clusterid.
    metadata_query must be an SQL query with columns locationid, trackid, valid_start
    tracks_query must be an SQl query with columns pointid, trackid, longitude, latitude"""

    # Check ahead of time if we will be able to write file. Make a new directory if necessary.
    utils.validate_filepath(filepath)
   

    # Fetch and pre-process dataframes from database
    if keep_raw == True:
        raw_polygons = utils.polygons_from_clusters(clusterids, f_tracks_query, datafetcher, simplify=False)
        polygons = raw_polygons.copy()
        polygons['geometry'] = utils.simplify_polygons(polygons['geometry'])

    polygons = utils.polygons_from_clusters(clusterids, f_tracks_query, datafetcher)
    metadata = utils.metadata_from_clusters(clusterids, f_metadata_query, datafetcher)

    if (polygons is None) or (metadata is None):
        logger.warning("WARNING: no polygons/metadata to save. Check SQL queries.")
        print("WARNING: no polygons/metadata to save. Check SQL queries")
        return None

    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    # NB polygons must also contain a column 'trackid' because the index is dropped when calculating intersections
    polygons = polygons.merge(metadata, left_index=True, right_on='trackid')
   
    if polygons.index.name != 'trackid':
        polygons.reset_index(inplace=True)
        polygons.set_index(polygons['trackid'], inplace=True)
    else:
        polygons['trackid']=polygons.index


    # Pre-filter
    # NB simplify treats the coordinates as if they are Cartesian but this is fine because they effectively are 
    # ..at the level of a single farm. Consider the local tangent plane (sin(longitude-offset), sin(latitude-offset))
    # This processing step is already done in utils.polygons_from_clusters unless simplify is set to false
    """
    polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))
    polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']
    """

    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    with utils.log_time(logger, "calculating intersections"):
        intersections = polygons.overlay(polygons)

    # Remove self-comparisons
    intersections = intersections.query("trackid_1 != trackid_2")

    # Remove duplicates that arise from comparing a dataframe with itself
    intersections = intersections.query("trackid_1 < trackid_2")

    # Resolve overlaps
    with utils.log_time(logger, "resolving_intersections"):  
        fix_polygons.resolve_overlaps(intersections, polygons, metadata=metadata, dividing_points=[0, 0.3, 0.5, 0.8, 1])

    # Calculate area
    with utils.log_time(logger, "calculating all areas"):
        polygons['area_m2'] = polygons['geometry'].apply(utils.polygon_area).astype('uint32')

    # Post-filter
    final = polygons.loc[(polygons['geometry'].geom_type == 'Polygon')&(polygons['removed'] == False)].drop(['trackid', 'removed'], axis='columns')
    

    # Write to file
    utils.gdf_to_gpkg(final, filepath, mode=write_mode)


    # Write CSV
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)
    csv_filename = os.path.splitext(filename)[0] + ".csv"
    csv_filepath = os.path.join(directory, csv_filename)
    final.drop('geometry', axis='columns', inplace=False).to_csv(csv_filepath)

    # Need to be careful not to overwrite "final" as it is returned for use by other code.
    if keep_raw == True:
        filename = os.path.basename(filepath)
        directory = os.path.dirname(filepath)
        raw_filename = os.path.splitext(filename)[0] + "_raw" + os.path.splitext(filename)[1]
        raw_filepath = os.path.join(directory, raw_filename)

        # Overwriting original metadata to save memory - will need to rename if you want to use later
        # Using copy to prevent messing up 'final' which will be returned later
        metadata = polygons.loc[:, polygons.columns!='geometry'].copy()
        
        # Fiddling with columns/indices
        # This might generate a warning about editing a slice
        if metadata.index.name == 'trackid':
            metadata.drop('trackid', axis='columns', errors='ignore', inplace=True)
        if metadata.index.name != 'locationid':
            metadata.set_index('locationid', inplace=True)

        if raw_polygons.index.name != 'trackid':
            raw_polygons.set_index('trackid', inplace=True)


        # Merge the metadata about cuts etc to the raw polygons
        raw_polygons=raw_polygons.merge(metadata, left_index=True, right_on='locationid')

        final_raw = raw_polygons.loc[raw_polygons['geometry'].geom_type=='Polygon']
        utils.gdf_to_gpkg(final_raw, raw_filepath)

    return final


def dereg_gpkg_from_clusters(clusterids, f_dereg_metadata_query, f_dereg_tracks_query, 
                            datafetcher: utils.DataFetcher, dereg_output_filepath,
                            active_input_filepath=None,
                            f_active_metadata_query=None, f_active_tracks_query=None, active_output_filepath=None):
    """Create a filtered and edited GeoPackage file containing deregistered locations. Save to dereg filepath.
    You are advised to include either an active_polygons_filepath or the f_active... queries so that deregistered locations
    overlapping active locations are ignored.

    f_metadata_query must be a function which returns a metadata_query given clusterid.
    f_tracks_query must be a function which returns a tracks_query given clusterid.
    dereg_metadata_query must be an SQL query with columns locationid, trackid, valid_start, valid_end
    active_metadata_query must be an SQL query with columns locationid, trackid, valid_start
    tracks_query must be an SQl query with columns pointid, trackid, longitude, latitude
    """

    # The step where we resolve overlaps could do with minor adjustment

    compare_active=False

    # Check ahead of time if we will be able to write file. Make a new directory if necessary.
    output_directory = os.path.dirname(dereg_output_filepath)
    if active_output_filepath is None:
        active_output_filepath = output_directory+"/active.gpkg"
    
    utils.validate_filepath(dereg_output_filepath)
    utils.validate_filepath(active_output_filepath)
                                        
    # Fetch and pre-process dataframes from database

    if active_input_filepath is not None:
        active_polygons=gpd.read_file(active_input_filepath)
        compare_active = True

    elif (f_active_metadata_query is not None) and (f_active_tracks_query is not None):
        gpkg_from_clusters(clusterids, f_active_metadata_query, f_active_tracks_query,  datafetcher, active_output_filepath)
        active_polygons=gpd.read_file(active_output_filepath)
        compare_active=True

    if compare_active==False: print("WARNING: You are loading all deregistered locations and not checking if they overlap with active locations.")

    # Metadata remove duplicates should be set to false - see below for why
    dereg_polygons = utils.polygons_from_clusters(clusterids, f_dereg_tracks_query, datafetcher)
    dereg_metadata = utils.metadata_from_clusters(clusterids, f_dereg_metadata_query, datafetcher, remove_duplicates=False) 


    # Use maximum cluster2group linkid as a proxy for the most recent cluster
    if dereg_metadata.index.name == 'locationid':
        dereg_metadata.reset_index(inplace=True)

    dereg_metadata = dereg_metadata.groupby('locationid').apply(lambda df: df.loc[df['c2g_linkid'].idxmax()])
    dereg_metadata.set_index('locationid', inplace=True)


    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    # NB polygons must also contain a column 'trackid' because the index is dropped when calculating intersections

    dereg_polygons = dereg_polygons.merge(dereg_metadata, left_index=True, right_on='trackid')
   
    if dereg_polygons.index.name != 'trackid':
        dereg_polygons.reset_index(inplace=True)
        dereg_polygons.set_index('trackid', inplace=True)
    
    dereg_polygons['trackid']=dereg_polygons.index


    # Pre-filter
    # NB simplify treats the coordinates as if they are Cartesian but this is fine because they effectively are 
    # ..at the level of a single farm. Consider the local tangent plane (sin(longitude-offset), sin(latitude-offset))
    # This processing step is already done in utils.polygons_from_clusters unless simplify is set to false
    """
    polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))
    polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']
    """

    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    with utils.log_time(logger, "calculating intersections"):
        intersections = dereg_polygons.overlay(dereg_polygons)

    # Remove self-comparisons
    intersections = intersections.query("trackid_1 != trackid_2")

    # Remove duplicates that arise from comparing a dataframe with itself
    intersections = intersections.query("trackid_1 < trackid_2")


    # Resolve overlaps
    #~~~~~~~~~~~~~~ fix_polygons.resolve_overlaps tends to keep older polygons.
    #~~~~~~~~~~~~~~ However, for deregistered polygons, it's more sensible to keep newer polygons.
    #~~~~~~~~~~~~~~ The simplest fix would be to make a copy of resolve_overlaps() with the inequalities reversed
    with utils.log_time(logger, "resolving_intersections"):  
        fix_polygons.resolve_overlaps(intersections, dereg_polygons, metadata=dereg_metadata, dividing_points=[0, 0.3, 0.5, 0.8, 1])


    with utils.log_time(logger, "calculating all areas"):
        dereg_polygons['area_m2'] = dereg_polygons['geometry'].apply(utils.polygon_area).astype('uint32')

    if compare_active == False:
        # Post-filter
        dereg_final = dereg_polygons.loc[(dereg_polygons['geometry'].geom_type == 'Polygon')&(dereg_polygons['removed'] == False)].drop(['trackid', 'removed'], axis='columns')

        # Write to file
        utils.gdf_to_gpkg(dereg_final, dereg_output_filepath)

        return
    

    #### The below should only executed if compare_active is True ####

    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    # NB polygons must also contain a column 'trackid' because the index is dropped when calculating intersections
    active_polygons.set_index('trackid', inplace=True)
    active_polygons['trackid'] = active_polygons.index

    intersections = dereg_polygons.overlay(active_polygons)

    fix_polygons.resolve_superceded_polygons(intersections, dereg_polygons, active_polygons, threshold=0.2)

    dereg_final = dereg_polygons.loc[(dereg_polygons['geometry'].geom_type == 'Polygon')&(dereg_polygons['removed'] == False)&(dereg_polygons['superceded']==False)].drop(['trackid', 'removed', 'superceded'], axis='columns')

    utils.gdf_to_gpkg(dereg_final, dereg_output_filepath)

    # Write CSV
    filename = os.path.basename(dereg_output_filepath)
    directory = os.path.dirname(dereg_output_filepath)
    csv_filename = os.path.splitext(filename)[0] + ".csv"
    csv_filepath = os.path.join(directory, csv_filename)
    dereg_final.drop('geometry', axis='columns', inplace=False).to_csv(csv_filepath)



def overlaps_from_clusters(clusterids, f_metadata_query, f_tracks_query, datafetcher: utils.DataFetcher, root_filepath)->None:
    """Create shapefiles displaying overlaps and a CSV listing them.
    f_metadata_query must be a function which returns a metadata_query given clusterid.
    f_tracks_query must be a function which returns a tracks_query given clusterid.
    metadata_query must be an SQL query with columns locationid, trackid, valid_start
    tracks_query must be an SQl query with columns pointid, trackid, longitude, latitude
    """

    # Check ahead of time if we will be able to write file - make a new directory if necessary
    directory = os.path.dirname(root_filepath)
    if directory == "":
        root_filepath = "overlaps/"

    utils.validate_filepath(root_filepath)



    # Fetch dataframes from remote
    polygons = utils.polygons_from_clusters(clusterids, f_tracks_query, datafetcher, simplify=False)
    metadata = utils.metadata_from_clusters(clusterids, f_metadata_query, datafetcher)

    # Reduce precision of date and also convert to string - this means that dates can no longer be compared
    metadata['valid_start'] = metadata['valid_start'].apply(lambda x: x.date()).astype(str)


    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    polygons = polygons.merge(metadata, left_index=True, right_on='trackid')

    if polygons.index.name != 'trackid':
        polygons.reset_index(inplace=True)
        polygons.set_index(polygons['trackid'], inplace=True)
    else:
        polygons['trackid']=polygons.index

    # Store a copy of the raw tracks for visual inspection
    raw_tracks = polygons['geometry'].copy()

    # Pre-filter
    # NB simplify treats the coordinates as if they are Cartesian but this is fine because they effectively are 
    # ..at the level of a single farm. Consider the local tangent plane (sin(longitude-offset), sin(latitude-offset))
    polygons['geometry'] = utils.simplify_polygons(polygons['geometry'])
    
    # Commented-out to allow non-polygons
    # polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']

    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    intersections = polygons.overlay(polygons)

    # Remove self-comparisons, NB duplicates of form (A, B) ~ (B, A) are left in place
    intersections = intersections.query("trackid_1 != trackid_2")


    # Resolve overlaps
    fix_polygons.label_overlaps(intersections, metadata, polygons)

    # Re-set the geometry to the raw_tracks for visualisation
    polygons['geometry'] = raw_tracks

    # Write CSV
    intersections.loc[intersections['type']==1].drop('geometry', axis='columns').to_csv(f"{root_filepath}_negligible_overlaps.csv")
    intersections.loc[intersections['type']!=1].drop('geometry', axis='columns').to_csv(f"{root_filepath}_significant_overlaps.csv")

    # Write overlaps to shapefiles
    for overlap_type in [1,2,3,4,5,6]:
        utils.gdf_to_gpkg(intersections.loc[intersections['type']==overlap_type], f"{root_filepath}_overlap_type_{overlap_type}.gpkg")

    # Write polygons involved in overlaps to shapefiles
    polygons.drop('trackid', axis='columns', inplace=True)
    utils.gdf_to_gpkg(polygons.loc[polygons['significant_overlap']==True], f"{root_filepath}_significant_overlap.gpkg")
    utils.gdf_to_gpkg(polygons.loc[polygons['negligible_overlap']==True], f"{root_filepath}_negligible_overlap.gpkg")
    utils.gdf_to_gpkg(polygons.loc[polygons['border_overlap']==True], f"{root_filepath}_border_overlap.gpkg")





def report_bad_tracks(metadata_query: str, tracks_query: str, datafetcher: utils.DataFetcher, root_filepath: str)->None:
    """Create a shapefile and CSV detailing bad tracks
    f_metadata_query must be a function which returns a metadata_query given clusterid.
    f_tracks_query must be a function which returns a tracks_query given clusterid.
    metadata_query must be an SQL query with columns locationid, trackid, valid_start
    tracks_query must be an SQl query with columns pointid, trackid, longitude, latitude"""
    
    # Fetch dataframes from remote
    metadata = utils.metadata_from_SQL(metadata_query, datafetcher)
    tracks = datafetcher.SQL_to_dataframe(tracks_query)

    # Get trackid of tracks with fewer than three points
    less_than_three = tracks.groupby('trackid').filter(lambda x: len(x.index) < 3).drop_duplicates(subset='trackid', keep='first')[['trackid']]

    # Get tracks which contain a 0
    zero_tracks = tracks.groupby('trackid').filter(lambda df: 0 in df[['longitude', 'latitude']].values)

    # Remove 0 points but leave the rest of the track
    tracks = tracks[(tracks['longitude']!=0)&(tracks['latitude']!=0)]

    # Get tracks which have spurious points
    max_difference_degrees = 0.02
    tracks = tracks.groupby('trackid').filter(lambda df: df[['longitude', 'latitude']].diff().abs().max(axis=1).max(axis=0) > max_difference_degrees)

    # Make polygons of spurious tracks for visualisation
    spurious_polygons = utils.polygons_from_tracks(tracks, filter_spurious_points=False)
    
    # Make polygons of tracks with zeros for visualisation
    # NB you should ensure filter_zeros is set to False if this becomes a named arg of polygons_from_tracks
    zero_polygons = utils.polygons_from_tracks(zero_tracks, filter_spurious_points=False)

    # Reduce precision of date and also convert to string - this means that dates can no longer be compared
    metadata['valid_start'] = metadata['valid_start'].apply(lambda x: x.date()).astype(str)


    # Add metadata (loctionid, groupid etc)
    spurious_polygons = spurious_polygons.merge(metadata, on='trackid')
    zero_polygons = zero_polygons.merge(metadata, on='trackid')
    less_than_three = less_than_three.merge(metadata, on='trackid')
    

    # Save erroneous tracks to CSV
    spurious_polygons.drop('geometry', axis='columns').to_csv(f"{root_filepath}_spurious_points.csv")
    zero_polygons.drop('geometry', axis='columns').to_csv(f"{root_filepath}_has_zero_point.csv")
    less_than_three.to_csv(f"{root_filepath}_less_than_three_points.csv")

    # Create shapefile of spurious points for visulisation
    utils.gdf_to_shapefile(spurious_polygons, f"{root_filepath}_spurious_points.shp")
    utils.gdf_to_shapefile(zero_polygons, f"{root_filepath}_has_zero_point.shp")












#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# The below pipelines are no longer used

def shapefile_from_queries(metadata_query: str, tracks_query: str, datafetcher: utils.DataFetcher, filepath: str)->None:
    """This is now redundant. Superceded by shapefile_from_clusters which batches the query at the cluster level to reduce memory consumption."""

    """Create a filtered and edited shapefile based on SQL queries which give tracks and metadata
    metadata_query must return a dataframe which has columns 'locationid', 'valid_start'
    tracks_query must return a datafram which has columns 'pointid, trackid, latitude, longitude' """

    # Fetch dataframes from remote
    metadata = utils.metadata_from_SQL(metadata_query, datafetcher)
    polygons = utils.polygons_from_SQL(tracks_query, datafetcher, remove_duplicates=True)

    # Ensure metadata is indexed by locationid
    metadata = metadata.set_index(metadata['locationid'])

    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    polygons = polygons.merge(metadata, on='trackid').set_index(polygons.index)



    # Pre-filter
    # NB simplify treats the coordinates as if they are Cartesian but this is fine because they effectively are 
    # ..at the level of a single farm. Consider the local tangent plane (sin(longitude-offset), sin(latitude-offset))
    polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))
    polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']



    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    intersections = polygons.overlay(polygons)

    # Remove self-comparisons
    intersections = intersections.query("trackid_1 != trackid_2")

    # Remove duplicates that arise from comparing a dataframe with itself
    intersections = intersections.query("trackid_1 < trackid_2")

    # Resolve overlaps
    fix_polygons.resolve_overlaps(intersections, metadata, polygons, dividing_points=[0, 0.3, 0.5, 0.8, 1])


    # Post-filter
    final = polygons.loc[(polygons['geometry'].geom_type == 'Polygon')&(polygons['removed'] == 0)].drop('trackid', axis='columns')


    # Write to file
    utils.gdf_to_shapefile(final, filepath)


def overlaps_from_queries(metadata_query: str, tracks_query: str, datafetcher: utils.DataFetcher, root_filepath: str)->None:
    """Superceded by overlaps_from_clusters
    metadata_query must be an SQL query as a string which returns locationid, trackid, valid_start.
    tracks_query must be an SQL query as a string which returns pointid, trackid, longitude, latitude"""

    directory = os.path.dirname(root_filepath)
    if directory == "":
        root_filepath = "overlaps/"
    utils.validate_filepath(root_filepath)

    # Fetch dataframes from remote
    metadata = utils.metadata_from_SQL(metadata_query, datafetcher)
    polygons = utils.polygons_from_SQL(tracks_query, datafetcher, remove_duplicates=True)


    # Reduce precision of date and also convert to string - this means that dates can no longer be compared
    metadata['valid_start'] = metadata['valid_start'].apply(lambda x: x.date()).astype(str)

    # Ensure metadata is indexed by locationid
    metadata = metadata.set_index(metadata['locationid'])

    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    polygons = polygons.merge(metadata, on='trackid').set_index(polygons.index)


    # Store a copy of the raw tracks for visual inspection
    raw_tracks = polygons['geometry'].copy()

    # Pre-filter
    # NB simplify treats the coordinates as if they are Cartesian but this is fine because they effectively are 
    # ..at the level of a single farm. Consider the local tangent plane (sin(longitude-offset), sin(latitude-offset))
    polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))
    
    # Commented-out to allow non-polygons
    # polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']

    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    intersections = polygons.overlay(polygons)

    # Remove self-comparisons, NB duplicates of form (A, B) ~ (B, A) are left in place
    intersections = intersections.query("trackid_1 != trackid_2")


    # Resolve overlaps
    fix_polygons.label_overlaps(intersections, metadata, polygons)

    # Re-set the geometry to the raw_tracks for visualisation
    polygons['geometry'] = raw_tracks

    # Write CSV
    intersections.loc[intersections['type']==1].drop('geometry', axis='columns').to_csv(f"{root_filepath}_negligible_overlaps.csv")
    intersections.loc[intersections['type']!=1].drop('geometry', axis='columns').to_csv(f"{root_filepath}_significant_overlaps.csv")

    # Write overlaps to shapefiles
    for overlap_type in [1,2,3,4,5,6]:
        utils.gdf_to_shapefile(intersections.loc[intersections['type']==overlap_type], f"{root_filepath}_overlap_type_{overlap_type}.shp")

    # Write polygons involved in overlaps to shapefiles
    polygons.drop('trackid', axis='columns', inplace=True)
    utils.gdf_to_shapefile(polygons.loc[polygons['significant_overlap']==1], f"{root_filepath}_significant_overlap.shp")
    utils.gdf_to_shapefile(polygons.loc[polygons['negligible_overlap']==1], f"{root_filepath}_negligible_overlap.shp")
    utils.gdf_to_shapefile(polygons.loc[polygons['border_overlap']==1], f"{root_filepath}_border_overlap.shp")



def shapefile_from_clusters_chunked(clusterids, metadata_query, f_cluster_query, datafetcher, filepath):
    """This has been superceded by shapefile_from_clusters.
    The idea was to save clusters with simplified polygons into temporary shapefiles.
    To ensure no overlap, all (simplified) clusters will need to be loaded into memory"""

    chunker = chunking.ClusterChunk()
    chunker.fetch_and_store_clusters(clusterids, datafetcher, f_cluster_query, "tmp/")
    polygons = chunker.load_all_clusers()
    polygons.drop_duplicates('trackid', inplace=True)

    # Fetch dataframes from remote
    metadata = utils.metadata_from_SQL(metadata_query, datafetcher)

    # Ensure metadata is indexed by locationid
    metadata = metadata.set_index(metadata['locationid'])

    # Ensure that polygons gains a locationid column and that it is still indexed by trackid
    polygons = polygons.merge(metadata, on='trackid').set_index(polygons['trackid'])
    print(polygons.index)


    polygons = polygons.loc[polygons['geometry'].geom_type == 'Polygon']

    print("intersecting")

    # Create table of pair-wise overlaps to be resolved. The geometry column contains the intersections as Polygon or MultiPolygon 
    intersections = polygons.overlay(polygons)

    # Remove self-comparisons
    intersections = intersections.query("trackid_1 != trackid_2")

    # Remove duplicates that arise from comparing a dataframe with itself
    intersections = intersections.query("trackid_1 < trackid_2")

    print("resolving overlaps")

    # Resolve overlaps
    fix_polygons.resolve_overlaps(intersections, metadata, polygons, dividing_points=[0, 0.3, 0.5, 0.8, 1])

    print("done resolving")

    # Post-filter
    final = polygons.loc[(polygons['geometry'].geom_type == 'Polygon')&(polygons['removed'] == 0)].drop('trackid', axis='columns')

    print("writing to file")

    # Write to file
    utils.gdf_to_shapefile(final, filepath)




    
