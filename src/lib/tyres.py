def get_tyre_compounds(year):
  return {
    "SOFT": 0 if year != 2018 else 8,
    "MEDIUM": 1 if year != 2018 else 9,
    "HARD": 2 if year != 2018 else 10,
    "INTERMEDIATE": 3,
    "WET": 4,
    "HYPERSOFT": 5,
    "ULTRASOFT": 6,
    "SUPERSOFT": 7
  }

def get_tyre_compound_int(compound_str, year):
  tyre_compounds_ints = get_tyre_compounds(year)
  return int(tyre_compounds_ints.get(compound_str.upper(), -1))

def get_tyre_compound_str(compound_int, year):
  tyre_compounds_ints = get_tyre_compounds(year)
  for k, v in tyre_compounds_ints.items():
    if v == compound_int:
      return k
  return "UNKNOWN"