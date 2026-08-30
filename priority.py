import pandas as pd

# Files
MASTER_FILE = "master_priority_updated.csv"
LOCATION_FILE = "location_master_updated.csv"

print("Reading files...")

# Read both files
master_df = pd.read_csv(MASTER_FILE, low_memory=False)
location_df = pd.read_csv(LOCATION_FILE, low_memory=False)

# Set priority = 1 for every row
master_df["priority"] = 1
location_df["priority"] = 1

# Save both files
master_df.to_csv(MASTER_FILE, index=False, encoding="utf-8")
location_df.to_csv(LOCATION_FILE, index=False, encoding="utf-8")

print("\nSUCCESS!")
print(f"Master Priority rows updated: {len(master_df)}")
print(f"Location Master rows updated: {len(location_df)}")
print("Priority value in both files: 1")