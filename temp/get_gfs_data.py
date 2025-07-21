import os, argparse, pandas

GFS_DIR = '/home/forecasting/WRF_operative/GFS/'

def find_station(prefix):
    df = pandas.read_csv('gfs_loc.csv')
    lat = df[df['short'] == prefix]['latitude']
    lon = df[df['short'] == prefix]['longitude']
    lan,las = float(lat.iloc[0])+5, float(lat.iloc[0])-5
    loe,low = float(lon.iloc[0])+5, float(lon.iloc[0])-5
    return lan,low,loe,las

def main(date, prefix):
    os.chdir(GFS_DIR)
    lan,low,loe,las=find_station(prefix)
    dt = date[0:8]
    hh = date[8:10]
    #if prefix=='bou' or prefix=='laa' or prefix=='qua':
    # 	hh = 18
    #elif prefix=='shu' or prefix=='ben' or prefix=='vin':
    #	hh = 12	
    lan,low,loe,las,dt,hh=str(lan),str(low),str(loe),str(las),str(dt),str(hh)
    DWN_DIR = GFS_DIR + 'gfs/' + dt
    os.makedirs(DWN_DIR, exist_ok=True)
    cmd='for i in `seq -w 000 3 174`; do wget "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=/' +\
        'gfs.'+dt+'/'+hh+'/atmos&file=gfs.t'+hh+'z.pgrb2.0p25.f${i}&all_var=on&all_lev=on&' +\
        'subregion=&toplat='+lan+'&leftlon='+low+'&rightlon='+loe+'&bottomlat='+las+'" -O '+\
        DWN_DIR + '/' + prefix + 'gfs.t'+hh+'z.pgrb2.0p25.f$i ; done'
    os.system(cmd)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PV_Low_Irradiance_Losses')
    parser.add_argument('-d', '--date', type=str, required=True, help='Fecha a descargar')
    parser.add_argument('-s', '--prefix', type=str, required=True, help='Prefijo de la planta')
    args = parser.parse_args()
    main(args.date, args.prefix)

exit()