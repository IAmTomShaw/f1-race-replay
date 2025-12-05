

# convert time in seconds to a MM:SS.sss format

def format_time(seconds: float) -> str:
  if seconds is None or seconds < 0:
    return "N/A"
  minutes = int(seconds // 60)
  secs = seconds % 60
  return f"{minutes:02}:{secs:06.3f}"
