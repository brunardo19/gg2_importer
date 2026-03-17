from pathlib import Path

MOTS = [
    "BMOT.PKM", "IMOT.PKM", "DMOT.PKM", "SMOT.PKM", "NMOT.PKM",
    "EMOT.PKM", "IMMOT.PKM", "DMMOT.PKM", "SMMOT.PKM", "NMMOT.PKM",
    "EMMOT.PKM", "VMMOT.PKM", "KMMOT.PKM", "CMOT.PKM",
]

GG2_PATH = Path("C:/", "Program Files (x86)", "Steam", "steamapps", "common", "GG2")
LOADTABLE_PATH = Path(GG2_PATH, "loadtable.bin")
DATA_PATH = Path(GG2_PATH, "data")

# Global state to hold parsed entries between the Importer and the Selector UI
temp_entries = []