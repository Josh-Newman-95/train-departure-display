import requests

def loadDeparturesForStation(apiKey):

    station_id = ['940GZZLUCPN', '37', '35']
    station_name = ['Clapham North',  'Bedford Road', 'Bedford Road']
    station_line = ['northern', '37', '35']
    line_direction = ['outbound', 'inbound', 'inbound']

    output = {}

    for station, name, line, direction in zip(station_id, station_name, station_line, line_direction):

        if station == '37' or station == '35':
            url = f'https://api.tfl.gov.uk/Line/{line}/Arrivals/'
        else:    
            url = f'https://api.tfl.gov.uk/Line/{line}/Arrivals/{station}?direction={direction}'

        print(url)
        headers = {
            'Cache-Control':'no-cache',
            'app_key': apiKey
        }
        tfl_request = requests.get(url, headers=headers)

        if tfl_request.status_code == 200:
            tfl_response_precursor = tfl_request.json()

            tfl_response = []
            if station == '37' or station == '35':
                for x in tfl_response_precursor:

                    if x['stationName'] == name and x['direction'] == direction:
                        tfl_response.append(x)
            else:
                tfl_response = tfl_response_precursor

            station_data = []
            for x in tfl_response:
                time_to_arrival = x.get('timeToStation', 0)
                minutes_to_arrival = round(time_to_arrival / 60, 0) if time_to_arrival >= 0 else 'N/A'

                if minutes_to_arrival == 0:
                    minutes_to_arrival = 'Due'

                data = {
                    'route': x.get('towards', '') if name == 'Clapham North' else f'{station}  Clapham Junction',
                    'minutes': minutes_to_arrival
                }
                station_data.append(data)

            # Sort the station data by minutes, ignoring entries with 'N/A' for minutes
            if name in output:
                output[name].extend(station_data)
                output[name] = sorted(
                    output[name],
                    key=lambda d: (0 if d['minutes'] == 'Due' else 
                                d['minutes'] if isinstance(d['minutes'], (int, float)) 
                                else float('inf'))
                )
            else:
                output[name] = sorted(
                    station_data,
                    key=lambda d: (0 if d['minutes'] == 'Due' else 
                                d['minutes'] if isinstance(d['minutes'], (int, float)) 
                                else float('inf'))
                )
        else:
            print(f"Error: Received status code {tfl_request.status_code} for station {station}")

    return output
