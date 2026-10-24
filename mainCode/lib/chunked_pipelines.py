"""This is for running chunked pipelines to further reduce memory.
We assume that there is no overlap between polygons of different countries"""

from TISTpolygons.lib import utils, chunking, fix_polygons, pipelines, queries

import logging
import numpy as np
import geopandas as gpd
import pandas as pd
from pandas import DataFrame
from shapely import geometry
from shapely import Polygon, MultiPolygon
from pyproj import Geod
from array import array
import os

logger = logging.getLogger(__name__)


def gpkg_from_clusterframe(clusterframe: DataFrame, f_metadata_query, f_tracks_query, datafetcher: utils.DataFetcher, folder):
    """READ WARNING BELOW
    This is an attempt at operating in chunks to reduce memory consumption.
    The idea is to first check polygon overlap at the country level,
    then add metadata at the area level.
    WARNING: we can't be 100% sure that locationids aren't duplicated across areas, invalidating this approach.
    It seems like active locationids aren't duplicated so this code is probably ok to use for active polygons."""
    utils.validate_filepath(folder)
    directory = os.path.dirname(folder)

    for countrycd, country_frame in clusterframe.groupby('countrycd'):
        country_clusterids = country_frame['clusterid'].values
        mininmal_filepath=os.path.join(directory, f"{countrycd}_minimal.gpkg")
        minimal_polygons=pipelines.gpkg_from_clusters(country_clusterids, queries.f_minimal_metadata_query, f_tracks_query, datafetcher, mininmal_filepath)
        
        # Country might have no polygons
        if minimal_polygons is None:
            continue

        full_filepath=os.path.join(folder, f"{countrycd}_full.gpkg")
        utils.validate_filepath(full_filepath)

        if os.path.exists(full_filepath):
            os.remove(full_filepath)


        for areaid, area_frame in clusterframe.groupby('areaid'):

            area_clusterids = area_frame['clusterid'].values
            full_metadata = utils.metadata_from_clusters(area_clusterids, f_metadata_query, datafetcher)

            # Area might have no polygons
            if full_metadata is None:
                continue

            if full_metadata.index.name == 'locationid':
                full_metadata.reset_index('locationid', inplace=True)

            if minimal_polygons.index.name != 'trackid':
                minimal_polygons.set_index('trackid', inplace=True)

            

            cols_to_keep = full_metadata.columns.difference(minimal_polygons.columns)

            full_polygons = minimal_polygons.merge(full_metadata[cols_to_keep], left_index=True, right_on='trackid')


            utils.gdf_to_gpkg(full_polygons, full_filepath, mode="a")