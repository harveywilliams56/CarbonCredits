active_cluster_query = """select clusterid, areaid, countrycd from tist_data.cluster cluster
                        join tist_data.area using (areaid)
                        where cluster.valid_end is null;"""



# The queries below are functions which return an SQL string given a clusterid. This allows looping over clusters.

def f_metadata_query(clusterid)->str:
    """SQL query for currently valid locations in cluster clusterid"""

    return f"""
    select locationid, trackid, groupid, clusterid, areaid, loc.valid_start from tist_data.cluster cluster
    join tist_data.area area using (areaid)
    join tist_data.cluster2group c2g using(clusterid)
    join tist_data.groups gp using (groupid)
    join tist_data.group2location g2l using (groupid)
    join tist_data.location loc using (locationid)
    join tist_data.location_track_master ltm using (locationid)
    where 
    cluster.valid_end is null and
    area.valid_end is null and
    c2g.valid_end is null and
    gp.date_deregistered is null and
    g2l.valid_end is null and
    loc.valid_end is null and
    loc.valid_start is not null and
    ltm.best = 1 and ltm.valid_end is null
    and cluster.clusterid = {clusterid}
    ;
    """


def f_tracks_query(clusterid)->str: 
    """SQL query for currently valid tracks in cluster clusterid"""

    return f"""
    select pointid, trackid, locationid, latitude, longitude from tist_data.cluster cluster
    join tist_data.area area using (areaid)
    join tist_data.cluster2group c2g using(clusterid)
    join tist_data.groups gp using (groupid)
    join tist_data.group2location g2l using (groupid)
    join tist_data.location loc using (locationid) 
    join tist_data.location_track_master ltm using (locationid)
    join tist_data.location_track_sub lts using (trackid)
    where 
    cluster.valid_end is null and
    area.valid_end is null and
    c2g.valid_end is null and
    gp.date_deregistered is null and
    g2l.valid_end is null and
    loc.valid_end is null and
    loc.valid_start is not null and
    ltm.best = 1 and ltm.valid_end is null
    and cluster.clusterid = {clusterid}
    ;
    """


def f_deregistered_metadata_query(clusterid)->str:
    """SQL query for deregistered metadata in clusterid - make sure to filter by max(linkid) in the code"""


    # Using max(linkid/trackid) is a proxy for the most recent entry.
    # ..which ensures we only get one copy of each location.
    # NB we should also filter by the max(linkid) in c2g
    # ..but there's no point doing that here because we've restricted attention to a cluster
    # flt is a solution to the "greatest-n-per-group" problem
    return f"""
    select locationid, trackid, groupid, clusterid, areaid, c2g.linkid as c2g_linkid, loc.valid_start, loc.valid_end from tist_data.cluster cluster
    join tist_data.cluster2group c2g using(clusterid)
    join tist_data.group2location g2l using (groupid)
    join tist_data.location loc using (locationid)
    join tist_data.location_track_master ltm using (locationid)
    join (select max(g2l.linkid) g2l_linkid, max(ltm.trackid) ltm_trackid from tist_data.cluster cluster
		join tist_data.cluster2group c2g using(clusterid)
		join tist_data.group2location g2l using (groupid)
		join tist_data.location loc using (locationid)
		join tist_data.location_track_master ltm using (locationid)
		where 
		loc.valid_end is not null
        and loc.valid_start is not null
		and ltm.best = 1
		and cluster.clusterid = {clusterid}
		group by locationid) flt on (flt.g2l_linkid=g2l.linkid and flt.ltm_trackid=ltm.trackid)
    ;
	"""

def f_deregistered_tracks_query(clusterid)->str:
    """SQL query for deregistered tracks in clusterid"""


    # Using max(linkid/trackid) is a proxy for the most recent entry
    # ..which ensures we only get one copy of each location.
    # flt solutions to the "greatest-n-per-group" problem
    return f"""
    select pointid, trackid, locationid, latitude, longitude from tist_data.cluster cluster
    join tist_data.cluster2group c2g using(clusterid)
    join tist_data.group2location g2l using (groupid)
    join tist_data.location loc using (locationid) 
    join tist_data.location_track_master ltm using (locationid)
    join tist_data.location_track_sub lts using (trackid)   
    join (select max(g2l.linkid) g2l_linkid, max(ltm.trackid) ltm_trackid from tist_data.cluster cluster
		join tist_data.cluster2group c2g using(clusterid)
		join tist_data.group2location g2l using (groupid)
		join tist_data.location loc using (locationid)
		join tist_data.location_track_master ltm using (locationid)
		where 
		loc.valid_end is not null 
        and loc.valid_start is not null
		and ltm.best = 1
		and cluster.clusterid = {clusterid}
		group by locationid) flt on (flt.g2l_linkid=g2l.linkid and flt.ltm_trackid=ltm.trackid)

    ;
    """


def f_minimal_metadata_query(clusterid)->str:
    """Minimal SQL query for currently valid locations in cluster clusterid.
    This gives sufficient information to resolve overlaps.
    Further metadata is then added later."""

    return f"""
    select locationid, trackid, loc.valid_start from tist_data.cluster cluster
    join tist_data.area area using (areaid)
    join tist_data.cluster2group c2g using(clusterid)
    join tist_data.groups gp using (groupid)
    join tist_data.group2location g2l using (groupid)
    join tist_data.location loc using (locationid)
    join tist_data.location_track_master ltm using (locationid)
    where 
    cluster.valid_end is null and
    area.valid_end is null and
    c2g.valid_end is null and
    gp.date_deregistered is null and
    g2l.valid_end is null and
    loc.valid_end is null and
    loc.valid_start is not null and
    ltm.best = 1 and ltm.valid_end is null
    and cluster.clusterid = {clusterid}
    ;
    """

