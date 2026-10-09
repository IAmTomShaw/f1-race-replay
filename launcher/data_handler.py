import fastf1
import pandas as pd
from datetime import timedelta

class SeasonSchedule:
    def __init__(self):
        # Static mapping of F1 Countries/Locations to Emoji Flags
        self.country_flags = {
            'Bahrain': '🇧🇭',
            'Saudi Arabia': '🇸🇦',
            'Australia': '🇦🇺',
            'Japan': '🇯🇵',
            'China': '🇨🇳',
            'USA': '🇺🇸',
            'United States': '🇺🇸',
            'Miami': '🇺🇸',
            'Italy': '🇮🇹',
            'Monaco': '🇲🇨',
            'Spain': '🇪🇸',
            'Canada': '🇨🇦',
            'Austria': '🇦🇹',
            'Great Britain': '🇬🇧',
            'UK': '🇬🇧',
            'Hungary': '🇭🇺',
            'Belgium': '🇧🇪',
            'Netherlands': '🇳🇱',
            'Azerbaijan': '🇦🇿',
            'Singapore': '🇸🇬',
            'Mexico': '🇲🇽',
            'Brazil': '🇧🇷',
            'Las Vegas': '🇺🇸',
            'Qatar': '🇶🇦',
            'Abu Dhabi': '🇦🇪',
            'UAE': '🇦🇪',
            'Portugal': '🇵🇹',
            'Turkey': '🇹🇷',
            'Russia': '🇷🇺',
            'France': '🇫🇷',
            'Germany': '🇩🇪',
            'Emilia Romagna': '🇮🇹', 
        }

    def get_flag(self, country):
        return self.country_flags.get(country, '🏳️') # Default white flag if not found

    def get_schedule(self, year):
        """
        Fetches the event schedule for a given year using fastf1.
        Returns a cleaned list of dictionaries with specific fields.
        """
        try:
            # fastf1.get_event_schedule returns a pandas DataFrame
            schedule = fastf1.get_event_schedule(year)
            
            cleaned_schedule = []
            
            for index, row in schedule.iterrows():
                # Filter out testing sessions (RoundNumber 0)
                if row['RoundNumber'] == 0:
                    continue
                
                # Calculate weekend range (EventDate is Race Day/Day 3)
                event_date = row['EventDate']
                start_date = event_date - timedelta(days=2)
                
                # Format date string based on whether month changes
                if start_date.month == event_date.month:
                    formatted_date = f"🏁 {start_date.strftime('%d')}-{event_date.strftime('%d %b')}"
                else:
                    formatted_date = f"🏁 {start_date.strftime('%d %b')} - {event_date.strftime('%d %b')}"
                
                country = row['Country']
                flag = self.get_flag(country)
                
                event_data = {
                    'RoundNumber': row['RoundNumber'],
                    'Country': country,
                    'EventDate': formatted_date,
                    'Location': row['Location'],
                    'OfficialName': row['EventName'],
                    'Flag': flag,
                    'EventFormat': row['EventFormat']
                }
                cleaned_schedule.append(event_data)
                
            return cleaned_schedule
            
        except Exception as e:
            # Basic error handling for network or other issues
            print(f"Error fetching schedule for {year}: {e}")
            return []
