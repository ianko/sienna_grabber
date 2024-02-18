"""Get a list of Toyota vehicles from the Toyota website."""
import os
import sys
import uuid
from functools import cache
from secrets import randbelow
from time import sleep
from timeit import default_timer as timer

import pandas as pd
import requests
import warnings

from sienna_grabber import config, wafbypass

# Get the model that we should be searching for.
MODEL = os.environ.get("MODEL")

# Get the zipcode and distance to search.
ZIPCODE = os.environ.get("ZIPCODE")
DISTANCE = os.environ.get("DISTANCE")

@cache
def get_vehicles_query():
    """Read vehicles query from a file."""
    with open(f"{config.BASE_DIRECTORY}/graphql/vehicles.graphql", "r") as fileh:
        query = fileh.read()

    # Replace certain place holders in the query with values.
    query = query.replace("ZIPCODE", ZIPCODE)
    query = query.replace("MODELCODE", MODEL)
    query = query.replace("DISTANCEMILES", DISTANCE)
    query = query.replace("LEADIDUUID", str(uuid.uuid4()))

    return query


def read_local_data():
    """Read local raw data from the disk instead of querying Toyota."""
    return pd.read_json(f"output/{MODEL}_raw.json")

def upload_output():
    sync_data_to_api(read_local_data())


def query_toyota(page_number, query, headers):
    """Query Toyota for a list of vehicles."""

    # Replace the page number in the query
    query = query.replace("PAGENUMBER", str(page_number))

    # Make request.
    json_post = {"query": query}
    url = "https://api.search-inventory.toyota.com/graphql"
    resp = requests.post(
        url,
        json=json_post,
        headers=headers,
        timeout=15,
    )

    try:
        result = resp.json()["data"]["locateVehiclesByZip"]
    except Exception as e:
        print(resp.headers)
        print(resp.text)
        return None

    if not result or "vehicleSummary" not in result:
        print(resp.text)
        return None
    else:
        return result


def get_all_pages():
    """Get all pages of results for a query to Toyota."""
    df = pd.DataFrame()
    page_number = 1

    # Read the query.
    query = get_vehicles_query()

    # Get headers by bypassing the WAF.
    print("Bypassing WAF")
    headers = wafbypass.WAFBypass().run()

    # Start a timer.
    timer_start = timer()

    # Set a last run counter.
    last_run_counter = 0

    while True:
        # Toyota's API won't return any vehicles past past 40.
        if page_number > 40:
            break

        # The WAF bypass expires every 5 minutes, so we refresh about every 4 minutes.
        elapsed_time = timer() - timer_start
        if elapsed_time > 4 * 60:
            print("  >>> Refreshing WAF bypass >>>\n")
            headers = wafbypass.WAFBypass().run()
            timer_start = timer()

        # Get a page of vehicles.
        print(f"Getting page {page_number} of {MODEL} vehicles")

        result = query_toyota(page_number, query, headers)
        if result and "vehicleSummary" in result:
            with warnings.catch_warnings():
                # TODO: pandas 2.1.0 has a FutureWarning for concatenating DataFrames with Null entries
                warnings.filterwarnings("ignore", category=FutureWarning)
                df = pd.concat([df, pd.json_normalize(result["vehicleSummary"])])

        # Drop any duplicate VINs.
        df.drop_duplicates(subset=["vin"], inplace=True)

        print(f"Found {len(df)} (+{len(df)-last_run_counter}) vehicles so far.\n")

        # If we didn't find more cars from the previous run, we've found them all.
        if len(df) == last_run_counter:
            print("All vehicles found.")
            break

        last_run_counter = len(df)
        page_number += 1

        sleep(10)
        continue

    return df


def update_vehicles():
    """Generate a curated database of vehicles."""
    if not MODEL:
        sys.exit("Set the MODEL environment variable first")
    
    if not ZIPCODE:
        sys.exit("Set the ZIPCODE environment variable first")

    if not DISTANCE:
        sys.exit("Set the DISTANCE environment variable first")

    df = get_all_pages()

    # Stop here if there are no vehicles to list.
    if df.empty:
        print(f"No vehicles found for model: {MODEL}")
        return

    # Write the raw data to a file.
    # sync_data_to_api(df)
    to_json_raw(df)
    to_csv_simple(df)

def sync_data_to_api(df):
    json_data = df.to_json(orient="records", date_format="iso", date_unit="s")

    # Set the headers for the POST request
    headers = {'Content-Type': 'application/json'}

    # Send the POST request to the remote URL
    response = requests.post("http://localhost:4000/gha/sync", 
        data=json_data, 
        headers=headers, 
        timeout=15
    )

    # Check the response status code
    if response.status_code == 200:
        print('DataFrame sent successfully!')
    else:
        print('Error sending DataFrame:', response.content)

def to_json_raw(df):
    df.to_json(f"output/{MODEL}_raw.json", orient="records", date_format="iso", date_unit="s")

def to_csv_simple(df):
    renames = {
        "eta.currToDate": "ETA",
        "vin": "VIN",
        "year": "Year",
        "model.marketingName": "Model",
        "holdStatus": "Hold Status",
        "isPreSold": "Pre-Sold",
        "dealerCategory": "Shipping Status",
        "price.totalMsrp": "Total MSRP",
        "extColor.marketingName": "Exterior Color",
        "intColor.marketingName": "Interior Color",
        "distance": "Distance",
        "dealerMarketingName": "Dealer",
        "dealerWebsite": "Dealer Website",
        "isSmartPath": "SmartPath",
        "options": "Options",
    }

    df = (
        df[
            [
                "eta.currToDate",
                "vin",
                "year",
                "model.marketingName",
                "holdStatus",
                "isPreSold",
                "dealerCategory",
                "price.totalMsrp",
                "extColor.marketingName",
                "intColor.marketingName",
                "distance",
                "dealerMarketingName",
                "dealerWebsite",
                "isSmartPath",
                "options",
            ]
        ]
        .copy(deep=True)
        .rename(columns=renames)
    )

    statuses = {None: False, 1: True, 0: False}
    df.replace({"Pre-Sold": statuses}, inplace=True)

    statuses = {
        "A": "Factory to port",
        "F": "Port to dealer",
        "G": "At dealer",
    }
    df.replace({"Shipping Status": statuses}, inplace=True)

    # when ETA is null, set as unknown, otherwise format as date
    if df["ETA"].isnull().any():
        df["ETA"].fillna("Unknown", inplace=True)
    else:
        df["ETA"] = df["ETA"].apply(lambda dt: dt.split("T")[0])

    df["Options"] = df["Options"].apply(format_options)

    df = df[
        [
            "ETA",
            "VIN",
            "Year",
            "Model",
            "Hold Status",
            "Pre-Sold",
            "Shipping Status",
            "Total MSRP",
            "Exterior Color",
            "Interior Color",
            "Distance",
            "Dealer",
            "Dealer Website",
            "SmartPath",
            "Options",
        ]
    ]

    # Write the data to a file.
    df.sort_values(by=["VIN"], inplace=True)
    df.to_csv(f"output/{MODEL}.csv", index=False)

def format_options(options_raw):
    """extracts `marketingName` from `Options` col"""
    options = set()
    for item in options_raw:
        if item.get("marketingName"):
            options.add(item.get("marketingName"))
        elif item.get("marketingLongName"):
            options.add(item.get("marketingLongName"))
        else:
            continue

    return " | ".join(sorted(options))