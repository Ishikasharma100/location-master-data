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
# REGION PROCESSING (IN-MEMORY)
# ============================================================
# The original city/state matching logic above is kept unchanged.
# Region processing runs on the already-updated DataFrames.
# It does not read or write intermediate CSV files.
# ============================================================

# ============================================================
# REGION CONFIGURATION
# ============================================================

VALID_REGIONS = {
    "North",
    "South",
    "East",
    "West",
    "Central",
    "North East",
}

MIN_SAMPLES = 3
MAJORITY_SHARE = 0.5

STATE_LEVEL = 2


# ============================================================
# MANUAL CORRECTIONS
# ============================================================

# These are individually verified data errors.
# Do NOT add general geography here.
MANUAL_LOCATION_CORRECTIONS = {
    "nraipur": "Central",
}


# URLs that are known to produce false location matches.
SKIP_URL_FRAGMENTS = [
    "gajuwaka_g4058520",
]


# States that have no usable state+region data in the source.
MANUAL_STATE_FALLBACK = {
    "uttar pradesh": "North",
    "andaman and nicobar islands": "South",
    "andaman and nicobar": "South",
    "lakshadweep": "South",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize(value):
    """
    Normalize text for matching.

    Example:
        ' New Delhi ' -> 'new delhi'
        'Bangalore'  -> 'bangalore'
    """

    if pd.isna(value):
        return ""

    text = str(value).strip().casefold()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("&", "and")

    return text


def is_usable_name(name):
    """
    Checks whether a location name is safe for free-text matching.
    """

    if not name:
        return False

    # Must contain at least one letter
    if not re.search(r"[a-z]", name):
        return False

    # Remove special characters
    clean = re.sub(r"[^a-z0-9]", "", name)

    # Avoid extremely short names
    if len(clean) < 4:
        return False

    return True


def majority_vote(
    df,
    group_col,
    value_col,
    min_samples=MIN_SAMPLES,
    majority_share=MAJORITY_SHARE,
):
    """
    Calculate majority region for each group.

    Example:

        Delhi -> North 80%
        Delhi -> West 20%

    Result:
        Delhi -> North
    """

    if df.empty:
        return pd.DataFrame(
            columns=[
                "total",
                "top_value",
                "top_share",
                "confident",
            ]
        )

    # Count values
    counts = (
        df.groupby(group_col)[value_col]
        .value_counts()
        .reset_index(name="count")
    )

    # Total observations per group
    counts["total"] = (
        counts.groupby(group_col)["count"]
        .transform("sum")
    )

    # Highest count per group
    counts["top_count"] = (
        counts.groupby(group_col)["count"]
        .transform("max")
    )

    # Percentage of winning region
    counts["top_share"] = (
        counts["top_count"] / counts["total"]
    )

    # Keep winning rows
    top_rows = counts[
        counts["count"] == counts["top_count"]
    ].copy()

    # If there is a tie, keep first but confidence will be false
    top_rows = top_rows.drop_duplicates(
        subset=group_col,
        keep="first",
    )

    top_rows = top_rows.set_index(group_col)

    top_rows = top_rows[
        ["total", value_col, "top_share"]
    ]

    top_rows = top_rows.rename(
        columns={
            value_col: "top_value"
        }
    )

    top_rows["confident"] = (
        (top_rows["total"] >= min_samples)
        & (top_rows["top_share"] > majority_share)
    )

    return top_rows


def is_skipped(url):
    """
    Check whether a URL belongs to a known conflict.
    """

    if pd.isna(url):
        return False

    url = str(url).lower()

    return any(
        fragment.lower() in url
        for fragment in SKIP_URL_FRAGMENTS
    )


# ============================================================
# URL EXTRACTORS
# ============================================================

_OLX_PATTERN = re.compile(
    r"/([a-z0-9\-]+)_g\d+",
    re.IGNORECASE,
)


def slug_olx(url):
    match = _OLX_PATTERN.search(str(url))

    if match:
        return match.group(1).replace("-", " ")

    return None


def slug_justdial(url):
    match = re.search(
        r"justdial\.com/([A-Za-z][A-Za-z\-]*)/",
        str(url),
    )

    if not match:
        return None

    city = match.group(1)

    ignored = {
        "india",
        "list",
        "streaming",
        "verticals",
        "guides",
        "entertainment",
    }

    if city.lower() in ignored:
        return None

    return city.replace("-", " ")


def slug_magicpin(url):
    match = re.search(
        r"magicpin\.in/(?:india/)?([A-Za-z][A-Za-z\-]*)/",
        str(url),
    )

    if not match:
        return None

    city = match.group(1)

    if city.lower() in {"india", "blog"}:
        return None

    return city.replace("-", " ")


def slug_zomato(url):
    match = re.search(
        r"zomato\.com/([a-z][a-z\-]*)/",
        str(url),
    )

    if not match:
        return None

    city = match.group(1)

    ignored = {
        "order-food-online-in-train",
        "restaurants-near-me",
    }

    if city.lower() in ignored:
        return None

    return city.replace("-", " ")


def slug_district(url):
    url = str(url)

    match = re.search(
        r"-in-([a-z\-]+)-(?:CD|MV)\d+",
        url,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).replace("-", " ")

    match = re.search(
        r"district\.in/dining/([a-z\-]+)/",
        url,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).replace("-", " ")

    return None


SOURCE_EXTRACTORS = {
    "olx.in": slug_olx,
    "justdial.com": slug_justdial,
    "magicpin.in": slug_magicpin,
    "zomato.com": slug_zomato,
    "district.in": slug_district,
}


# ============================================================
# TEXT MATCHING
# ============================================================

WORD_PATTERN = re.compile(r"[a-z0-9]+")


def build_text_lookup(location_df):
    """
    Build:

        location name -> region

    using majority voting.
    """

    temp = location_df.copy()

    temp["_name_norm"] = temp["name"].apply(normalize)

    temp["_level_num"] = pd.to_numeric(
        temp["location_level"],
        errors="coerce",
    )

    # Location levels used for text matching
    temp = temp[
        temp["_level_num"].isin(
            [3, 4, 5, 6, 7]
        )
    ]

    temp = temp[
        temp["_name_norm"] != ""
    ]

    stats = majority_vote(
        temp,
        "_name_norm",
        "region",
    )

    confident = stats[
        stats["confident"]
    ]

    lookup = {}

    for name, row in confident.iterrows():

        if is_usable_name(name):

            region = row["top_value"]

            if region in VALID_REGIONS:
                lookup[name] = region

    # Add verified correction
    for name, region in MANUAL_LOCATION_CORRECTIONS.items():
        lookup[normalize(name)] = region

    return lookup


def find_place_in_text(text, lookup):
    """
    Search text for a known location.

    Longest matching phrase is preferred.
    """

    if pd.isna(text):
        return None

    words = WORD_PATTERN.findall(
        str(text).lower()
    )

    if not words:
        return None

    max_ngram = max(
        (
            len(name.split())
            for name in lookup
        ),
        default=1,
    )

    max_ngram = min(max_ngram, 4)

    # Longest matches first
    for n in range(max_ngram, 0, -1):

        for i in range(
            len(words) - n + 1
        ):

            candidate = " ".join(
                words[i:i + n]
            )

            if candidate in lookup:
                return candidate

    return None





def fill_regions(location_df, master_df):

    # ========================================================
    # STEP 1
    # COMPUTE STATE -> REGION
    # ========================================================

    print("\n" + "-" * 70)
    print("STEP 1: Computing STATE -> REGION")
    print("-" * 70)

    have_both = master_df[
        master_df["state"].notna()
        & master_df["region"].notna()
    ].copy()

    # Keep only valid regions
    have_both = have_both[
        have_both["region"].isin(
            VALID_REGIONS
        )
    ]

    have_both["state_norm"] = (
        have_both["state"].apply(normalize)
    )

    state_stats = majority_vote(
        have_both,
        "state_norm",
        "region",
        min_samples=1,
        majority_share=0.0,
    )

    STATE_REGION = dict(
        zip(
            state_stats.index,
            state_stats["top_value"],
        )
    )

    # Add manual fallback only if state is absent
    for state, region in MANUAL_STATE_FALLBACK.items():

        state_norm = normalize(state)

        STATE_REGION.setdefault(
            state_norm,
            region,
        )

    # Odisha alias
    if "odisha" in STATE_REGION:

        STATE_REGION.setdefault(
            "od",
            STATE_REGION["odisha"],
        )

    print(
        f"States resolved: {len(STATE_REGION)}"
    )


    # ========================================================
    # STEP 2
    # LOCATION MASTER STATE CASCADE
    # ========================================================

    print("\n" + "-" * 70)
    print("STEP 2: Filling location_master regions")
    print("-" * 70)

    location_df["_id_num"] = pd.to_numeric(
        location_df["id"],
        errors="coerce",
    )

    location_df["_parent_num"] = pd.to_numeric(
        location_df["parent_id"],
        errors="coerce",
    )

    location_df["_level_num"] = pd.to_numeric(
        location_df["location_level"],
        errors="coerce",
    )


    # --------------------------------------------------------
    # State ID -> Region
    # --------------------------------------------------------

    state_id_to_region = {}

    state_rows = location_df[
        location_df["_level_num"]
        == STATE_LEVEL
    ]

    for _, row in state_rows.iterrows():

        state_name = normalize(
            row["name"]
        )

        region = STATE_REGION.get(
            state_name
        )

        location_id = row["_id_num"]

        if (
            pd.notna(location_id)
            and region in VALID_REGIONS
        ):

            state_id_to_region[
                int(location_id)
            ] = region


    # --------------------------------------------------------
    # Parent maps
    # --------------------------------------------------------

    id_to_parent = dict(
        zip(
            location_df["_id_num"],
            location_df["_parent_num"],
        )
    )

    id_to_level = dict(
        zip(
            location_df["_id_num"],
            location_df["_level_num"],
        )
    )


    # --------------------------------------------------------
    # Find region through parent chain
    # --------------------------------------------------------

    def find_region_for_location(location_id):

        if pd.isna(location_id):
            return None

        seen = set()
        current = location_id

        while (
            pd.notna(current)
            and current not in seen
        ):

            seen.add(current)

            level = id_to_level.get(
                current
            )

            # State reached
            if level == STATE_LEVEL:

                try:
                    return state_id_to_region.get(
                        int(current)
                    )
                except (ValueError, TypeError):
                    return None

            current = id_to_parent.get(
                current
            )

        return None


    location_df["region"] = (
        location_df["_id_num"]
        .apply(find_region_for_location)
    )


    print(
        "Regions filled through parent cascade:"
    )

    print(
        f"  {location_df['region'].notna().sum():,}"
        f" / {len(location_df):,}"
    )


    # ========================================================
    # STEP 3
    # MAJORITY VOTE FOR DUPLICATE NAMES
    # ========================================================

    print("\n" + "-" * 70)
    print("STEP 3: Resolving duplicate location names")
    print("-" * 70)

    location_df["_name_norm"] = (
        location_df["name"].apply(normalize)
    )

    name_subset = location_df[
        location_df["_level_num"].isin(
            [3, 4]
        )
    ].copy()

    name_subset = name_subset[
        name_subset["_name_norm"] != ""
    ]

    name_stats = majority_vote(
        name_subset,
        "_name_norm",
        "region",
    )

    confident_names = name_stats[
        name_stats["confident"]
    ]

    ambiguous_names = name_stats[
        ~name_stats["confident"]
    ]

    NAME_TO_REGION = dict(
        zip(
            confident_names.index,
            confident_names["top_value"],
        )
    )

    # Manual verified corrections
    for name, region in MANUAL_LOCATION_CORRECTIONS.items():

        NAME_TO_REGION[
            normalize(name)
        ] = region


    # --------------------------------------------------------
    # Correct location_master
    # --------------------------------------------------------

    mapped_region = (
        location_df["_name_norm"]
        .map(NAME_TO_REGION)
    )

    corrected_rows = (
        mapped_region.notna()
        & (
            mapped_region
            != location_df["region"]
        )
    ).sum()


    location_df["region"] = (
        mapped_region.combine_first(
            location_df["region"]
        )
    )


    print(
        f"Unique names analysed : {len(name_stats):,}"
    )

    print(
        f"Confident names        : {len(confident_names):,}"
    )

    print(
        f"Ambiguous names        : {len(ambiguous_names):,}"
    )

    print(
        f"Rows corrected         : {corrected_rows:,}"
    )


    # ========================================================
    # STEP 3B
    # BUILD TEXT MATCH LOOKUP
    # ========================================================

    print("\n" + "-" * 70)
    print("STEP 3B: Building text matching lookup")
    print("-" * 70)

    text_lookup = build_text_lookup(
        location_df
    )

    print(
        f"Usable location names: {len(text_lookup):,}"
    )


    # ========================================================
    # STEP 4
    # MASTER PRIORITY REGION
    # ========================================================

    print("\n" + "-" * 70)
    print("STEP 4: Filling master_priority regions")
    print("-" * 70)


    before_count = (
        master_df["region"]
        .notna()
        .sum()
    )


    # --------------------------------------------------------
    # 4B - STATE
    # --------------------------------------------------------

    blank = master_df["region"].isna()

    state_norm = (
        master_df.loc[blank, "state"]
        .apply(normalize)
    )

    master_df.loc[
        blank,
        "region"
    ] = state_norm.map(
        STATE_REGION
    )


    # --------------------------------------------------------
    # 4C - LOCATION ID
    # --------------------------------------------------------

    location_id_to_region = {}

    location_ids = pd.to_numeric(
        location_df["id"],
        errors="coerce",
    )

    for location_id, region in zip(
        location_ids,
        location_df["region"],
    ):

        if (
            pd.notna(location_id)
            and region in VALID_REGIONS
        ):

            location_id_to_region[
                int(location_id)
            ] = region


    blank = (
        master_df["region"].isna()
        & master_df["location_id"].notna()
    )

    master_location_ids = pd.to_numeric(
        master_df.loc[
            blank,
            "location_id"
        ],
        errors="coerce",
    )

    master_df.loc[
        blank,
        "region"
    ] = master_location_ids.map(
        location_id_to_region
    )


    # --------------------------------------------------------
    # 4D - CITY
    # --------------------------------------------------------

    blank = (
        master_df["region"].isna()
        & master_df["city"].notna()
    )

    city_norm = (
        master_df.loc[
            blank,
            "city"
        ].apply(normalize)
    )

    master_df.loc[
        blank,
        "region"
    ] = city_norm.map(
        text_lookup
    )


    after_authoritative = (
        master_df["region"]
        .notna()
        .sum()
    )

    print(
        f"Authoritative matching:"
    )

    print(
        f"  {before_count:,} -> "
        f"{after_authoritative:,}"
    )


    # ========================================================
    # 4E
    # URL / KEYWORD FALLBACK
    # ========================================================

    print("\nSearching URL and keyword data...")

    blank_mask = (
        master_df["region"].isna()
    )

    blank_rows = master_df.loc[
        blank_mask
    ]


    def resolve_from_url_and_keyword(row):

        # Known conflict
        if is_skipped(
            row.get("ranking_url")
        ):
            return None, "skipped_known_conflict"


        source = row.get(
            "source"
        )

        url = row.get(
            "ranking_url"
        )

        keyword = row.get(
            "keyword"
        )

        if pd.isna(keyword):
            keyword = ""


        # ----------------------------------------------------
        # Try source-specific URL
        # ----------------------------------------------------

        if (
            pd.notna(url)
            and source in SOURCE_EXTRACTORS
        ):

            slug = SOURCE_EXTRACTORS[
                source
            ](url)

            if slug:

                # NCR = National Capital Region
                if (
                    slug.strip().lower()
                    == "ncr"
                ):

                    return (
                        "North",
                        "ncr_alias",
                    )


                place = find_place_in_text(
                    slug,
                    text_lookup,
                )

                if place:

                    return (
                        text_lookup[place],
                        f"slug:{place}",
                    )


        # ----------------------------------------------------
        # Try URL + keyword
        # ----------------------------------------------------

        combined_text = (
            f"{url if pd.notna(url) else ''} "
            f"{keyword}"
        )


        place = find_place_in_text(
            combined_text,
            text_lookup,
        )


        if place:

            return (
                text_lookup[place],
                f"text:{place}",
            )


        return (
            None,
            "no_match",
        )


    if len(blank_rows) > 0:

        results = blank_rows.apply(
            resolve_from_url_and_keyword,
            axis=1,
        )

        resolved_regions = results.apply(
            lambda x: x[0]
        )

        resolved_methods = results.apply(
            lambda x: x[1]
        )


        matched_indices = (
            resolved_regions[
                resolved_regions.notna()
            ].index
        )


        master_df.loc[
            matched_indices,
            "region"
        ] = resolved_regions.loc[
            matched_indices
        ]


        print(
            f"URL/keyword matches: "
            f"+{len(matched_indices):,}"
        )


        if len(matched_indices) > 0:

            print(
                "\nMethod breakdown:"
            )

            method_counts = (
                resolved_methods
                .loc[matched_indices]
                .apply(
                    lambda x: x.split(":")[0]
                )
                .value_counts()
            )

            print(
                method_counts.to_string()
            )

    else:

        print(
            "No blank rows remained "
            "for URL/keyword matching."
        )


    # ========================================================
    # STEP 5
    # FINAL COUNTS
    # ========================================================

    final_count = (
        master_df["region"]
        .notna()
        .sum()
    )

    missing_count = (
        master_df["region"]
        .isna()
        .sum()
    )


    print("\n" + "=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    print(
        f"master_priority total : "
        f"{len(master_df):,}"
    )

    print(
        f"Region filled          : "
        f"{final_count:,}"
    )

    print(
        f"Region missing         : "
        f"{missing_count:,}"
    )


    # ========================================================
    # SELF CHECK
    # ========================================================

    print("\n" + "=" * 70)
    print("SELF-CHECK")
    print("=" * 70)


    problems = []


    # --------------------------------------------------------
    # Check manual location corrections
    # --------------------------------------------------------

    for name, expected_region in (
        MANUAL_LOCATION_CORRECTIONS.items()
    ):

        normalized_name = normalize(name)

        subset = location_df[
            location_df["name"]
            .apply(normalize)
            == normalized_name
        ]

        regions = (
            subset["region"]
            .dropna()
            .unique()
        )

        if len(regions) > 1:

            problems.append(
                f"'{name}' has multiple regions: "
                f"{list(regions)}"
            )

        elif (
            len(regions) == 1
            and regions[0] != expected_region
        ):

            problems.append(
                f"'{name}' expected "
                f"'{expected_region}', "
                f"got '{regions[0]}'"
            )


    # --------------------------------------------------------
    # Check skipped URLs
    # --------------------------------------------------------

    for fragment in SKIP_URL_FRAGMENTS:

        matches = master_df[
            master_df["ranking_url"]
            .astype(str)
            .str.contains(
                fragment,
                case=False,
                na=False,
            )
        ]

        wrongly_filled = matches[
            matches["region"].notna()
        ]

        if len(wrongly_filled) > 0:

            problems.append(
                f"Known conflict URL "
                f"'{fragment}' has "
                f"{len(wrongly_filled)} "
                f"filled rows."
            )


    # --------------------------------------------------------
    # Check valid region values
    # --------------------------------------------------------

    master_bad_values = (
        set(
            master_df["region"]
            .dropna()
            .unique()
        )
        - VALID_REGIONS
    )


    location_bad_values = (
        set(
            location_df["region"]
            .dropna()
            .unique()
        )
        - VALID_REGIONS
    )


    if master_bad_values:

        problems.append(
            "Invalid master_priority regions: "
            f"{master_bad_values}"
        )


    if location_bad_values:

        problems.append(
            "Invalid location_master regions: "
            f"{location_bad_values}"
        )


    # --------------------------------------------------------
    # Print self-check result
    # --------------------------------------------------------

    if problems:

        print(
            f"\nSELF-CHECK FAILED: "
            f"{len(problems)} issue(s)"
        )

        for problem in problems:

            print(
                f"  ! {problem}"
            )

    else:

        print(
            "\nSELF-CHECK PASSED."
        )


    return location_df, master_df


# ============================================================
# AREA CORRECTION PROCESSING
# ============================================================
# This section is added after City/State/Region processing.
# It works ONLY on the in-memory updated DataFrames.
# Raw CSV files are never modified.
# ============================================================

def fix_incorrect_areas(location, master):

    print("\n" + "=" * 70)
    print("STARTING AREA CORRECTION PROCESS")
    print("=" * 70)

    # --------------------------------------------------------
    # HELPER FUNCTIONS
    # --------------------------------------------------------

    def area_norm(x):
        if pd.isna(x):
            return None
        return " ".join(str(x).strip().lower().split())


    def area_slug(x):
        x = re.sub(r"[^a-zA-Z0-9\s]", "", str(x))
        return "-".join(x.strip().lower().split())


    def area_is_numeric(x):
        if pd.isna(x):
            return False
        x = str(x)
        return sum(c.isdigit() for c in x) > len(x) * 0.4


    def clean_id(x):
        if pd.isna(x):
            return None
        x = str(x).strip()
        if x.endswith(".0"):
            x = x[:-2]
        return x


    # --------------------------------------------------------
    # LOCATION HIERARCHY
    # --------------------------------------------------------

    parent = {
        clean_id(row["id"]): clean_id(row["parent_id"])
        for _, row in location.iterrows()
        if clean_id(row["id"]) is not None
    }

    names = {
        clean_id(row["id"]): row["name"]
        for _, row in location.iterrows()
        if clean_id(row["id"]) is not None
    }


    def ancestors(location_id):

        result = []
        seen = set()

        location_id = clean_id(location_id)

        while location_id and location_id not in seen and location_id in names:

            seen.add(location_id)

            location_id = parent.get(location_id)

            if location_id:
                result.append(names.get(location_id))

        return result


    # --------------------------------------------------------
    # FIND INCORRECT AREA ROWS
    # --------------------------------------------------------

    areas = location[
        location["location_type"].astype(str).str.strip().str.lower() == "area"
    ].copy()

    print(f"Total Area rows: {len(areas):,}")

    if areas.empty:
        print("No Area rows found. Area correction skipped.")
        return location, master


    areas["ancestors"] = areas["id"].apply(ancestors)

    areas["incorrect"] = areas.apply(
        lambda r: area_is_numeric(r["name"]) or any(
            area_norm(r["name"]) == area_norm(a)
            for a in r["ancestors"] if a
        ),
        axis=1
    )

    incorrect = areas[areas["incorrect"]].copy()

    print(f"Incorrect Area rows found: {len(incorrect):,}")


    # --------------------------------------------------------
    # GET AREA NAMES FROM MASTER PRIORITY
    # --------------------------------------------------------

    if "location_id" not in master.columns or "area" not in master.columns:
        print("WARNING: 'location_id' or 'area' column missing.")
        print("Area correction skipped.")
        return location, master


    m = master[
        master["location_id"].notna() &
        master["area"].notna()
    ][["location_id", "area"]].copy()

    m["location_id_clean"] = m["location_id"].apply(clean_id)
    m["norm_area"] = m["area"].apply(area_norm)

    m = m.dropna(subset=["location_id_clean", "norm_area"])

    m = m.drop_duplicates(["location_id_clean", "norm_area"])

    candidates = (
        m.groupby("location_id_clean")["area"]
        .apply(list)
        .to_dict()
    )


    # --------------------------------------------------------
    # EXISTING CORRECT AREA NAMES
    # --------------------------------------------------------

    correct = areas[~areas["incorrect"]].copy()
    correct["norm_name"] = correct["name"].apply(area_norm)
    correct["parent_id_clean"] = correct["parent_id"].apply(clean_id)

    used = (
        correct.dropna(subset=["parent_id_clean"])
        .groupby("parent_id_clean")["norm_name"]
        .apply(set)
        .to_dict()
    )


    # --------------------------------------------------------
    # UPDATE INCORRECT AREA NAMES
    # --------------------------------------------------------

    updated = location.copy()

    corrections = 0

    incorrect["parent_id_clean"] = incorrect["parent_id"].apply(clean_id)

    for city_id, rows in incorrect.groupby("parent_id_clean"):

        used_names = set(used.get(city_id, set()))

        available = [
            area for area in candidates.get(city_id, [])
            if area_norm(area) not in used_names
        ]

        for _, row in rows.sort_values("id").iterrows():

            if available:

                new_name = available.pop(0)

                row_mask = (
                    updated["id"].apply(clean_id)
                    == clean_id(row["id"])
                )

                updated.loc[row_mask, "name"] = new_name

                if "slug" in updated.columns:
                    updated.loc[row_mask, "slug"] = area_slug(new_name)

                corrections += 1


    print("\nArea correction completed.")
    print(f"Incorrect Area rows : {len(incorrect):,}")
    print(f"Area rows corrected : {corrections:,}")

    return updated, master


# ============================================================
# FINAL SAVE - ONLY TWO OUTPUT FILES
# ============================================================

print("\nStarting region processing...")

# Apply region logic to the in-memory outputs produced by data.py.
updated_location_df, master_df = fill_regions(
    updated_location_df,
    master_df,
)


# ============================================================
# AREA PROCESSING
# ============================================================

print("\nStarting area correction...")

updated_location_df, master_df = fix_incorrect_areas(
    updated_location_df,
    master_df,
)


# ============================================================
# SAVE FINAL UPDATED FILES
# ============================================================

print("\nSaving ONLY two output files...")

updated_location_df.to_csv(
    LOCATION_OUTPUT,
    index=False,
    encoding="utf-8",
)

master_df.to_csv(
    MASTER_OUTPUT,
    index=False,
    encoding="utf-8",
)

print("\n" + "=" * 60)
print("COMBINED PROCESSING COMPLETED")
print("=" * 60)
print("Created ONLY:")
print(LOCATION_OUTPUT)
print(MASTER_OUTPUT)
print("\nRaw files were NOT changed.")









  






















#   # ============================================================
# # FINAL COMBINED DATA MATCHING SUMMARY
# # ============================================================

# print("\n" + "=" * 75)
# print("FINAL CITY / STATE / REGION MATCHING SUMMARY")
# print("=" * 75)


# # ------------------------------------------------------------
# # TOTAL ROWS
# # ------------------------------------------------------------

# total_rows = len(master_df)

# print(f"\nTOTAL MASTER PRIORITY ROWS: {total_rows:,}")


# # ============================================================
# # CITY MATCH SUMMARY
# # ============================================================

# city_status_counts = (
#     master_df["location_match_status"]
#     .value_counts(dropna=False)
# )

# city_matched_statuses = [
#     "EXACT_CITY_STATE",
#     "EXACT_CITY",
#     "REUSED_CITY",
#     "SPELLING_MATCH",
#     "NEW_LOCATION"
# ]

# city_matched_rows = (
#     master_df["location_match_status"]
#     .isin(city_matched_statuses)
#     .sum()
# )

# city_not_found = (
#     master_df["location_match_status"]
#     == "NOT_FOUND"
# ).sum()

# blank_city = (
#     master_df["location_match_status"]
#     == "BLANK_CITY"
# ).sum()


# print("\n" + "-" * 75)
# print("CITY MATCHING")
# print("-" * 75)

# print(f"Total rows               : {total_rows:,}")
# print(f"City matched             : {city_matched_rows:,}")
# print(f"City not found           : {city_not_found:,}")
# print(f"Blank city               : {blank_city:,}")

# if total_rows > 0:
#     city_match_percentage = (
#         city_matched_rows / total_rows
#     ) * 100

#     print(
#         f"City match percentage    : "
#         f"{city_match_percentage:.2f}%"
#     )


# print("\nCity Match Breakdown:")

# for status in city_matched_statuses + [
#     "NOT_FOUND",
#     "BLANK_CITY"
# ]:

#     count = city_status_counts.get(status, 0)

#     print(
#         f"  {status:<25}: {count:,}"
#     )


# # ============================================================
# # STATE MATCH SUMMARY
# # ============================================================

# state_present_before = (
#     master_df["state"]
#     .notna()
#     .sum()
# )

# state_blank = (
#     master_df["state"]
#     .isna()
#     .sum()
# )


# print("\n" + "-" * 75)
# print("STATE DATA SUMMARY")
# print("-" * 75)

# print(f"Rows with state           : {state_present_before:,}")
# print(f"Rows without state        : {state_blank:,}")

# if total_rows > 0:

#     state_percentage = (
#         state_present_before / total_rows
#     ) * 100

#     print(
#         f"State availability        : "
#         f"{state_percentage:.2f}%"
#     )


# # ============================================================
# # REGION MATCH SUMMARY
# # ============================================================

# region_filled = (
#     master_df["region"]
#     .notna()
#     .sum()
# )

# region_missing = (
#     master_df["region"]
#     .isna()
#     .sum()
# )


# print("\n" + "-" * 75)
# print("REGION MATCHING")
# print("-" * 75)

# print(f"Region filled             : {region_filled:,}")
# print(f"Region missing            : {region_missing:,}")

# if total_rows > 0:

#     region_percentage = (
#         region_filled / total_rows
#     ) * 100

#     print(
#         f"Region match percentage  : "
#         f"{region_percentage:.2f}%"
#     )


# # ============================================================
# # LOCATION MASTER SUMMARY
# # ============================================================

# original_location_rows = len(location_df)

# final_location_rows = len(updated_location_df)

# new_locations_added = (
#     final_location_rows - original_location_rows
# )


# print("\n" + "-" * 75)
# print("LOCATION MASTER SUMMARY")
# print("-" * 75)

# print(
#     f"Original Location rows    : "
#     f"{original_location_rows:,}"
# )

# print(
#     f"Final Location rows       : "
#     f"{final_location_rows:,}"
# )

# print(
#     f"New Location rows added   : "
#     f"{new_locations_added:,}"
# )


# # ============================================================
# # FINAL OVERALL SUMMARY
# # ============================================================

# print("\n" + "=" * 75)
# print("FINAL OVERALL RESULT")
# print("=" * 75)

# print(
#     f"""
# Master Priority Total Rows : {total_rows:,}

# CITY
# ----
# Matched                   : {city_matched_rows:,}
# Not Found                 : {city_not_found:,}
# Match Rate                : {(city_matched_rows / total_rows * 100):.2f}%

# STATE
# -----
# Available                 : {state_present_before:,}
# Missing                   : {state_blank:,}
# Availability Rate         : {(state_present_before / total_rows * 100):.2f}%

# REGION
# ------
# Matched / Filled          : {region_filled:,}
# Missing                   : {region_missing:,}
# Match Rate                : {(region_filled / total_rows * 100):.2f}%

# LOCATION MASTER
# ---------------
# Original Rows             : {original_location_rows:,}
# Final Rows                : {final_location_rows:,}
# New Locations Added       : {new_locations_added:,}
# """
# )

# print("=" * 75)
# print("FINAL SUMMARY COMPLETED")
# print("=" * 75)