from mastodon import Mastodon
import requests, json
from datetime import datetime

DEBUG = False # Set this to True to print the results without posting to Mastodon
MASTODON_API_TOKEN = "XXXXXXXXXXXXXXXXXXXXXX"
DOWNTOWN_SF_WEATHER_STATION_ID = "047772"

# For missing values, we can't leave them as a string (namely "M") so convert them to a dummy numerical value
MISSING_VALUE = 777

#For adding a Leading Zero to a single-digit integer
LZ = lambda x : str(x) if x >= 10 else '0'+str(x)

def ordinalize(x):
    if x >= 10 and x <= 14:
        return str(x)+'th'
    last_digit = x % 10
    if last_digit == 1:
        ordinal = 'st'
    elif last_digit == 2:
        ordinal = 'nd'
    elif last_digit == 3:
        ordinal = 'rd'
    else:
        ordinal = 'th'
    return str(x)+ordinal

def convert_date_string(s): # Convert a YYYY-MM-DD string to a datetime object
    x = [int(y) for y in s.split("-")]
    return datetime(x[0], x[1], x[2])

def record_year(y):
    if isinstance(y, int): # If y is a String (a single year)
        return str(y)
    else: # If y is a List (a daily record has occured in multiple years)
        sortarr = reversed(sorted([x for x in y])) # Most recent years first
        sortarr = [str(x) for x in sortarr]
        return ', '.join(sortarr)

def get_records(d, station_id=DOWNTOWN_SF_WEATHER_STATION_ID): # "d" is a datetime object
    request_params = {"sid":station_id,
                      "sdate":f"1875-{LZ(d.month)}-"+LZ(d.day),
                      "edate":f"2022-{LZ(d.month)}-"+LZ(d.day),
                      "elems":[{"name":"maxt","interval":[1,0,0],"duration":"dly"},
                               {"name":"mint","interval":[1,0,0],"duration":"dly"},
                               {"name":"pcpn","interval":[1,0,0],"duration":"dly"}]
                      }
    r = requests.post("http://data.rcc-acis.org/StnData", json=request_params, headers={'Accept':'application/json'})
    raw_data = json.loads(r.text)["data"]
    data = []
    
    for d in raw_data:
        high_temp = int(d[1]) if d[1] != "M" else MISSING_VALUE
        low_temp = int(d[2]) if d[2] != "M" else MISSING_VALUE

        pcpn = d[3]
        if pcpn == "T": # Convert T (for Trace amounts of rain) to a numerical value
            pcpn = 0.001
        elif pcpn == "M" or pcpn == "S": # Record for Febuary 6th 1982 has precipitation value "S" (??)
            pcpn = MISSING_VALUE
        else:
            pcpn = float(pcpn)
        data.append([convert_date_string(d[0]), high_temp, low_temp, pcpn])
    
    data.sort(key = lambda x: x[1])

    lowest_maxt = [x for x in data[0] if x != MISSING_VALUE]
    lowest_maxt_value = lowest_maxt[1]
    lowest_maxt_year = [x[0].year for x in data if x[1] == lowest_maxt_value]

    highest_maxt = [x for x in data[-1] if x != MISSING_VALUE]
    highest_maxt_value = highest_maxt[1]
    highest_maxt_year = [x[0].year for x in reversed(data) if x[1] == highest_maxt_value]

    output = {"max_temps": {
                    "lowest": {
                        "year": lowest_maxt_year if len(lowest_maxt_year) > 1 else lowest_maxt_year[0],
                        "temp": lowest_maxt_value
                        },
                    "highest": {
                        "year": highest_maxt_year if len(highest_maxt_year) > 1 else highest_maxt_year[0],
                        "temp": highest_maxt_value
                        },
                    }
    }
    
    data.sort(key = lambda x: x[2])
    
    lowest_mint = [x for x in data[0] if x != MISSING_VALUE]
    lowest_mint_value = lowest_mint[2]
    lowest_mint_year = [x[0].year for x in data if int(x[2]) == lowest_mint_value]

    highest_mint = [x for x in data[-1] if x != MISSING_VALUE]
    highest_mint_value = highest_mint[2]
    highest_mint_year = [x[0].year for x in reversed(data) if int(x[2]) == highest_mint_value]
    
    output.update({"min_temps": {
                    "lowest": {
                        "year": lowest_mint_year if len(lowest_mint_year) > 1 else lowest_mint_year[0],
                        "temp": lowest_mint_value
                        },
                    "highest": {
                        "year": highest_mint_year if len(highest_mint_year) > 1 else highest_mint_year[0],
                        "temp": highest_mint_value
                        },
                    }
    })

    #Sort by precipitation
    data.sort(key = lambda x: x[3])
    data = [x for x in data if x[3] != MISSING_VALUE]

    rainiest_day = data[-1]
    output['precipitation'] = {"year": rainiest_day[0].year,
                                "amount": rainiest_day[3]}
    return output

def get_normal_temps(x):
    today = f'{x.year}-{LZ(x.month)}-{LZ(x.day)}'
    params = {"sid":DOWNTOWN_SF_WEATHER_STATION_ID,"date":today,"elems":[{"name":"maxt","normal":"1"},{"name":"mint","normal":"1"}]}
    r = requests.post("http://data.rcc-acis.org/StnData", json=params, headers={'Accept':'application/json'})
    data = json.loads(r.text)
    avg_high = data['data'][0][1]
    avg_low = data['data'][0][2]
    return [avg_high, avg_low]

def main():
    mastodon = Mastodon(
    access_token = MASTODON_API_TOKEN,
    api_base_url = 'https://botsin.space/')

    d = datetime.now()
    records = get_records(d)
    max_temps = records['max_temps']
    min_temps = records['min_temps']

    toot = f"Daily Records for {d.strftime('%B '+ordinalize(d.day))}:\n\nHighs\n"

    norms = get_normal_temps(d)
    avg_high = f" / Normal: {norms[0]}\n\n"
    avg_low = f" / Normal: {norms[1]}\n\n"

    toot += f"{max_temps['highest']['temp']} ({record_year(max_temps['highest']['year'])}) / {max_temps['lowest']['temp']} ({record_year(max_temps['lowest']['year'])})"+avg_high
    toot += f"Lows\n{min_temps['highest']['temp']} ({record_year(min_temps['highest']['year'])}) / "
    toot += f"{min_temps['lowest']['temp']} ({record_year(min_temps['lowest']['year'])})"+avg_low
    toot += f"Most Precipitation\n{records['precipitation']['amount']} inches ({record_year(records['precipitation']['year'])})"
    
    if DEBUG:
        print(toot)
    else:
        mastodon.toot(toot)
        print("Success! Records posted to Mastodon.")

main()
