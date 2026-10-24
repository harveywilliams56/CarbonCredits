# OBTAINING LEGACY BIOMASS ESTIMATES BY FARM

# This R code connects to the SQL database and pulls all tree data and biomass estimates over time for each farm
# Result is a csv file per cluster


# import relevant libraries
library(RMySQL)
library(BIOMASS)
library(data.table)
library(tidyr)


# set up connection to SQL server

# need port forwarding
conn <- dbConnect(RMySQL::MySQL(), 
                  host='127.0.0.1',
                  port=3307,
                  user='tist',
                  # need package rstudioapi
                  password = rstudioapi::askForPassword("Database password"))



# SQL query for valid clusterids

cluster_query <- "select distinct(clusterid)
from tist_data.cluster c
join tist_data.cluster2group c2g using (clusterid)
join tist_data.group2location g2l using (groupid)
join tist_data.location loc using(locationid)
where c.valid_end is null and
c2g.valid_end is null and
g2l.valid_end is null and
loc.valid_end is null"



# functions that return SQL queries for tree data per cluster and relevant coordinate data (used for calculating AGB from BIOMASS)

get_trees <- function(clusterid) {
  
  # all survey data
  
  tree_query <- sprintf("select locationid, loc_name, year(loc.valid_start) as loc_start, countrycd, treeid, genus, species, tc.age, tc.treecount, avg(tcirc.circ) as avgCirc, date(tm.valid_start) as survey_date
from tist_data.area a
join tist_data.cluster c using(areaid)
join tist_data.cluster2group c2g using (clusterid)
join tist_data.group2location g2l using (groupid)
join tist_data.location loc using(locationid)
join tist_data.location_name ln using(locationid)
join tist_data.location_track_master ltm using (locationid)
join tist_data.location_tree_master tm using (locationid)
join tist_data.location_tree_count tc using (treeid)
join tist_data.location_tree_circ tcirc using (treeid)
join tist_data.species s on s.cnameid = tc.cnameid
join tist_data.species_scientific sci using (scientificid)
where
ltm.best = 1 and ltm.valid_end is null and
a.valid_end is null and
c.valid_end is null and
c2g.valid_end is null and
g2l.valid_end is null and
loc.valid_end is null
and s.valid_end is null
and sci.valid_end is null
and clusterid = %d
group by locationid, loc_name, countrycd, treeid, tc.cnameid, tc.age, survey_date
;", clusterid)
  
  return(tree_query)
}


get_coordinates <- function(clusterid) {
  
  
  coordinate_query <- sprintf("select locationid, longitude, latitude 
from tist_data.area a
join tist_data.cluster c using(areaid)
join tist_data.cluster2group c2g using (clusterid)
join tist_data.group2location g2l using (groupid)
join tist_data.location loc using (locationid)
join tist_data.location_track_master ltm using (locationid)
join (select trackid, min(pointid) as pointid from tist_data.location_track_sub group by trackid) pts using (trackid)
join tist_data.location_track_sub lts on lts.pointid = pts.pointid
where
a.valid_end is null and
c.valid_end is null and
c2g.valid_end is null and
g2l.valid_end is null and
loc.valid_end is null and
ltm.best = 1 and ltm.valid_end is null
and clusterid = %d
;", clusterid)
  
  return(coordinate_query)
}



# create dataframe from cluster query
result.cluster <- dbGetQuery(conn, cluster_query)


# create null empty vector for clusterids with no data
empty <- c()



# loop through valid clusterids
for (i in 1:nrow(result.cluster)) {
  
  result.trees <- dbGetQuery(conn, get_trees(clusterid = result.cluster[i,]))
  result.coordinates <- dbGetQuery(conn, get_coordinates(clusterid = result.cluster[i,]))
  
  cluster_df <- merge(result.trees, result.coordinates, by='locationid')
  
  
  if (nrow(cluster_df)>0) {
    # get wood density and add to df
    densities <- getWoodDensity(cluster_df$genus, cluster_df$species)
    withDensity <- cbind(cluster_df, densities[c('meanWD', 'sdWD')])
    
    
    # calculates AGB and uses Monte Carlo method of error propagation
    # NB use Carbon=TRUE for AGC
    output = AGBmonteCarlo((withDensity$avgCirc)/pi, WD=withDensity$meanWD, errWD=withDensity$sdWD, coord=withDensity[c('longitude', 'latitude')], Dpropag=withDensity$stdCirc, n=50, Carbon=FALSE)
    AGB <- output$AGB_simu
    
    
    # take matrix and return AGB data
    withDensity$meanAGB <- apply(AGB, 1, mean)
    withDensity$sdAGB <- apply(AGB, 1, sd)
    # multiply up by tree count
    withDensity$AGB <- with(withDensity, meanAGB * treecount)
    withDensity$errAGB <- with(withDensity, sdAGB * treecount)
    
    
    # create data table
    df.alltrees <- data.table(withDensity)
    # sum AGB per survey
    summedAGB <- df.alltrees[, list(totalAGB = sum(AGB)), by = .(locationid, loc_name, loc_start, survey_date)]


    # create counter key
    summedAGB$counter <- with(summedAGB, ave(locationid, locationid, with(rle(locationid), rep(seq_along(values), lengths)), FUN = seq_along))

    # convert to one row per farm
    farmAGB <- pivot_wider(summedAGB, id_cols = c(locationid, loc_name, loc_start), names_from = counter, values_from = c(survey_date, totalAGB), names_vary = "slowest", values_fill = NULL)

    # save to csv using filepath
    filepath = "/Users/hamdah/tist/legacy_AGB"
    write.csv(farmAGB,file= sprintf("%s/cluster%d_legacyAGB", filepath, result.cluster[i,]), row.names = FALSE, col.names = TRUE)
  
    
    # clear dataframe
    rm(result.trees, result.coordinates)
  }
  
  # collate clusterids with no tree data
  else empty <- append(empty, result.cluster[i,])
  
}

print(empty)

    
