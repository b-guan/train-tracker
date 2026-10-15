import zipfile

import pytest

from mta_tracker.stops import StopIndex, build_index

FILES = {
    "stops.txt": """stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station
101,Van Cortlandt Park-242 St,40.889,-73.898,1,
101N,Van Cortlandt Park-242 St,40.889,-73.898,,101
101S,Van Cortlandt Park-242 St,40.889,-73.898,,101
127,Times Sq-42 St,40.755,-73.987,1,
127N,Times Sq-42 St,40.755,-73.987,,127
127S,Times Sq-42 St,40.755,-73.987,,127
A27,42 St-Port Authority Bus Terminal,40.757,-73.989,1,
A27N,42 St-Port Authority Bus Terminal,40.757,-73.989,,A27
A27S,42 St-Port Authority Bus Terminal,40.757,-73.989,,A27
142,South Ferry,40.702,-74.013,1,
142N,South Ferry,40.702,-74.013,,142
142S,South Ferry,40.702,-74.013,,142
121,86 St,40.788,-73.976,1,
121N,86 St,40.788,-73.976,,121
121S,86 St,40.788,-73.976,,121
626,86 St,40.779,-73.955,1,
626N,86 St,40.779,-73.955,,626
626S,86 St,40.779,-73.955,,626
""",
    "routes.txt": """route_id,agency_id,route_short_name,route_long_name,route_type,route_color,route_text_color,route_sort_order
A,MTA NYCT,A,8 Av Express,1,0062CF,FFFFFF,1
1,MTA NYCT,1,Broadway Local,1,D82233,FFFFFF,20
6,MTA NYCT,6,Lexington Local,1,009952,FFFFFF,25
6X,MTA NYCT,6X,Pelham Express,1,009952,FFFFFF,26
GS,MTA NYCT,S,42 St Shuttle,1,7C858C,FFFFFF,17
""",
    "trips.txt": """route_id,trip_id,service_id,trip_headsign,direction_id,shape_id
1,T1,Weekday,South Ferry,1,
A,TA,Weekday,Far Rockaway,1,
6X,T6X,Weekday,Brooklyn Bridge,1,
6,T6,Weekday,Brooklyn Bridge,1,
""",
    "stop_times.txt": """trip_id,stop_id,arrival_time,departure_time,stop_sequence
T1,101S,00:00:00,00:00:00,1
T1,121S,00:10:00,00:10:00,2
T1,127S,00:15:00,00:15:00,3
T1,142S,00:30:00,00:30:00,4
TA,A27S,00:00:00,00:00:00,1
T6X,626S,00:00:00,00:00:00,1
T6,626S,00:00:00,00:00:00,1
""",
    "transfers.txt": """from_stop_id,to_stop_id,transfer_type,min_transfer_time
127,127,2,0
127,A27,2,300
A27,127,2,300
""",
}


@pytest.fixture
def gtfs_zip(tmp_path):
    path = tmp_path / "google_transit.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in FILES.items():
            zf.writestr(name, content)
    return path


@pytest.fixture
def index(gtfs_zip):
    return StopIndex(build_index(gtfs_zip))
