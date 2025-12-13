import os
import requests

# [FIX] Determine Project Root
CURRENT_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_SRC_DIR)

# Target: .../project/images/circuits
BASE_CACHE_DIR = os.path.join(PROJECT_ROOT, "images", "circuits")

# [CRITICAL] Headers to bypass Wikimedia 403 Forbidden
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://en.wikipedia.org/'
}


def get_wiki_image_url(search_query):
    """
    Use Wikipedia Search Generator to find the most relevant page
    and get its main image.
    """
    base_url = "https://en.wikipedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": search_query,
        "gsrlimit": 1,
        "prop": "pageimages",
        "pithumbsize": 1000
    }

    try:
        response = requests.get(base_url, params=params, headers=HEADERS, timeout=10)
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None

        for _, page_data in pages.items():
            if "thumbnail" in page_data:
                source = page_data["thumbnail"]["source"]
                print(f"[Wiki] Found URL for '{search_query}': {source}")
                return source

    except Exception as e:
        print(f"[Wiki Error] Search '{search_query}': {e}")
    return None


def download_image(url, save_path):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            print(f"[Wiki] SUCCESS: Saved to {save_path}")
            return True
        else:
            print(f"[Wiki] Download Status {response.status_code} for {url}")

    except Exception as e:
        print(f"[Wiki] Download Failed: {e}")
    return False


def fetch_circuit_image(year, event_name, callback=None):
    """
    Logic:
    1. Check Cache (File Exists?) -> If Yes, Callback & Return (SKIP DOWNLOAD)
    2. Search "Event + Circuit"
    3. Search "Event" (Fallback)
    4. Download
    """
    # 1. Create Directory
    year_dir = os.path.join(BASE_CACHE_DIR, str(year))
    if not os.path.exists(year_dir):
        try:
            os.makedirs(year_dir, exist_ok=True)
        except Exception as e:
            print(f"[Wiki] Dir Error: {e}")
            return

    # 2. Check Cache (이미지 필터)
    safe_name = event_name.replace(" ", "_")
    filename = f"{year}_{safe_name}_circuit.png"
    save_path = os.path.join(year_dir, filename)

    # [핵심] 파일이 존재하고 크기가 0보다 크면(정상 파일이면) 다운로드 건너뜀
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        print(f"[Wiki] Cache Hit (Skipping Download): {filename}")
        if callback:
            callback(save_path)
        return

    # 3. Search Wikipedia (Smart Search)
    url = None

    # Strategy 1: Search for "{Event} Circuit" (e.g., "Belgian Grand Prix Circuit")
    search_q1 = f"{event_name} Circuit"
    print(f"[Wiki] Downloading... Searching: {search_q1}")
    url = get_wiki_image_url(search_q1)

    # Strategy 2: Search for "{Year} {Event}"
    if not url:
        search_q2 = f"{year} {event_name}"
        print(f"[Wiki] Retry: {search_q2}")
        url = get_wiki_image_url(search_q2)

    # Strategy 3: Just Event Name
    if not url:
        print(f"[Wiki] Retry: {event_name}")
        url = get_wiki_image_url(event_name)

    # 4. Download
    if url:
        if download_image(url, save_path):
            if callback: callback(save_path)
    else:
        print(f"[Wiki] Failed to find image for {event_name}")