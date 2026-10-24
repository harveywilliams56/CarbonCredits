from TISTpolygons.lib import utils
import geopandas as gpd
import pandas as pd


def fetch_and_store_cluster(clusterid, datafetcher, tracks_query, metadata_query)->None:
    """Get all polygons in the cluster from the remote database and store simplified versions in a temp file."""
    polygons = utils.polygons_from_SQL(tracks_query, datafetcher)
    if polygons is None:
        return
    polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))
    utils.gdf_to_shapefile(polygons, f"cluster_{clusterid}_tmp.shp")



class ClusterChunk():
    """This class is for saving a set of clusters as simplified polygons, which can later be reloaded into one GeoDataFrame.
    This is to avoid the memory cost of handling all the raw polygons at the same time."""
    def __init__(self) -> None:
        self.filenames=[]

    def fetch_and_store_clusters(self, clusterids, datafetcher, f_tracks_query, root_filepath):
        num = len(clusterids)
        i = 1
        for clusterid in clusterids:
            tracks_query = f_tracks_query(clusterid)
            self._fetch_and_store_cluster(clusterid, datafetcher, tracks_query, root_filepath)
            print(f"{i} of {num} clusters saved")
            i += 1



    def _fetch_and_store_cluster(self, clusterid, datafetcher, tracks_query, root_filepath="")->None:
        """Get all polygons in the cluster from the remote database and store simplified versions in a temp file."""
        polygons = utils.polygons_from_SQL(tracks_query, datafetcher)
        if polygons is None:
            return
        polygons['geometry'] = polygons['geometry'].apply(lambda x: x.simplify(tolerance = 0.00003, preserve_topology = False))

        filename = f"{root_filepath}cluster_{clusterid}_tmp.shp"
        self.filenames += [filename]
        utils.gdf_to_shapefile(polygons, filename)

    def load_all_clusers(self)->gpd.GeoDataFrame | None:
        """load the stored simplified clusters into one dataframe"""
        if self.filenames == []:
            return 
        
        gdf = gpd.GeoDataFrame(pd.concat([gpd.read_file(filename) for filename in self.filenames]))
        return gdf

