import pandas as pd
from rapidfuzz import process, fuzz


# ============================================================
# FILES
# ============================================================

LOCATION_FILE = "location_master.csv"
MASTER_FILE = "master_priority.csv"

LOCATION_OUTPUT = "location_master_updated.csv"
MASTER_OUTPUT = "master_priority_updated.csv"


# ============================================================
# READ
# ============================================================

print("Reading files...")

location_df = pd.read_csv(
    LOCATION_FILE,
    low_memory=False
)

master_df = pd.read_csv(
    MASTER_FILE,
    low_memory=False
)

print("Location Master :", len(location_df))
print("Master Priority :", len(master_df))


# ============================================================
# NORMALIZE
# ============================================================

def normalize(value):

    if pd.isna(value):
        return ""

    text = str(value).strip().casefold()

    replacements = {
        "banglore": "bangalore",
        "bengaluru": "bangalore",
        "bombay": "mumbai",
        "calcutta": "kolkata",
        "madras": "chennai"
    }

    return replacements.get(text, text)


# ============================================================
# CHECK COLUMNS
# ============================================================

required_location = [
    "id",
    "parent_id",
    "location_level",
    "location_type",
    "name"
]

for col in required_location:

    if col not in location_df.columns:
        raise ValueError(
            f"location_master.csv mein '{col}' nahi hai."
        )


if "city" not in master_df.columns:
    raise ValueError(
        "master_priority.csv mein 'city' column nahi hai."
    )


# ============================================================
# LOCATION LEVELS
# ============================================================

COUNTRY = 1
STATE = 2
CITY = 3


# ============================================================
# CLEAN LOCATION DATA
# ============================================================

location_df["_name_clean"] = (
    location_df["name"].apply(normalize)
)


states = location_df[
    location_df["location_level"] == STATE
].copy()

cities = location_df[
    location_df["location_level"] == CITY
].copy()


print("\nLocation levels:")
print(
    "Countries :",
    len(
        location_df[
            location_df["location_level"] == COUNTRY
        ]
    )
)

print("States    :", len(states))
print("Cities    :", len(cities))


# ============================================================
# STATE LOOKUP
#
# state name -> state id
# ============================================================

state_lookup = {}

for _, row in states.iterrows():

    state_name = normalize(row["name"])

    if not state_name:
        continue

    state_lookup.setdefault(
        state_name,
        []
    ).append(row["id"])


# ============================================================
# CITY LOOKUP
#
# city name + parent state id -> city id
# ============================================================

city_state_lookup = {}

for _, row in cities.iterrows():

    city_name = normalize(row["name"])

    if not city_name:
        continue

    key = (
        city_name,
        str(row["parent_id"])
    )

    # Keep first existing location only
    if key not in city_state_lookup:

        city_state_lookup[key] = {
            "id": row["id"],
            "name": row["name"]
        }


# ============================================================
# CITY ONLY LOOKUP
# ============================================================

city_only_lookup = {}

for _, row in cities.iterrows():

    city_name = normalize(row["name"])

    if not city_name:
        continue

    city_only_lookup.setdefault(
        city_name,
        []
    ).append({
        "id": row["id"],
        "name": row["name"],
        "parent_id": row["parent_id"]
    })


# ============================================================
# GET STATE ID
# ============================================================

def get_state_id(state_name):

    state_clean = normalize(state_name)

    if not state_clean:
        return None

    candidates = state_lookup.get(
        state_clean,
        []
    )

    if len(candidates) == 1:
        return candidates[0]

    return None


# ============================================================
# BUILD CITY -> STATES FROM MASTER PRIORITY
#
# IMPORTANT:
# We inspect ALL rows of a city.
# We do NOT take only the first row.
# ============================================================

print("\nReading city/state combinations...")


master_city_state = (
    master_df[
        ["city", "state"]
    ]
    .copy()
)


master_city_state["_city_clean"] = (
    master_city_state["city"].apply(normalize)
)

master_city_state["_state_clean"] = (
    master_city_state["state"].apply(normalize)
)


# Remove blank city
master_city_state = master_city_state[
    master_city_state["_city_clean"] != ""
]


city_state_pairs = (
    master_city_state[
        [
            "_city_clean",
            "_state_clean"
        ]
    ]
    .drop_duplicates()
)


print(
    "Unique city/state combinations :",
    len(city_state_pairs)
)


# ============================================================
# MATCH CACHE
# ============================================================

match_cache = {}

new_locations = []


# ============================================================
# MATCH EACH CITY + STATE
# ============================================================

print("\nMatching city + state...")


for index, pair in city_state_pairs.iterrows():

    city_clean = pair["_city_clean"]
    state_clean = pair["_state_clean"]


    # --------------------------------------------------------
    # STATE ID
    # --------------------------------------------------------

    state_candidates = state_lookup.get(
        state_clean,
        []
    )

    state_id = None

    if len(state_candidates) == 1:

        state_id = state_candidates[0]


    # --------------------------------------------------------
    # EXACT CITY + STATE
    # --------------------------------------------------------

    location = None

    if state_id is not None:

        location = city_state_lookup.get(
            (
                city_clean,
                str(state_id)
            )
        )


    if location is not None:

        match_cache[
            (
                city_clean,
                state_clean
            )
        ] = (
            location["id"],
            location["name"],
            "EXACT_CITY_STATE"
        )

        continue


    # --------------------------------------------------------
    # CITY EXISTS BUT STATE NOT RESOLVED
    #
    # DO NOT CREATE DUPLICATE.
    # --------------------------------------------------------

    city_candidates = city_only_lookup.get(
        city_clean,
        []
    )


    if state_id is None:

        # If there is exactly one city with this name,
        # use it rather than creating duplicate.
        if len(city_candidates) == 1:

            location = city_candidates[0]

            match_cache[
                (
                    city_clean,
                    state_clean
                )
            ] = (
                location["id"],
                location["name"],
                "EXACT_CITY"
            )

            continue


    # --------------------------------------------------------
    # CITY EXISTS WITH DIFFERENT/UNKNOWN PARENT
    # --------------------------------------------------------

    if state_id is not None:

        same_state = []

        for candidate in city_candidates:

            if str(
                candidate["parent_id"]
            ) == str(state_id):

                same_state.append(
                    candidate
                )


        if len(same_state) == 1:

            location = same_state[0]

            match_cache[
                (
                    city_clean,
                    state_clean
                )
            ] = (
                location["id"],
                location["name"],
                "EXACT_CITY_STATE"
            )

            continue


    # --------------------------------------------------------
    # DO NOT DO LOOSE FUZZY MATCH
    #
    # First exact matching must be correct.
    # --------------------------------------------------------

    match_cache[
        (
            city_clean,
            state_clean
        )
    ] = (
        None,
        None,
        "NOT_FOUND"
    )


    # --------------------------------------------------------
    # SAVE NEW LOCATION CANDIDATE
    # --------------------------------------------------------

    if state_id is not None:

        new_locations.append({
            "city_clean": city_clean,
            "state_clean": state_clean,
            "state_id": state_id
        })


    if index % 20 == 0:

        print(
            f"Processed city/state pairs: {index}"
        )


print(
    "\nMatching completed."
)


# ============================================================
# REMOVE DUPLICATE NEW LOCATION CANDIDATES
# ============================================================

unique_new_locations = []

seen_new = set()


for item in new_locations:

    key = (
        item["city_clean"],
        str(item["state_id"])
    )

    if key not in seen_new:

        seen_new.add(key)

        unique_new_locations.append(
            item
        )


print(
    "New location candidates :",
    len(unique_new_locations)
)


# ============================================================
# NEXT ID
# ============================================================

numeric_ids = pd.to_numeric(
    location_df["id"],
    errors="coerce"
)

if numeric_ids.notna().any():

    next_id = int(
        numeric_ids.max()
    ) + 1

else:

    next_id = 1


# ============================================================
# CREATE NEW LOCATIONS
# ============================================================

new_rows = []


for item in unique_new_locations:

    city_clean = item["city_clean"]
    state_id = item["state_id"]


    # Check AGAIN before creating.
    # Safety against duplicates.
    existing = city_state_lookup.get(
        (
            city_clean,
            str(state_id)
        )
    )


    if existing is not None:

        match_cache[
            (
                city_clean,
                item["state_clean"]
            )
        ] = (
            existing["id"],
            existing["name"],
            "EXACT_CITY_STATE"
        )

        continue


    # --------------------------------------------------------
    # GET ORIGINAL CITY DISPLAY NAME
    # --------------------------------------------------------

    matching_rows = master_df[
        master_df["city"].apply(normalize)
        == city_clean
    ]

    if len(matching_rows) == 0:
        continue

    city_display = str(
        matching_rows.iloc[0]["city"]
    ).strip()


    # --------------------------------------------------------
    # CREATE EMPTY ROW WITH SAME COLUMNS
    # --------------------------------------------------------

    new_row = {}

    for column in location_df.columns:

        if column != "_name_clean":

            new_row[column] = None


    new_row["id"] = next_id
    new_row["parent_id"] = state_id
    new_row["location_level"] = CITY
    new_row["location_type"] = "City"
    new_row["name"] = city_display
    new_row["short_name"] = city_display
    new_row["status"] = "active"


    new_rows.append(
        new_row
    )


    # Add immediately to cache
    match_cache[
        (
            city_clean,
            item["state_clean"]
        )
    ] = (
        next_id,
        city_display,
        "NEW_LOCATION"
    )


    print(
        f"NEW LOCATION: "
        f"{city_display} "
        f"-> {next_id} "
        f"({item['state_clean']})"
    )


    next_id += 1


# ============================================================
# UPDATE MASTER PRIORITY
# ============================================================

print("\nApplying results to Master Priority...")


def resolve_master_row(row):

    city_clean = normalize(
        row["city"]
    )

    state_clean = ""

    if "state" in row.index:

        state_clean = normalize(
            row["state"]
        )


    return match_cache.get(
        (
            city_clean,
            state_clean
        ),
        (
            None,
            None,
            "NOT_FOUND"
        )
    )


results = master_df.apply(
    resolve_master_row,
    axis=1
)


master_df["location_id"] = results.apply(
    lambda x: x[0]
)

master_df["matched_location_name"] = results.apply(
    lambda x: x[1]
)

master_df["location_match_status"] = results.apply(
    lambda x: x[2]
)


# ============================================================
# UPDATED LOCATION MASTER
# ============================================================

updated_location_df = location_df.drop(
    columns=["_name_clean"],
    errors="ignore"
).copy()


if new_rows:

    new_location_df = pd.DataFrame(
        new_rows
    )

    updated_location_df = pd.concat(
        [
            updated_location_df,
            new_location_df
        ],
        ignore_index=True
    )


# ============================================================
# SAVE
# ============================================================

print("\nSaving output files...")


updated_location_df.to_csv(
    LOCATION_OUTPUT,
    index=False,
    encoding="utf-8"
)

master_df.to_csv(
    MASTER_OUTPUT,
    index=False,
    encoding="utf-8"
)


# ============================================================
# REPORT
# ============================================================

print("\n")
print("=" * 60)
print("MATCHING COMPLETED")
print("=" * 60)

print(
    "Original Location Master :",
    len(location_df)
)

print(
    "Updated Location Master  :",
    len(updated_location_df)
)

print(
    "Master Priority          :",
    len(master_df)
)

print(
    "Exact city-state matches :",
    (
        master_df["location_match_status"]
        == "EXACT_CITY_STATE"
    ).sum()
)

print(
    "Exact city matches       :",
    (
        master_df["location_match_status"]
        == "EXACT_CITY"
    ).sum()
)

print(
    "New locations            :",
    (
        master_df["location_match_status"]
        == "NEW_LOCATION"
    ).sum()
)

print(
    "Still unmatched          :",
    master_df["location_id"].isna().sum()
)

print("\nCreated ONLY:")

print(
    LOCATION_OUTPUT
)

print(
    MASTER_OUTPUT
)

print("\nRaw files were NOT changed.")