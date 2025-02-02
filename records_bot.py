from mastodon import Mastodon
import requests, json
from datetime import datetime

DEBUG = False # Set this to True to print the results without posting to Mastodon
MASTODON_HOST_INSTANCE = "https://botsin.space/" # This was the host instance I was using but as of December 2024 it has gone into read-only mode
MASTODON_API_TOKEN = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
DOWNTOWN_SF_WEATHER_STATION_ID = "047772" # This value has to be a string since it has a leading zero
ACIS_URL = "http://data.rcc-acis.org/StnData"

# For missing values, we can't leave them as a string (namely "M") so convert them to a dummy numerical value
# Must be a number that won't occur naturally in any temperature records
MISSING_VALUE = 777

# For adding a Leading Zero to a single-digit integer
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

#Returns a string, e.g. "1887" or "1901, 1925, 1982"
def display_record_years(y):
    if isinstance(y, int): # If y is an Integer (a single year)
        return str(y)
    
    else: # If y is a List (i.e. a daily record has occured in multiple years)
        sortarr = reversed(sorted(y)) # Most recent years first
        sortarr = [str(x) for x in sortarr]
        return ', '.join(sortarr)

def get_records(station_id, month, day, starting_year, ending_year): # "d" is a datetime object
    IS_LEAP_DAY  = (month == 2 and day == 29)
    starting_year = 1876 if IS_LEAP_DAY else starting_year
    ending_year = 2020 if IS_LEAP_DAY else ending_year
    request_params = {"sid":station_id,
                      "sdate":f"{starting_year}-{LZ(month)}-"+LZ(day),
                      "edate":f"{ending_year}-{LZ(month)}-"+LZ(day),
                      "elems":[{"name":"maxt","interval":[1,0,0],"duration":"dly"},
                               {"name":"mint","interval":[1,0,0],"duration":"dly"},
                               {"name":"pcpn","interval":[1,0,0],"duration":"dly"}]
                      }
    
    r = requests.post(ACIS_URL, json=request_params, headers={'Accept':'application/json'})
    raw_data = json.loads(r.text)["data"]
    data = []

    for d in raw_data:

        year = int(d[0][:4]) #The first four digits of the YYYY-MM-DD string
        current_day = int(d[0][-2:])

        # ACIS will return a mixture of values for both February 28th AND 29th if we ask for just the Feb 29th values
        # Therefore if we see a February 28th value and today is Leap Day, skip it
        if IS_LEAP_DAY and current_day == 28:
            continue
        
        high_temp = int(d[1]) if d[1] != "M" else MISSING_VALUE
        low_temp = int(d[2]) if d[2] != "M" else MISSING_VALUE
        pcpn = d[3]
        # Code below for edge case of November 10 1975 in SF (047772) records
        # Precipitation value for that day was recorded as "0.12A"
        # I assume the "A" is a typo
        pcpn = pcpn.replace("A", "")

        if pcpn == "T": # Convert T (for Trace amounts of rain) to a numerical value
            pcpn = 0.001
        elif pcpn == "M" or pcpn == "S": # Record for Febuary 6th 1982 has precipitation value "S" (??)
            pcpn = MISSING_VALUE
        else:
            pcpn = float(pcpn)

        data.append([year, high_temp, low_temp, pcpn])
    
    #Sort by high temperatures
    data.sort(key = lambda x: x[1])

    lowest_maxt = [x for x in data[0] if x != MISSING_VALUE]
    lowest_maxt_value = lowest_maxt[1]
    lowest_maxt_year = [x[0] for x in data if x[1] == lowest_maxt_value]
    data = [x for x in data if MISSING_VALUE not in x]

    highest_maxt = [x for x in data[-1] if x != MISSING_VALUE]
    highest_maxt_value = highest_maxt[1]
    highest_maxt_year = [x[0] for x in reversed(data) if x[1] == highest_maxt_value]

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
    
    #Now sort by low temperatures
    data.sort(key = lambda x: x[2])
    
    lowest_mint = [x for x in data[0] if x != MISSING_VALUE]
    lowest_mint_value = lowest_mint[2]
    lowest_mint_year = [x[0] for x in data if int(x[2]) == lowest_mint_value]

    highest_mint = [x for x in data[-1] if x != MISSING_VALUE]
    highest_mint_value = highest_mint[2]
    highest_mint_year = [x[0] for x in reversed(data) if int(x[2]) == highest_mint_value]
    
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

    #Finally, sort by precipitation
    data.sort(key = lambda x: x[3])
    
    data = [x for x in data if x[3] != MISSING_VALUE]
    rainiest_day = data[-1]
    output['precipitation'] = {"year": rainiest_day[0],
                                "amount": rainiest_day[3]}
    return output

#Returns a List with two elements, the average High and average Low temperatures for the given date
def get_normal_temps(x, sid):
    today = f'{x.year}-{LZ(x.month)}-{LZ(x.day)}'
    params = {"sid":sid,"date":today,"elems":[{"name":"maxt","normal":"1"},{"name":"mint","normal":"1"}]}
    r = requests.post(ACIS_URL, json=params, headers={'Accept':'application/json'})
    data = json.loads(r.text)
    avg_high = data['data'][0][1]
    avg_low = data['data'][0][2]
    
    return [avg_high, avg_low]

def main():
    mastodon = Mastodon(access_token = MASTODON_API_TOKEN, api_base_url = MASTODON_HOST_INSTANCE)

    d = datetime.now()
    records = get_records(DOWNTOWN_SF_WEATHER_STATION_ID, d.month, d.day, 1875, d.year-1) #Assumes weather records will have been updated within one (1) year
    max_temps = records['max_temps']
    min_temps = records['min_temps']
    monthly_record_highs = [79,81,87,94,97,103,99,98,106,102,86,76]
    monthly_record_lows = [29,31,33,40,42,46,47,46,47,43,38,27,27]

    toot = f"Daily Records for {d.strftime('%B '+ordinalize(d.day))}:\n\n"

    norms = get_normal_temps(d, DOWNTOWN_SF_WEATHER_STATION_ID)
    avg_high = f" / Normal: {norms[0]}\n\n"
    avg_low = f" / Normal: {norms[1]}\n\n"
    is_monthly_record_high = (monthly_record_highs[d.month-1] == max_temps['highest']['temp'])
    is_monthly_record_low = (monthly_record_lows[d.month-1] == min_temps['lowest']['temp'])
    asterisk_h = "*" if is_monthly_record_high else ""
    asterisk_l = "*" if is_monthly_record_low else ""
    toot += f"Highs\n{max_temps['highest']['temp']}{asterisk_h} ({display_record_years(max_temps['highest']['year'])}) / {max_temps['lowest']['temp']} ({display_record_years(max_temps['lowest']['year'])})"+avg_high
    toot += f"Lows\n{min_temps['highest']['temp']} ({display_record_years(min_temps['highest']['year'])}) / "
    toot += f"{min_temps['lowest']['temp']}{asterisk_l} ({display_record_years(min_temps['lowest']['year'])})"+avg_low
    toot += f"Most Precipitation\n{records['precipitation']['amount']} inches ({display_record_years(records['precipitation']['year'])})"
    if (is_monthly_record_low or is_monthly_record_high):
        toot += "\n\n*Monthly record"
    if DEBUG:
        print(toot)
    else:
        mastodon.toot(toot)
        print("Success! Records posted to Mastodon.")

main()
