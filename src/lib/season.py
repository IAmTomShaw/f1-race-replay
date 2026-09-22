from datetime import datetime as date

def get_season():
    current_year_date = date.now()
    return current_year_date.year if (current_year_date.month >= 2) else (current_year_date.year-1)