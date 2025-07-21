#!/bin/bash

#############################################################
##  THIS IS AN EMERGENCY VERSION IN BASH IF THE PYHTON
##  SCRIPT FAIL IN TASK
#############################################################

cd data/gfs
dt=`date -u +%Y%m%d`
HI=`date -u +%H`
hh=`expr ${HI} - 4`
if [ ${1} -ge 0 ]; then 
	dt=`echo $1 | cut -c1-8`
	hh=`echo $1 | cut -c9-10`
fi

#if [ $hh -lt 10 ] ; then hh="0${hh}" ; fi
echo $hh


mkdir -p $dt ; cd ${dt}
for i in `seq -w 000 3 174`; do 
    #~ wget -c https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.${dt}/${hh}/atmos/gfs.t${hh}z.pgrb2.0p25.f${i} 
    wget "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=/gfs.${dt}/${hh}/atmos&file=gfs.t${hh}z.pgrb2.0p25.f${i}&all_var=on&all_lev=on&subregion=&toplat=16&leftlon=103&rightlon=113&bottomlat=6" -O svgfs.t${hh}z.pgrb2.0p25.f$i
done