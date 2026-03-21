from pathlib import Path

MOTS = [
    "BMOT.PKM", "IMOT.PKM", "DMOT.PKM", "SMOT.PKM", "NMOT.PKM",
    "EMOT.PKM", "IMMOT.PKM", "DMMOT.PKM", "SMMOT.PKM", "NMMOT.PKM",
    "EMMOT.PKM", "VMMOT.PKM", "KMMOT.PKM", "CMOT.PKM",
]

DISPLAY_NAMES_1 = {
    "E" : "Valentine", #Elphelt?
    "S" : "Sol",
    "N" : "Sin",
    "D" : "Dr Paradigm",
    "V" : "Raven",
    "K" : "Ky",
    "I" : "Izuna"
}
DISPLAY_NAMES_2 = {
    "H" : "Master", #Hero?
    "M" : "Basic", #Minion?
    "A" : "Elite", #Advanced?
    "S" : "Special", #?
    "J" : "Alternative", #?
    "I" : "Special" #?
}
DISPLAY_NAMES_3 = {
    "M" : "Meele",
    "A" : "Armor",
    "S" : "Ranged", # Sniper/Shooter?
    "R" : "Mobile", # Raider?
    "G" : "Magic" # Gear?
}

GG2_PATH = Path("C:/", "Program Files (x86)", "Steam", "steamapps", "common", "GG2")
LOADTABLE_PATH = Path(GG2_PATH, "loadtable.bin")
DATA_PATH = Path(GG2_PATH, "data")

# Global state to hold parsed entries between the Importer and the Selector UI
temp_entries = []