from sqlalchemy import create_engine, URL
import pandas as pd
from pandas import DataFrame
from geopandas import GeoDataFrame
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from array import array
import numpy as np
import time
import logging
import os

import subprocess
from time import sleep

logger = logging.getLogger(__name__)

class SSHTunnel:
    """Class for maintaining an ssh tunnel"""
    def __init__(self, remote_host, remote_port, ssh_file_path, ssh_username, local_host, local_port):
        """Run a port forwarding command. This might not work well on Windows or Mac, in which case you must manually
        run the correct port forwarding command"""
        # NB - I tried using python libraries for this but it turned into a headache. Hence running subrocess.

        # cmd in the form "ssh  -N -i /harvey/home/.ssh/ssh_harveyw -L 3307:localhost:3306 hw562@sherwood.cl.cam.ac.uk"
        
        cmd = ["ssh", "-N",
        "-i", f"{ssh_file_path}",
        "-L", f"{local_port}:{local_host}:{remote_port}",
        f"{ssh_username}@{remote_host}"]
        
        self.tunnel = subprocess.Popen(cmd)

    def __del__(self):
        self.tunnel.terminate()


class DataFetcher:
    """Class for fetching data from MYSQL databse and returning Pandas DataFrames"""

    def __init__(self, local_hostname, local_port, sql_username, sql_password=None) -> None:

        if sql_password is None:
            sql_password = input("sql password: ") # password for the remote database, NOT the same as SSH password

        connection_string = URL.create(
            "mysql+mysqlconnector",
            username=sql_username,
            password=sql_password,
            host=local_hostname,
            port=local_port
            )
        self.engine = create_engine(connection_string)
        self.check_connection()

    def check_connection(self):
        timeout = 10
        test_query = "select * from tist_data.cluster limit 1;"
        test_result = None
        start_time = time.time()
        while True:
            time_elapsed = time.time() - start_time
            if time_elapsed > timeout:
                break
            logger.debug("Attempting to connect to database")
            try:
                with self.engine.connect() as connection:
                    test_result = pd.read_sql_query(test_query, connection)
                break
            except:
                sleep(0.2)

        if not(isinstance(test_result, pd.DataFrame)):
            raise Exception("Can't reach database. Check SSH connection or port numbers.") 

    def SQL_to_dataframe(self, query, dtype=None) -> pd.DataFrame:
        connection = self.engine.connect()
        dataframe = pd.read_sql_query(query, connection, dtype)
        connection.close()
        return dataframe
    
    

class log_time():
    """Helper class to log timings"""
    def __init__(self, logger: logging.Logger, process_name: str) -> None:
        self.logger = logger
        self.start_time = None
        self.process_name = process_name

    def __enter__(self) -> None:
        self.start_time = time.process_time()
        logger.info(f"Starting {self.process_name}")

    def __exit__(self, *args):
        if self.start_time == None:
            return
        
        time_diff = time.process_time() - self.start_time
        logger.info(f"Finshed  {self.process_name} after time: {time_diff}")
    

# The motivation for this is to reduce memory on two counts: grouping tracks into polygons significantly reduces the number of rows.
# .. and pd.read_sql adds overhead before creating a dataframe so manually forcing this to evaluate in chunks is a good idea.
def polygons_from_clusters(clusterids, f_query, datafetcher, agg_func=Polygon,remove_duplicate_tracks = True, filter_spurious_points=True, filter_minimum_points=True, remove_duplicate_points=True, simplify=True, dtype=None)-> GeoDataFrame:
    """Returns a dataframe of polygons, indexed by trackid. 
    Requires the query to be a function taking clusterid and returning the SQL query.
    SQL query must include pointid, trackid, longitude, latitude"""

    num_clusters = len(clusterids)



    # wrapper for polygons_from_SQL
    def polygons_from_SQL_wrapper(index, clusterid) -> gpd.GeoDataFrame:
        """Return the polygons for that clusterid, possibly simplified."""
        logger.info(f"Polygons cluster {index} of {num_clusters}")
        query = f_query(clusterid)
        subset_polygons = polygons_from_SQL(query, datafetcher, agg_func=agg_func, filter_spurious_points=filter_spurious_points, filter_minimum_points=filter_minimum_points, remove_duplicate_points=remove_duplicate_points, dtype=dtype)
        
        # Empty SQL query returned eg when all groups within cluster are deregistered
        if subset_polygons is None:
            return None

        # Simplify the polygons to further reduce memory use
        if simplify == True:
            subset_polygons['geometry'] = simplify_polygons(subset_polygons['geometry'])

        return subset_polygons

    # Looping through clusterids is a memory optimisation
    try:
        polygons = pd.concat([polygons_from_SQL_wrapper(index, clusterid) for index, clusterid in enumerate(clusterids)])
    except ValueError:
        # Happens if all clusters have no polygons
        return None

    # Further filtering actions
    if remove_duplicate_tracks:
        with log_time(logger, "resetting index"):
            polygons.reset_index(inplace=True)

        with log_time(logger, "removing duplicate tracks"):
            polygons.drop_duplicates('trackid', inplace=True)

        polygons.set_index('trackid', inplace=True)

    return polygons


def polygons_from_SQL(query, datafetcher: DataFetcher, agg_func=Polygon, filter_spurious_points=True, filter_minimum_points=True, remove_duplicate_points=True, dtype=None) -> gpd.GeoDataFrame:
    """Create a pandas.DataFrame of polygons from an SQL query. The query must return columns including pointid, trackid, longitude, latitude.
    The returned table uses trackid as the primary key.
    """

    # Make the SQL query
    with log_time(logger, "fetching tracks"):
        tracks = datafetcher.SQL_to_dataframe(query)

    # Check if the SQL query returns an empty table
    # Can happen if you are looping over clusters in an area and one of the clusters has valid_end != null
    if (tracks.empty):
        logging.info("WARNING: EMPTY SQL RETURNED")
        return None
    
    # If the same locationid is referenced multiple times at a higher level in the database,
    # ..you will end up with the same track being duplicated. 
    # That gives you exactly overlapping points and creates comletely invalid polygons.
    # The SQL query ought to be specific enough to not need this filter, but time cost of this step is negligible.
    if remove_duplicate_points:
        with log_time(logger, "removing duplicate points"):
            tracks.drop_duplicates('pointid', inplace=True)

    # Remove tracks with spurious points (points that are greater max_difference_degrees apart from previous points)
    # This step is computaionally intensive and costs as much time as downloading the SQL file.
    # A difference of 0.02 degrees corresponds to ~ 1KM anywhere on the earth
    max_difference_degrees = 0.02
    if filter_spurious_points:
        with log_time(logger, "removing spurious points"):
            tracks = tracks.groupby('trackid').filter(lambda df: df[['longitude', 'latitude']].diff().abs().max(axis=1).max(axis=0) < max_difference_degrees)

    # Remove tracks with fewer than 3 points 
    if filter_minimum_points:
        with log_time(logger, "filtering minumum points"):
            tracks = tracks.groupby('trackid').filter(lambda x: len(x.index) >= 3)

    # Concatinate decimal longitude and latitide columns into a combined Point type column
    with log_time(logger, "concatinating coords to Point"):
        tracks['points'] = gpd.points_from_xy(tracks.longitude, tracks.latitude)


    # Merge the multiple rows of points into polygons per trackid
    # Could use groupby(['trackid', 'locationid']) but this will result in a multi-index
    with log_time(logger, "grouping Points to Polygons"):
        grouped_tracks = tracks.groupby('trackid').agg(
        geometry = pd.NamedAgg(column='points', aggfunc = agg_func)
        )


    gdf = gpd.GeoDataFrame(grouped_tracks, geometry='geometry', crs='EPSG:4326')

    return gdf



def metadata_from_clusters(clusterids, f_query, datafetcher: DataFetcher, remove_duplicates=True, dtype=None) -> DataFrame:
    """Create a table of metadata using a function returning an SQL query given a clusterid (an f_query).
    The query must contain columns inluding locationid, trackid. The returned table uses locationid as the primary key."""

    num_clusters = len(clusterids)

    # wrapper for metadata_from_SQL
    def metadata_from_SQL_wrapper(index, clusterid) -> pd.DataFrame:
        """Return the metadata for that cluster id."""
        logger.info(f"Polygons cluster {index} of {num_clusters}")
        query = f_query(clusterid)
        subset_metadata = metadata_from_SQL(query , datafetcher, remove_duplicates=remove_duplicates, dtype=dtype)        
        
        # Empty SQL query returned eg when all groups within cluster are deregistered
        if subset_metadata is None:
            return None
        
        return subset_metadata
    
    # Looping through clusterids is a memory optimisation
    try:
        locations = pd.concat([metadata_from_SQL_wrapper(index, clusterid) for index, clusterid in enumerate(clusterids)])
    except ValueError:
        # Happens if all clusters have no polygons
        return None


    # Remove duplicate locationids - these occur if locations have moved between groups etc
    if remove_duplicates:
        logger.info("Removing duplicate locationid")
        if locations.index.name == 'locationid':
            locations.reset_index(inplace=True)
        locations.drop_duplicates('locationid', inplace=True)
        
    if locations.index.name != 'locationid':
        locations.set_index('locationid', inplace=True)
    
    return locations



def metadata_from_SQL(query, datafetcher: DataFetcher, remove_duplicates=True, dtype=None) -> pd.DataFrame:
    """Create a table of metadata from an SQL query. The query must return columns including locationid, trackid.
    The returned table uses locationid as the primary key"""

    # Fetch the metadata
    with log_time(logger, "fetching metadata"):
        metadata = datafetcher.SQL_to_dataframe(query, dtype=dtype)

    # Check locationid in columns
    if metadata.index.name == 'locationid':
        metadata.reset_index(inplace=True)

    # Check if the SQL query returns an empty table
    # Can happen if you are looping over clusters in an area and one of the clusters has valid_end != null
    if (metadata.empty):
        logging.warn("WARNING: EMPTY SQL RETURNED")
        return

    # If the same locationid is referenced multiple times at a higher level in the database,
    # ..you will end up with the same location being duplicated.
    # The SQL query ought to be specific enough to not need this filter. But it's a negligible cost to run.
    if remove_duplicates:
        metadata.drop_duplicates('locationid', inplace=True)

    metadata.set_index('locationid', inplace=True)
    return metadata


def simplify_polygons(geometries: gpd.GeoSeries):
    """Removes vertices from polygons if the resulting polygon outline is within a distance 'tolerence' 
    ..of the original everywhere.

    0.00003 degrees is about 3 metres anywhere on earth ie 0.00001 per metre
    """
    
    return geometries.apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))


def gdf_to_shapefile(gdf: gpd.GeoDataFrame, file_path) -> None:
    """Wrtie a GeoDataFrame to a shapefile"""

    #used because you can't write datetime64 into a shape file
    for col in  gdf.select_dtypes(include=['datetime64']).columns.tolist():
        gdf[col] = gdf[col].apply(lambda x: x.date()).astype(str)

    gdf.to_file(file_path, driver="ESRI Shapefile")

def gdf_to_gpkg(gdf: gpd.GeoDataFrame, file_path, mode="w") -> None:
    """Wrtie a GeoDataFrame to a GeoPackage"""
    if mode=="a" and (not os.path.exists(file_path)):
            mode="w"

    # Drop the time and keep date.
    for col in  gdf.select_dtypes(include=['datetime64']).columns.tolist():
        gdf[col] = gdf[col].apply(lambda x: x.date()).astype(str)

    gdf.to_file(file_path, driver="GPKG", mode=mode)



def _polygon_area(lats: array, lons: array):
    """
    Calculates area in m^2 by approximating the surface as locally flat.
    Local radius of earth is calculated based on the WGS84 ellipsoid values.

    Inexplicably this seems to give an area 0.4% larger than QGIS at 37 deg latitude
    """

    if (len(lats) == 0) or (len(lons)==0):
        logger.warning("WARNING: attempted to calculate empty polygon")
        return 0

    lats = np.deg2rad(lats)
    lons = np.deg2rad(lons)

    # WGS84 ellipsoid values in metres
    a = 6378137
    b = 6356752

    # Calculate local radius
    theta = lats[0]
    radius = (a*b)/np.sqrt(a**2 *np.sin(theta)**2 + b**2 * np.cos(theta)**2)

    # Make sure area is closed
    if lats[0]!=lats[-1]:
        lats = np.append(lats, lats[0])
        lons = np.append(lons, lons[0])

    # Project onto local flat plane
    xs = (lats - lats[0]) * radius
    ys = (lons - lons[0]) * radius

    # Calulate area using trapeziums
    return abs(sum([(xs[i+1]-xs[i])*(ys[i+1]+ys[i])/2.0 for i in range(0, len(xs)-1)]))



def polygon_area(geometry):
    """Approximate area of polygon. Not very accurate and only used for checking overlaps"""
    if isinstance(geometry, Polygon):
        return _polygon_area(*geometry.exterior.coords.xy)
    if isinstance(geometry, MultiPolygon):
        return sum([polygon_area(polygon) for polygon in geometry.geoms])
    else:
        logger.warning("WARNING: attempted to calculate area of non-polygon")
        return 0


def validate_filepath(filepath):
    """Check if directory in filepath exists, if not try and construct it."""
    cwd = os.getcwd()
    directory = os.path.dirname(filepath)
    if directory == "":
        return
    if (not os.path.isdir(directory)):
        try:
            os.makedirs(directory)
        except:
            raise Exception(f"ERROR: invalid folder '{directory}'.\n Current working directory: {cwd}")
        
        


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#The below is no longer used


def polygons_from_tracks(tracks: DataFrame, agg_func=Polygon, filter_spurious_points=True, filter_minimum_points=True, remove_duplicates=False) -> gpd.GeoDataFrame:
    """ Deprecated - preferable to use polygons_from_clusters which calls polygons_from_SQL
    Requires tracks dataframe to include columns pointid, trackid, longitude, latitude"""


    # Check if the SQL query returns an empty table
    # Can happen if you are looping over clusters in an area and one of the clusters has valid_end != null
    if (tracks.empty):
        print("WARNING: EMPTY SQL RETURNED")
        return


    
    """If the same locationid is referenced multiple times at a higher level in the database,
    you will end up with the same track being duplicated. That gives you exactly overlapping points
    and creates comletely invalid polygons.

    The SQL query ought to be specific enough to not need this filter."""
    if remove_duplicates == True:
        tracks.drop_duplicates('pointid', inplace=True)


    # Remove tracks with spurious points (points that are greater max_difference_degrees apart from previous points)
    # Note that this becomes questionable as we head away from the equator
    max_difference_degrees = 0.02
    if filter_spurious_points:
        tracks = tracks.groupby('trackid').filter(lambda df: df[['longitude', 'latitude']].diff().abs().max(axis=1).max(axis=0) < max_difference_degrees)


    #Really we should report information about any tracks with fewer than 3 points
    if filter_minimum_points:
        tracks = tracks.groupby('trackid').filter(lambda x: len(x.index) >= 3)

    # Concatinate decimal longitude and latitide columns into a combined Point type column
    tracks['points'] = gpd.points_from_xy(tracks.longitude, tracks.latitude)

    #Minimum number of tracks to make a valid polygon is 3


    # Merge the multiple rows of points into polygons per trackid
    # Could use groupby(['trackid', 'locationid']) but this will result in a multi-index
    grouped_tracks = tracks.groupby('trackid').agg(
    geometry = pd.NamedAgg(column='points', aggfunc = agg_func)
    )

    gdf = gpd.GeoDataFrame(grouped_tracks, geometry='geometry', crs='EPSG:4326')
    # gdf.set_crs(epsg=4326)

    return gdf