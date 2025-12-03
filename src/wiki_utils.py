import os
import requests

# 이미지를 저장할 기본 폴더
BASE_CACHE_DIR = "images/circuits"

# 위키피디아 API 차단 방지를 위한 헤더 (User-Agent 필수)
HEADERS = {
    'User-Agent': 'F1ArcadeReplay/1.0 (contact@example.com)'
}


def get_wiki_image_url(query):
    """
    위키피디아 API를 통해 검색어(query)에 해당하는 문서의 썸네일(대표 이미지) URL을 가져옵니다.
    F1 그랑프리 문서의 경우 대표 이미지는 대부분 서킷 레이아웃입니다.
    """
    base_url = "https://en.wikipedia.org/w/api.php"

    # pageimages 모듈을 사용하여 썸네일(pithumbsize)을 요청
    # pithumbsize: 600px 너비로 요청
    params = {
        "action": "query",
        "format": "json",
        "titles": query,
        "prop": "pageimages",
        "pithumbsize": 600
    }

    try:
        response = requests.get(base_url, params=params, headers=HEADERS, timeout=5)
        data = response.json()

        # 페이지 ID가 동적이므로 순회하며 찾음
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if "thumbnail" in page_data:
                return page_data["thumbnail"]["source"]
    except Exception as e:
        print(f"[Wiki API Error] 검색어 '{query}': {e}")

    return None


def download_image(url, save_path):
    """
    URL의 이미지를 다운로드하여 save_path에 저장합니다.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"[Download Error] {url}: {e}")
    return False


def fetch_circuit_image(year, event_name, callback=None):
    """
    메인 로직:
    1. images/circuits/{year} 폴더가 없으면 생성
    2. 파일명 생성 (예: 2025_Dutch_Grand_Prix_circuit.png)
    3. 이미 파일이 있으면 다운로드 스킵하고 callback 호출
    4. 없으면 위키피디아 검색 -> 다운로드 -> callback 호출
    """

    # 1. 연도별 폴더 경로 생성 (예: images/circuits/2025)
    year_dir = os.path.join(BASE_CACHE_DIR, str(year))
    if not os.path.exists(year_dir):
        try:
            os.makedirs(year_dir)
        except OSError as e:
            print(f"폴더 생성 실패: {e}")
            return

    # 2. 파일명 생성 (공백을 언더바(_)로 치환하고 뒤에 _circuit.png 붙임)
    # 예: "Dutch Grand Prix" -> "2025_Dutch_Grand_Prix_circuit.png"
    safe_event_name = event_name.replace(" ", "_")
    filename = f"{year}_{safe_event_name}_circuit.png"
    save_path = os.path.join(year_dir, filename)

    # 3. 이미 캐시된 파일이 있는지 확인
    if os.path.exists(save_path):
        if callback:
            callback(save_path)
        return

    # 4. 위키피디아 검색 쿼리 생성
    # 정확도를 위해 "2025 Dutch Grand Prix" 형태로 검색
    search_query = f"{year} {event_name}"

    print(f"[Wiki] 검색 시작: {search_query}...")
    img_url = get_wiki_image_url(search_query)

    # 만약 "2025 Dutch Grand Prix"로 이미지가 없으면,
    # 연도를 뺀 "Dutch Grand Prix"로 재시도 (오래된 시즌 대비)
    if not img_url:
        print(f"[Wiki] 연도 포함 검색 실패. '{event_name}'으로 재시도...")
        img_url = get_wiki_image_url(event_name)

    if img_url:
        print(f"[Wiki] 이미지 발견. 다운로드 중... -> {filename}")
        if download_image(img_url, save_path):
            if callback:
                callback(save_path)
    else:
        print(f"[Wiki] 이미지를 찾을 수 없습니다: {search_query}")