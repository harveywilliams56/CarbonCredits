import pandas as pd
import geopandas as gpd
from mainCode.lib import utils, pipelines, fix_polygons, queries
import config

import sys
import logging


# from TIST_polygons.src import utils



local_host = config.local_host
sql_username = config.sql_username
remote_port = config.remote_port
remote_host = config.remote_host
ssh_user = config.ssh_user
ssh_pkey = config.ssh_pkey
local_port = config.local_port




if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(0)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)


    # If not running on Sherwood, open SSH_tunnel
    if config.running_local:
        tunnel = utils.SSHTunnel(remote_host, remote_port, ssh_pkey, ssh_user, local_host, local_port)

    datafetcher = utils.DataFetcher(local_host, local_port, sql_username)



    cluster_frame = datafetcher.SQL_to_dataframe("select * from tist_data.cluster;")



    clusterids = cluster_frame['clusterid'].values


    # These are SQL queries dressed up as functions ie f_queries which accept a clusterid
    f_metadata_query = queries.f_metadata_query
    f_tracks_query = queries.f_tracks_query

    # This is where the bulk of the processing happens:w




# A small edit should ideally be made to dereg_gpkg_from_clusters - please see the file for this suggestion
pipelines.dereg_gpkg_from_clusters(clusterids, queries.f_deregistered_metadata_query, queries.f_deregistered_tracks_query, datafetcher, "shapefiles/dereg_pipeline/all_dereg_download.gpkg",
                                   f_active_metadata_query=queries.f_metadata_query, f_active_tracks_query=queries.f_tracks_query)







