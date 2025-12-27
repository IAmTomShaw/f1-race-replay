import fastf1
import argparse
from settings import enable_cache, schedule_cache

enable_cache()

# Force use of --year flag to get schedule for the year
parser = argparse.ArgumentParser()
parser.add_argument("--year", type=int, required=True)
args = parser.parse_args()

schedule_df = fastf1.get_event_schedule(args.year, include_testing=False)

# Filter out unnecessary columns
filtered_schedule_df = schedule_df[
    ['RoundNumber', 'Country', 'Location', 'OfficialEventName']
]

# Create JSON
schedule_json = filtered_schedule_df.to_dict(orient='records')
schedule_cache(args.year, schedule_json)

print(f"Schedule for {args.year} cached successfully.")