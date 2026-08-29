import pandas as pd
import re
from rapidfuzz import process, fuzz


# ============================================================
# FILES
# ============================================================

LOCATION_FILE = "location_master.csv"
MASTER_FILE = "master_priority.csv"

LOCATION_OUTPUT = "location_master_updated.csv"
MASTER_OUTPUT = "master_priority_updated.csv"


# ============================================================
# READ FILES
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
# CHECK REQUIRED COLUMNS
# ============================================================

required_location_columns = [
    "id",
    "parent_id",
    "location_level",
    "location_type",
    "name"
]

for col in required_location_columns:
    if col not in location_df.columns:
        raise ValueError(
            f"location_master.csv mein '{col}' column missing hai."
        )

if "city" not in master_df.columns:
    raise ValueError(
        "master_priority.csv mein 'city' column missing hai."
    )


# ============================================================
# NORMALIZE TEXT & HANDLE ALIASES
# ============================================================

def normalize(value):

    if pd.isna(value):
        return ""

    text = str(value).strip().casefold()

    text = re.sub(r"\s+", " ", text)

    replacements = {
        "up": "uttar pradesh",
        "mp": "madhya pradesh",
        "mh": "maharashtra",
        "maha": "maharashtra",
        "ap": "andhra pradesh",
        "tn": "tamil nadu",
        "wb": "west bengal",
        "hp": "himachal pradesh",
        "jk": "jammu and kashmir",
        "j&k": "jammu and kashmir",
        "uk": "uttarakhand",
        "cg": "chhattisgarh",
        "rj": "rajasthan",
        "raj": "rajasthan",
        "gj": "gujarat",
        "guj": "gujarat",
        "kr": "karnataka",
        "kl": "kerala",
        "mum": "mumbai",
        "bom": "mumbai",
        "bombay": "mumbai",
        "banglore": "bangalore",
        "bengaluru": "bangalore",
        "bangalore": "bangalore",
        "calcutta": "kolkata",
        "madras": "chennai",
        "new delhi": "delhi",
        "del": "delhi",
        "gurgaon": "gurugram",
        "mysore": "mysuru",
        "ooty": "ooty"
    }

    return replacements.get(text, text)


# ============================================================
# LOCATION LEVELS
# ============================================================

COUNTRY = 1
STATE = 2
CITY = 3


# ============================================================
# CLEAN LOCATION MASTER
# ============================================================

location_df["_name_clean"] = (
    location_df["name"].apply(normalize)
)

location_df["_id_clean"] = pd.to_numeric(
    location_df["id"],
    errors="coerce"
)

location_df["_parent_clean"] = pd.to_numeric(
    location_df["parent_id"],
    errors="coerce"
)

location_df["_level_clean"] = pd.to_numeric(
    location_df["location_level"],
    errors="coerce"
)


# ============================================================
# STATES
# ============================================================

states = location_df[
    location_df["_level_clean"] == STATE
].copy()

state_lookup = {}

for _, row in states.iterrows():

    if pd.isna(row["_id_clean"]):
        continue

    state_name = normalize(
        row["name"]
    )

    if not state_name:
        continue

    state_lookup.setdefault(
        state_name,
        []
    ).append(
        int(row["_id_clean"])
    )


# ============================================================
# CITIES
# ============================================================

cities = location_df[
    location_df["_level_clean"] == CITY
].copy()

print("\nLocation levels:")

print(
    "Countries :",
    (location_df["_level_clean"] == COUNTRY).sum()
)

print(
    "States    :",
    len(states)
)

print(
    "Cities    :",
    len(cities)
)


# ============================================================
# CITY LOOKUPS
# ============================================================

city_lookup = {}

city_state_lookup = {}

for _, row in cities.iterrows():

    if pd.isna(row["_id_clean"]):
        continue

    city_name = normalize(
        row["name"]
    )

    if not city_name:
        continue

    city_id = int(
        row["_id_clean"]
    )

    parent_id = row["_parent_clean"]

    if pd.isna(parent_id):
        parent_id = None
    else:
        parent_id = int(parent_id)

    record = {
        "id": city_id,
        "name": str(row["name"]).strip(),
        "parent_id": parent_id
    }

    city_lookup.setdefault(
        city_name,
        []
    ).append(
        record
    )

    if parent_id is not None:

        city_state_lookup[
            (
                city_name,
                parent_id
            )
        ] = record


city_names = list(
    city_lookup.keys()
)


# ============================================================
# STATE RESOLVER
# ============================================================

def resolve_state(state_value):

    state_clean = normalize(
        state_value
    )

    if not state_clean:
        return None

    candidates = state_lookup.get(
        state_clean,
        []
    )

    if len(candidates) == 1:
        return candidates[0]

    # Fuzzy state match
    if not candidates:

        match = process.extractOne(
            state_clean,
            list(state_lookup.keys()),
            scorer=fuzz.ratio
        )

        if match:

            matched_name, score, _ = match

            if score >= 90:

                ids = state_lookup[
                    matched_name
                ]

                if len(ids) == 1:
                    return ids[0]

    return None


# ============================================================
# CITY -> STATE MAP
# ============================================================

city_parent_map = {}

for city_name, records in city_lookup.items():

    parents = set()

    for record in records:

        if record["parent_id"] is not None:
            parents.add(
                record["parent_id"]
            )

    city_parent_map[
        city_name
    ] = parents


# ============================================================
# RESOLVE EXISTING CITY
# ============================================================

def resolve_existing_city(
    city_value,
    state_value
):

    city_clean = normalize(
        city_value
    )

    if not city_clean:
        return None

    state_clean = normalize(
        state_value
    )

    candidates = city_lookup.get(
        city_clean,
        []
    )

    if not candidates:
        return None

    # --------------------------------------------------------
    # STATE IS KNOWN
    # --------------------------------------------------------

    if state_clean:

        state_id = resolve_state(
            state_value
        )

        if state_id is None:
            return None

        same_state = [
            x
            for x in candidates
            if x["parent_id"] == state_id
        ]

        if len(same_state) == 1:
            return same_state[0]["id"]

        return None

    # --------------------------------------------------------
    # STATE IS BLANK
    # --------------------------------------------------------

    parent_ids = {
        x["parent_id"]
        for x in candidates
        if x["parent_id"] is not None
    }

    if len(parent_ids) != 1:
        return None

    exact_name = [
        x
        for x in candidates
        if x["name"].strip().casefold()
        == str(city_value).strip().casefold()
    ]

    if len(exact_name) == 1:
        return exact_name[0]["id"]

    return candidates[0]["id"]


# ============================================================
# CITY MATCH FUNCTION
# ============================================================

def match_city(
    city_value,
    state_value
):

    city_clean = normalize(
        city_value
    )

    if not city_clean:

        return (
            None,
            None,
            "BLANK_CITY"
        )

    # --------------------------------------------------------
    # RESOLVE STATE
    # --------------------------------------------------------

    state_id = resolve_state(
        state_value
    )

    # --------------------------------------------------------
    # 1. EXACT CITY + STATE
    # --------------------------------------------------------

    if state_id is not None:

        exact = city_state_lookup.get(
            (
                city_clean,
                state_id
            )
        )

        if exact:

            return (
                exact["id"],
                exact["name"],
                "EXACT_CITY_STATE"
            )

    # --------------------------------------------------------
    # 2. EXACT CITY ONLY
    # --------------------------------------------------------

    candidates = city_lookup.get(
        city_clean,
        []
    )

    if len(candidates) == 1:

        record = candidates[0]

        return (
            record["id"],
            record["name"],
            "EXACT_CITY"
        )

    # --------------------------------------------------------
    # 3. SAME CITY + STATE
    # --------------------------------------------------------

    if state_id is not None:

        same_state = [
            x
            for x in candidates
            if x["parent_id"] == state_id
        ]

        if len(same_state) == 1:

            record = same_state[0]

            return (
                record["id"],
                record["name"],
                "EXACT_CITY_STATE"
            )

    # --------------------------------------------------------
    # 4. SAFE REUSE
    # --------------------------------------------------------

    reuse_id = resolve_existing_city(
        city_value,
        state_value
    )

    if reuse_id is not None:

        reuse_records = [
            x
            for x in candidates
            if x["id"] == reuse_id
        ]

        if reuse_records:

            record = reuse_records[0]

            return (
                record["id"],
                record["name"],
                "REUSED_CITY"
            )

    # --------------------------------------------------------
    # 5. FUZZY CITY MATCH
    # --------------------------------------------------------

    fuzzy = process.extractOne(
        city_clean,
        city_names,
        scorer=fuzz.ratio
    )

    if fuzzy:

        matched_city, score, _ = fuzzy

        if score >= 92:

            fuzzy_candidates = city_lookup[
                matched_city
            ]

            if state_id is not None:

                same_state = [
                    x
                    for x in fuzzy_candidates
                    if x["parent_id"] == state_id
                ]

                if len(same_state) == 1:

                    record = same_state[0]

                    return (
                        record["id"],
                        record["name"],
                        "SPELLING_MATCH"
                    )

            if len(fuzzy_candidates) == 1:

                record = fuzzy_candidates[0]

                return (
                    record["id"],
                    record["name"],
                    "SPELLING_MATCH"
                )

    # --------------------------------------------------------
    # 6. NOT FOUND
    # --------------------------------------------------------

    return (
        None,
        None,
        "NOT_FOUND"
    )

# ============================================================
# NEW PROCESS: ADD MISSING STATES TO LOCATION MASTER
# ============================================================

print("\nChecking for missing States...")

# Sirf naye states ke liye temporarily Next ID nikalna
temp_ids = pd.to_numeric(location_df["id"], errors="coerce")
current_next_id = int(temp_ids.max()) + 1 if temp_ids.notna().any() else 1

unique_states = master_df["state"].dropna().unique()
new_states_list = []
missing_states_count = 0

for state_value in unique_states:
    state_clean = normalize(state_value)
    if not state_clean:
        continue
        
    state_id = resolve_state(state_value)
    
    # Agar state exist nahi karti hai
    if state_id is None:
        state_display = str(state_value).strip()
        
        # Nayi state ka structure banana
        new_state_row = {col: None for col in location_df.columns if not col.startswith("_")}
        new_state_row["id"] = current_next_id
        new_state_row["parent_id"] = COUNTRY
        new_state_row["location_level"] = STATE
        new_state_row["location_type"] = "State"
        new_state_row["name"] = state_display
        
        if "short_name" in location_df.columns:
            new_state_row["short_name"] = state_display
        if "status" in location_df.columns:
            new_state_row["status"] = "Active"
            
        new_states_list.append(new_state_row)
        
        # In-memory dictionary update karna taaki cities match ho sakein
        state_lookup.setdefault(state_clean, []).append(current_next_id)
        
        print(f"NEW STATE ADDED: {state_display} -> ID {current_next_id}")
        current_next_id += 1
        missing_states_count += 1

# Agar nayi states mili hain, toh unhe turant location_df mein add kar do
if new_states_list:
    new_states_df = pd.DataFrame(new_states_list)
    
    new_states_df["_name_clean"] = new_states_df["name"].apply(normalize)
    new_states_df["_id_clean"] = pd.to_numeric(new_states_df["id"], errors="coerce")
    new_states_df["_parent_clean"] = pd.to_numeric(new_states_df["parent_id"], errors="coerce")
    new_states_df["_level_clean"] = pd.to_numeric(new_states_df["location_level"], errors="coerce")
    
    location_df = pd.concat([location_df, new_states_df], ignore_index=True)

print(f"Total new states integrated: {missing_states_count}")


# ============================================================
# MATCH MASTER PRIORITY
# ============================================================

print("\nMatching Master Priority...")

location_ids = []
matched_names = []
match_statuses = []

total = len(master_df)

for i, (_, row) in enumerate(
    master_df.iterrows(),
    start=1
):

    city = row.get(
        "city",
        ""
    )

    state = row.get(
        "state",
        ""
    )

    location_id, matched_name, status = (
        match_city(
            city,
            state
        )
    )

    location_ids.append(
        location_id
    )

    matched_names.append(
        matched_name
    )

    match_statuses.append(
        status
    )

    if i % 10000 == 0:

        print(
            f"Processed: {i}/{total}"
        )


# ============================================================
# ADD MATCH RESULT
# ============================================================

master_df["location_id"] = location_ids

master_df["matched_location_name"] = (
    matched_names
)

master_df["location_match_status"] = (
    match_statuses
)


# ============================================================
# FIND GENUINELY MISSING CITIES
# ============================================================

missing = master_df[
    (
        master_df["location_match_status"]
        == "NOT_FOUND"
    )
    &
    (
        master_df["city"].notna()
    )
].copy()

print(
    "\nGenuinely unmatched rows :",
    len(missing)
)


# ============================================================
# NEXT LOCATION ID
# ============================================================

numeric_ids = pd.to_numeric(
    location_df["id"],
    errors="coerce"
)

if numeric_ids.notna().any():

    next_id = (
        int(numeric_ids.max())
        + 1
    )

else:

    next_id = 1


# ============================================================
# NEW LOCATION CACHE
# ============================================================

new_rows = []

new_location_cache = {}


# ============================================================
# PROCESS GENUINELY MISSING CITIES
# ============================================================

missing_pairs = (
    missing[
        [
            "city",
            "state"
        ]
    ]
    .drop_duplicates()
)


for _, row in missing_pairs.iterrows():

    city_value = row["city"]
    state_value = row["state"]

    city_clean = normalize(
        city_value
    )

    state_clean = normalize(
        state_value
    )

    if not city_clean:
        continue

    # --------------------------------------------------------
    # RESOLVE STATE
    # --------------------------------------------------------

    state_id = resolve_state(
        state_value
    )

    # --------------------------------------------------------
    # NO STATE
    # --------------------------------------------------------

    if state_id is None:

        # Try to reuse an existing city safely.
        reuse_id = resolve_existing_city(
            city_value,
            state_value
        )

        if reuse_id is not None:

            records = [
                x
                for x in city_lookup.get(
                    city_clean,
                    []
                )
                if x["id"] == reuse_id
            ]

            if records:

                record = records[0]

                mask = (
                    master_df["city"]
                    .apply(normalize)
                    == city_clean
                )

                # Only update rows where state is blank
                blank_state_mask = (
                    master_df["state"]
                    .apply(normalize)
                    == ""
                )

                final_mask = (
                    mask
                    & blank_state_mask
                    & (
                        master_df[
                            "location_match_status"
                        ]
                        == "NOT_FOUND"
                    )
                )

                master_df.loc[
                    final_mask,
                    "location_id"
                ] = record["id"]

                master_df.loc[
                    final_mask,
                    "matched_location_name"
                ] = record["name"]

                master_df.loc[
                    final_mask,
                    "location_match_status"
                ] = "REUSED_CITY"

                continue

        print(
            f"Cannot safely add: "
            f"{city_value} "
            f"(state not resolved)"
        )

        continue

    cache_key = (
        city_clean,
        state_id
    )

    # --------------------------------------------------------
    # ALREADY CREATED DURING THIS RUN
    # --------------------------------------------------------

    if cache_key in new_location_cache:

        existing_id = new_location_cache[
            cache_key
        ]

        mask = (
            master_df["city"]
            .apply(normalize)
            == city_clean
        )

        state_mask = (
            master_df["state"]
            .apply(normalize)
            == state_clean
        )

        final_mask = (
            mask
            & state_mask
            & (
                master_df[
                    "location_match_status"
                ]
                == "NOT_FOUND"
            )
        )

        master_df.loc[
            final_mask,
            "location_id"
        ] = existing_id

        master_df.loc[
            final_mask,
            "matched_location_name"
        ] = str(
            city_value
        ).strip()

        master_df.loc[
            final_mask,
            "location_match_status"
        ] = "NEW_LOCATION"

        continue

    # --------------------------------------------------------
    # DOUBLE CHECK EXISTING CITY
    # --------------------------------------------------------

    existing = city_state_lookup.get(
        (
            city_clean,
            state_id
        )
    )

    if existing:

        mask = (
            master_df["city"]
            .apply(normalize)
            == city_clean
        )

        state_mask = (
            master_df["state"]
            .apply(normalize)
            == state_clean
        )

        final_mask = (
            mask
            & state_mask
            & (
                master_df[
                    "location_match_status"
                ]
                == "NOT_FOUND"
            )
        )

        master_df.loc[
            final_mask,
            "location_id"
        ] = existing["id"]

        master_df.loc[
            final_mask,
            "matched_location_name"
        ] = existing["name"]

        master_df.loc[
            final_mask,
            "location_match_status"
        ] = "EXACT_CITY_STATE"

        continue

    # --------------------------------------------------------
    # CREATE NEW CITY
    # --------------------------------------------------------

    city_display = str(
        city_value
    ).strip()

    new_row = {}

    for column in location_df.columns:

        if column.startswith("_"):
            continue

        new_row[column] = None

    new_row["id"] = next_id
    new_row["parent_id"] = state_id
    new_row["location_level"] = CITY
    new_row["location_type"] = "City"
    new_row["name"] = city_display

    if "short_name" in location_df.columns:
        new_row["short_name"] = city_display

    if "status" in location_df.columns:
        new_row["status"] = "active"

    new_rows.append(
        new_row
    )

    new_location_cache[
        cache_key
    ] = next_id

    # Add immediately to lookup
    new_record = {
        "id": next_id,
        "name": city_display,
        "parent_id": state_id
    }

    city_lookup.setdefault(
        city_clean,
        []
    ).append(
        new_record
    )

    city_state_lookup[
        (
            city_clean,
            state_id
        )
    ] = new_record

    # --------------------------------------------------------
    # UPDATE MASTER
    # --------------------------------------------------------

    mask = (
        master_df["city"]
        .apply(normalize)
        == city_clean
    )

    state_mask = (
        master_df["state"]
        .apply(normalize)
        == state_clean
    )

    final_mask = (
        mask
        & state_mask
        & (
            master_df[
                "location_match_status"
            ]
            == "NOT_FOUND"
        )
    )

    master_df.loc[
        final_mask,
        "location_id"
    ] = next_id

    master_df.loc[
        final_mask,
        "matched_location_name"
    ] = city_display

    master_df.loc[
        final_mask,
        "location_match_status"
    ] = "NEW_LOCATION"

    print(
        f"NEW LOCATION: "
        f"{city_display} "
        f"-> ID {next_id} "
        f"({state_clean})"
    )

    next_id += 1


# ============================================================
# FINAL SAFETY PASS
#
# Resolve remaining blank-state cities if they have exactly
# one safe existing city location.
# ============================================================

remaining = master_df[
    (
        master_df["location_match_status"]
        == "NOT_FOUND"
    )
    &
    (
        master_df["city"].notna()
    )
].copy()


for idx, row in remaining.iterrows():

    city = row.get(
        "city",
        ""
    )

    state = row.get(
        "state",
        ""
    )

    reuse_id = resolve_existing_city(
        city,
        state
    )

    if reuse_id is None:
        continue

    city_clean = normalize(
        city
    )

    records = [
        x
        for x in city_lookup.get(
            city_clean,
            []
        )
        if x["id"] == reuse_id
    ]

    if not records:
        continue

    record = records[0]

    master_df.at[
        idx,
        "location_id"
    ] = record["id"]

    master_df.at[
        idx,
        "matched_location_name"
    ] = record["name"]

    master_df.at[
        idx,
        "location_match_status"
    ] = "REUSED_CITY"


# ============================================================
# BUILD UPDATED LOCATION MASTER
# ============================================================

updated_location_df = (
    location_df
    .drop(
        columns=[
            "_name_clean",
            "_id_clean",
            "_parent_clean",
            "_level_clean"
        ],
        errors="ignore"
    )
    .copy()
)


if new_rows:

    new_location_df = pd.DataFrame(
        new_rows
    )

    # Ensure same columns
    for column in updated_location_df.columns:

        if column not in new_location_df.columns:

            new_location_df[column] = None

    new_location_df = (
        new_location_df[
            updated_location_df.columns
        ]
    )

    updated_location_df = pd.concat(
        [
            updated_location_df,
            new_location_df
        ],
        ignore_index=True
    )


# ============================================================
# SAVE OUTPUT
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
# FINAL REPORT
# ============================================================

print("\n")
print("=" * 60)
print("MATCHING COMPLETED")
print("=" * 60)

print(
    "Original Location Master :",
    len(location_df) - missing_states_count
)

print(
    "Updated Location Master  :",
    len(updated_location_df)
)

print(
    "Master Priority rows     :",
    len(master_df)
)

print(
    "Exact City + State       :",
    (
        master_df[
            "location_match_status"
        ]
        == "EXACT_CITY_STATE"
    ).sum()
)

print(
    "Exact City               :",
    (
        master_df[
            "location_match_status"
        ]
        == "EXACT_CITY"
    ).sum()
)

print(
    "Spelling Matches         :",
    (
        master_df[
            "location_match_status"
        ]
        == "SPELLING_MATCH"
    ).sum()
)

print(
    "Reused City              :",
    (
        master_df[
            "location_match_status"
        ]
        == "REUSED_CITY"
    ).sum()
)

print(
    "New Locations            :",
    (
        master_df[
            "location_match_status"
        ]
        == "NEW_LOCATION"
    ).sum()
)

print(
    "Blank City               :",
    (
        master_df[
            "location_match_status"
        ]
        == "BLANK_CITY"
    ).sum()
)

print(
    "Still Unmatched          :",
    (
        master_df[
            "location_match_status"
        ]
        == "NOT_FOUND"
    ).sum()
)

print("\nCreated ONLY:")

print(
    LOCATION_OUTPUT
)

print(
    MASTER_OUTPUT
)

print("\nRaw files were NOT changed.")