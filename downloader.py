import os
import re
import json
import time
import uuid
import html
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, Dict, Any, Tuple

import requests
from requests.adapters import HTTPAdapter
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


URL_REGEX = re.compile(r'(https?://[^\s<>"\'`]+)')

PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Mobile/15E148 Safari/604.1"
)


def create_high_speed_session(pool_size: int = 64) -> requests.Session:
    """
    Creates a persistent HTTP session with massive connection pooling, keep-alive,
    and zero SSL verification overhead for maximum throughput.
    """
    sess = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=2,
        pool_block=False,
    )
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.headers.update(
        {
            "User-Agent": PC_UA,
            "Referer": "https://www.kuaishou.com/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
    )
    return sess


GLOBAL_CDN_SESSION = create_high_speed_session(128)


def extract_urls(raw_text: str) -> List[str]:
    """
    Extracts all valid URLs from raw text (supports Kuaishou share text with captions).
    Deduplicates while preserving order.
    """
    seen = set()
    urls = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        matches = URL_REGEX.findall(line)
        for url in matches:
            clean_url = url.rstrip(',.;!?)]}"\'')
            if clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)
    return urls


def sanitize_filename(name: str, max_len: int = 75) -> str:
    """Cleans a string so it is safe for Windows/macOS/Linux filenames."""
    if not name:
        return "kuaishou_video"
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]+', "_", name).strip(" ._")
    if len(clean) > max_len:
        clean = clean[:max_len].strip(" ._")
    return clean or "kuaishou_video"


class DownloadTask:
    def __init__(self, task_id: int, url: str):
        self.task_id = task_id
        self.url = url
        self.title: str = url
        self.video_id: str = f"ks_{task_id}_{int(time.time())}"
        self.engine_used: str = "Turbo Ready"
        self.status: str = "រង់ចាំ (Queued)"
        self.progress: float = 0.0
        self.speed_str: str = "-"
        self.size_str: str = "-"
        self.eta_str: str = "-"
        self.filepath: Optional[str] = None
        self.error: Optional[str] = None
        self.cancelled: bool = False


class KuaishouParallelResolver:
    """
    Ultra-Fast Parallel Racing Resolver for Kuaishou Links.
    Instead of waiting sequentially for each method to fail, it races multiple
    resolution channels concurrently and returns the FIRST valid MP4 URL in < 1 second!
    """

    def __init__(self, custom_cookie: str = ""):
        self.custom_cookie = custom_cookie.strip()
        self._fast_session = create_high_speed_session(64)
        self._did = f"web_{uuid.uuid4().hex[:16]}"
        self._fast_session.cookies.set("did", self._did, domain=".kuaishou.com")
        self._fast_session.cookies.set("didv", str(int(time.time() * 1000)), domain=".kuaishou.com")
        self._fast_session.cookies.set("kpf", "PC_WEB", domain=".kuaishou.com")
        self._fast_session.cookies.set("kpn", "KUAISHOU_VISION", domain=".kuaishou.com")

    @staticmethod
    def _unescape_url(raw_url: str) -> str:
        if not raw_url:
            return ""
        u = raw_url.strip()
        u = (
            u.replace("\\u002F", "/")
            .replace("\\u0026", "&")
            .replace("\\/", "/")
        )
        u = html.unescape(u)
        if u.startswith("//"):
            u = "https:" + u
        return u

    @staticmethod
    def _extract_photo_id(url: str) -> Optional[str]:
        patterns = [
            r"/short-video/([A-Za-z0-9_-]+)",
            r"/fw/photo/([A-Za-z0-9_-]+)",
            r"/photo/([A-Za-z0-9_-]+)",
            r"[?&]photoId=([A-Za-z0-9_-]+)",
            r"/f/([A-Za-z0-9_-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return None

    def _parse_html_for_video(self, page_html: str) -> Optional[Tuple[str, str]]:
        if not page_html:
            return None

        norm = (
            page_html.replace("\\u002F", "/")
            .replace("\\u0026", "&")
            .replace("\\/", "/")
        )

        title = "Kuaishou_Video"
        for t_pat in [
            r'"caption"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r'"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r"<title[^>]*>(.*?)</title>",
        ]:
            tm = re.search(t_pat, page_html, re.DOTALL)
            if tm:
                raw_t = tm.group(1).strip()
                try:
                    raw_t = json.loads(f'"{raw_t}"')
                except Exception:
                    pass
                raw_t = re.sub(r"\s*-\s*快手.*$", "", raw_t).strip()
                if raw_t and raw_t not in ("快手", "Kuaishou", "驗證碼"):
                    title = raw_t
                    break

        url_patterns = [
            r'"srcNoMark"\s*:\s*"(https?://[^"]+)"',
            r'"photoUrl"\s*:\s*"(https?://[^"]+)"',
            r'"mainMvUrls"\s*:\s*\[\s*\{[^\}]*?"url"\s*:\s*"(https?://[^"]+)"',
            r'"representation"\s*:\s*\[\s*\{[^\}]*?"url"\s*:\s*"(https?://[^"]+)"',
            r'"H265Url"\s*:\s*"(https?://[^"]+)"',
            r'"h264Urls"\s*:\s*\[\s*\{[^\}]*?"url"\s*:\s*"(https?://[^"]+)"',
            r'"mp4Url"\s*:\s*"(https?://[^"]+)"',
            r'<meta[^>]+property=["\']og:video(?::url)?["\'][^>]+content=["\'](https?://[^"\']+)["\']',
            r'<video[^>]+src=["\'](https?://[^"\']+)["\']',
            r'(https?://[a-zA-Z0-9._-]+\.(?:kwaicdn\.com|kwimgs\.com|yximgs\.com)/[^"\'\s<>\\]+\.mp4[^"\'\s<>\\]*)',
        ]

        for pat in url_patterns:
            m = re.search(pat, norm)
            if m:
                candidate = self._unescape_url(m.group(1))
                if candidate.startswith("http") and ".m3u8" not in candidate:
                    return candidate, title

        return None

    def _quick_resolve_redirect(self, url: str) -> Tuple[str, Optional[str], Optional[Tuple[str, str]]]:
        """
        Ultra-fast initial redirect check (timeout 4s) to grab photoId and check if HTML already has the MP4.
        """
        photo_id = self._extract_photo_id(url)
        headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.kuaishou.com/"}
        if self.custom_cookie:
            headers["Cookie"] = self.custom_cookie

        try:
            r = self._fast_session.get(url, headers=headers, allow_redirects=True, timeout=4.5, verify=False)
            final_url = str(r.url)
            if not photo_id:
                photo_id = self._extract_photo_id(final_url)
            parsed = self._parse_html_for_video(r.text)
            return final_url, photo_id, parsed
        except Exception:
            return url, photo_id, None

    def _worker_cloud_api(self, api_cfg: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
        try:
            resp = self._fast_session.get(
                api_cfg["url"], headers=api_cfg["headers"], timeout=5.5, verify=False
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            video_url = (
                payload.get("url")
                or payload.get("video_url")
                or payload.get("videoUrl")
                or payload.get("no_watermark_video_url")
                or payload.get("playAddr")
                or payload.get("srcNoMark")
                or payload.get("mp4")
                or payload.get("video")
            )
            if isinstance(video_url, str) and video_url.startswith("http"):
                title = (
                    payload.get("title")
                    or payload.get("desc")
                    or payload.get("caption")
                    or "Kuaishou_Video"
                )
                return self._unescape_url(video_url), str(title), api_cfg["name"]
        except Exception:
            pass
        return None

    def _worker_pc_apollo(self, target_url: str) -> Optional[Tuple[str, str, str]]:
        try:
            headers = {"User-Agent": PC_UA, "Referer": "https://www.kuaishou.com/"}
            if self.custom_cookie:
                headers["Cookie"] = self.custom_cookie
            if HAS_CFFI:
                r = cffi_requests.get(target_url, headers=headers, impersonate="chrome120", timeout=5.5)
            else:
                r = self._fast_session.get(target_url, headers=headers, timeout=5.5, verify=False)
            parsed = self._parse_html_for_video(r.text)
            if parsed:
                return parsed[0], parsed[1], "PC Apollo Turbo"
        except Exception:
            pass
        return None

    def _worker_mobile_h5(self, photo_id: str) -> Optional[Tuple[str, str, str]]:
        if not photo_id:
            return None
        try:
            headers = {
                "User-Agent": MOBILE_UA,
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": "https://c.kuaishou.com",
                "Referer": f"https://c.kuaishou.com/fw/photo/{photo_id}",
            }
            if self.custom_cookie:
                headers["Cookie"] = self.custom_cookie
            payload = {"photoId": photo_id, "isLongVideo": False}
            for host in ["https://c.kuaishou.com", "https://v.m.chenzhongtech.com"]:
                api_url = f"{host}/rest/wd/ugH5App/photo/simple/info"
                resp = self._fast_session.post(api_url, json=payload, headers=headers, timeout=5.0, verify=False)
                if resp.status_code == 200:
                    parsed = self._parse_html_for_video(resp.text)
                    if parsed:
                        return parsed[0], parsed[1], "Mobile H5 Turbo"
        except Exception:
            pass
        return None

    def _worker_graphql(self, photo_id: str) -> Optional[Tuple[str, str, str]]:
        if not photo_id:
            return None
        try:
            gql_payload = {
                "operationName": "visionVideoDetail",
                "variables": {"photoId": photo_id, "page": "detail"},
                "query": (
                    "query visionVideoDetail($photoId: String, $type: String, $page: String, $webPageArea: String) { "
                    "visionVideoDetail(photoId: $photoId, type: $type, page: $page, webPageArea: $webPageArea) { "
                    "status type photo { id duration caption coverUrl photoUrl H265Url "
                    "manifest { adaptationSet { representation { url backupUrl qualityLabel } } } } } }"
                ),
            }
            headers = {
                "User-Agent": PC_UA,
                "Content-Type": "application/json",
                "Origin": "https://www.kuaishou.com",
                "Referer": f"https://www.kuaishou.com/short-video/{photo_id}",
            }
            if self.custom_cookie:
                headers["Cookie"] = self.custom_cookie
            resp = self._fast_session.post(
                "https://www.kuaishou.com/graphql",
                json=gql_payload,
                headers=headers,
                timeout=5.5,
                verify=False,
            )
            if resp.status_code == 200:
                j = resp.json()
                photo = j.get("data", {}).get("visionVideoDetail", {}).get("photo", {})
                if photo:
                    title = photo.get("caption") or f"Kuaishou_{photo_id}"
                    v_url = photo.get("photoUrl") or photo.get("H265Url")
                    if not v_url:
                        adapts = photo.get("manifest", {}).get("adaptationSet", [])
                        if adapts and adapts[0].get("representation"):
                            v_url = adapts[0]["representation"][0].get("url")
                    if v_url:
                        return self._unescape_url(v_url), str(title), "GraphQL Turbo"
        except Exception:
            pass
        return None

    def resolve_fast(self, url: str) -> Tuple[Optional[str], str, Optional[str], str]:
        """
        Fires all resolution engines in parallel (First-Wins Race) so resolution finishes in < 1 second!
        """
        # 1. Quick redirect & mobile check + parallel cloud race
        encoded_raw = urllib.parse.quote(url, safe="")
        cloud_apis = [
            {
                "name": "BugPK Turbo",
                "url": f"https://api.bugpk.com/api/kuaishou?url={encoded_raw}",
                "headers": {
                    "User-Agent": PC_UA,
                    "Referer": "https://api.bugpk.com/doc-kuaishou.html",
                    "X-Requested-With": "XMLHttpRequest",
                },
            },
            {
                "name": "PearkTrue Turbo",
                "url": f"https://api.pearktrue.cn/api/video/kuaishou/?url={encoded_raw}",
                "headers": {"User-Agent": PC_UA},
            },
            {
                "name": "TenAPI Turbo",
                "url": f"https://tenapi.cn/v2/video?url={encoded_raw}",
                "headers": {"User-Agent": PC_UA},
            },
            {
                "name": "Yujn Turbo",
                "url": f"https://api.yujn.cn/api/ks.php?url={encoded_raw}",
                "headers": {"User-Agent": PC_UA},
            },
        ]

        photo_id = self._extract_photo_id(url)
        resolved_url = url

        # Launch a parallel race across redirect + cloud APIs + PC scrape simultaneously!
        with ThreadPoolExecutor(max_workers=7) as race_pool:
            futures = []
            redirect_future = race_pool.submit(self._quick_resolve_redirect, url)
            futures.append(redirect_future)

            for api_cfg in cloud_apis:
                futures.append(race_pool.submit(self._worker_cloud_api, api_cfg))

            futures.append(race_pool.submit(self._worker_pc_apollo, url))
            if photo_id:
                futures.append(race_pool.submit(self._worker_graphql, photo_id))
                futures.append(race_pool.submit(self._worker_mobile_h5, photo_id))

            for fut in as_completed(futures):
                try:
                    res = fut.result()
                    if not res:
                        continue
                    # Check if this is the redirect_future tuple (final_url, pid, parsed)
                    if fut == redirect_future:
                        resolved_url, pid, parsed = res
                        if pid and not photo_id:
                            photo_id = pid
                        if parsed:
                            return parsed[0], parsed[1], photo_id, "Mobile Direct Turbo"
                    else:
                        # Worker returned (video_url, title, engine_name)
                        v_url, title, eng = res
                        if v_url:
                            return v_url, title, photo_id, eng
                except Exception:
                    continue

        # Secondary race if photo_id was newly discovered from redirect
        if photo_id:
            with ThreadPoolExecutor(max_workers=3) as pool2:
                futs2 = [
                    pool2.submit(self._worker_graphql, photo_id),
                    pool2.submit(self._worker_mobile_h5, photo_id),
                    pool2.submit(self._worker_pc_apollo, f"https://www.kuaishou.com/short-video/{photo_id}"),
                ]
                for fut in as_completed(futs2):
                    try:
                        res = fut.result()
                        if res and res[0]:
                            return res[0], res[1], photo_id, res[2]
                    except Exception:
                        continue

        return None, "Kuaishou_Video", photo_id, "Unresolved"


class KuaishouBatchDownloader:
    """
    IDM-Style Ultra-Sonic Multi-Connection Downloader Engine.
    Splits each video into up to 16 parallel HTTP Range byte streams while downloading
    multiple videos concurrently, multiplying download speed by 8x–16x!
    """

    def __init__(
        self,
        output_dir: str,
        max_workers: int = 6,
        idm_channels: int = 8,
        custom_cookie: str = "",
        on_update: Optional[Callable[[DownloadTask], None]] = None,
        on_all_complete: Optional[Callable[[], None]] = None,
    ):
        self.output_dir = output_dir
        self.max_workers = max(1, min(16, max_workers))
        self.idm_channels = max(1, min(16, idm_channels))
        self.custom_cookie = custom_cookie
        self.on_update = on_update
        self.on_all_complete = on_all_complete

        self._stop_event = threading.Event()
        self._active_tasks: List[DownloadTask] = []
        self.resolver = KuaishouParallelResolver(custom_cookie=custom_cookie)

    def start_batch(self, tasks: List[DownloadTask]) -> None:
        self._stop_event.clear()
        self._active_tasks = tasks
        os.makedirs(self.output_dir, exist_ok=True)

        def _coordinator():
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(self._process_task, task) for task in tasks]
                for f in futures:
                    try:
                        f.result()
                    except Exception:
                        pass
            if self.on_all_complete:
                self.on_all_complete()

        threading.Thread(target=_coordinator, daemon=True).start()

    def stop_all(self) -> None:
        self._stop_event.set()
        for t in self._active_tasks:
            t.cancelled = True

    def _notify(self, task: DownloadTask) -> None:
        if self.on_update:
            self.on_update(task)

    def _probe_file_size_and_range(self, video_url: str, headers: Dict[str, str]) -> Tuple[int, bool]:
        """
        Probes CDN with a 1-byte Range GET to immediately get total file size and verify
        HTTP 206 Partial Content support for IDM multi-channel splitting.
        """
        probe_headers = dict(headers)
        probe_headers["Range"] = "bytes=0-0"
        try:
            with GLOBAL_CDN_SESSION.get(
                video_url, headers=probe_headers, stream=True, timeout=8, verify=False
            ) as r:
                if r.status_code == 206:
                    cr = r.headers.get("Content-Range", "")
                    # Format: bytes 0-0/12345678
                    if "/" in cr:
                        total_str = cr.split("/")[-1].strip()
                        if total_str.isdigit():
                            return int(total_str), True
                elif r.status_code == 200:
                    cl = int(r.headers.get("Content-Length", 0))
                    accept_ranges = r.headers.get("Accept-Ranges", "").lower() == "bytes"
                    return cl, accept_ranges
        except Exception:
            pass
        return 0, False

    def _download_idm_multichannel(self, task: DownloadTask, video_url: str, target_path: str) -> bool:
        """
        IDM-Style Multi-Channel Segmented Downloader.
        Splits the video into `self.idm_channels` concurrent byte-range chunks (e.g., 8 or 12 channels)
        and writes them in parallel using pre-allocated file offsets + 512 KB high-speed buffers!
        """
        headers = {
            "User-Agent": PC_UA,
            "Referer": "https://www.kuaishou.com/",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        temp_path = target_path + ".part"

        total_bytes, supports_range = self._probe_file_size_and_range(video_url, headers)

        # Use multi-channel Range splitting if file > 512 KB and supports HTTP 206 Range
        if supports_range and total_bytes > 524288 and self.idm_channels > 1:
            num_parts = min(self.idm_channels, max(2, total_bytes // (512 * 1024)))
            task.engine_used = f"{task.engine_used} • {num_parts}x IDM"
            self._notify(task)

            try:
                # Pre-allocate file on disk
                with open(temp_path, "wb") as f:
                    f.truncate(total_bytes)

                part_size = total_bytes // num_parts
                ranges = []
                for i in range(num_parts):
                    start_b = i * part_size
                    end_b = (total_bytes - 1) if (i == num_parts - 1) else ((i + 1) * part_size - 1)
                    ranges.append((i, start_b, end_b))

                downloaded_lock = threading.Lock()
                shared_state = {"downloaded": 0, "last_notify": 0.0, "start_t": time.time()}

                def _download_part(part_info: Tuple[int, int, int]) -> bool:
                    _, start_b, end_b = part_info
                    cur_pos = start_b
                    for attempt in range(3):
                        if self._stop_event.is_set() or task.cancelled:
                            return False
                        if cur_pos > end_b:
                            return True
                        p_headers = dict(headers)
                        p_headers["Range"] = f"bytes={cur_pos}-{end_b}"
                        try:
                            with GLOBAL_CDN_SESSION.get(
                                video_url, headers=p_headers, stream=True, timeout=15, verify=False
                            ) as resp:
                                if resp.status_code not in (200, 206):
                                    continue
                                with open(temp_path, "r+b") as f_part:
                                    f_part.seek(cur_pos)
                                    for chunk in resp.iter_content(chunk_size=524288):  # 512 KB buffer
                                        if self._stop_event.is_set() or task.cancelled:
                                            return False
                                        if not chunk:
                                            continue
                                        f_part.write(chunk)
                                        c_len = len(chunk)
                                        cur_pos += c_len

                                        with downloaded_lock:
                                            shared_state["downloaded"] += c_len
                                            dl_now = shared_state["downloaded"]
                                            now = time.time()
                                            if now - shared_state["last_notify"] >= 0.06 or dl_now >= total_bytes:
                                                elapsed = max(0.001, now - shared_state["start_t"])
                                                spd = dl_now / elapsed
                                                task.speed_str = f"{spd / (1024 * 1024):.2f} MB/s"
                                                task.progress = min(0.99, dl_now / total_bytes)
                                                rem = max(0, total_bytes - dl_now)
                                                eta = int(rem / spd) if spd > 0 else 0
                                                task.eta_str = f"{eta}s"
                                                task.size_str = (
                                                    f"{dl_now / (1024 * 1024):.1f} / "
                                                    f"{total_bytes / (1024 * 1024):.1f} MB"
                                                )
                                                task.status = f"⚡ កំពុងទាញយកលឿន ({int(task.progress * 100)}%)"
                                                self._notify(task)
                                                shared_state["last_notify"] = now
                            if cur_pos > end_b:
                                return True
                        except Exception:
                            time.sleep(0.2)
                    return cur_pos > end_b

                with ThreadPoolExecutor(max_workers=num_parts) as part_pool:
                    part_results = list(part_pool.map(_download_part, ranges))

                if all(part_results) and os.path.exists(temp_path) and os.path.getsize(temp_path) >= total_bytes:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.replace(temp_path, target_path)
                    task.filepath = target_path
                    return True
            except Exception as e:
                task.error = str(e)

        # Fallback: High-Speed 1MB-Buffer Single Stream
        for attempt in range(3):
            if self._stop_event.is_set() or task.cancelled:
                return False
            try:
                with GLOBAL_CDN_SESSION.get(
                    video_url, headers=headers, stream=True, timeout=20, verify=False
                ) as resp:
                    resp.raise_for_status()
                    total_bytes = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    start_t = time.time()
                    last_notify = 0.0

                    with open(temp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1048576):  # 1 MB turbo buffer
                            if self._stop_event.is_set() or task.cancelled:
                                raise InterruptedError("Cancelled")
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if now - last_notify >= 0.06 or (total_bytes and downloaded >= total_bytes):
                                elapsed = max(0.001, now - start_t)
                                speed = downloaded / elapsed
                                task.speed_str = f"{speed / (1024 * 1024):.2f} MB/s"

                                if total_bytes > 0:
                                    task.progress = min(0.99, downloaded / total_bytes)
                                    rem = max(0, total_bytes - downloaded)
                                    eta = int(rem / speed) if speed > 0 else 0
                                    task.eta_str = f"{eta}s"
                                    task.size_str = (
                                        f"{downloaded / (1024 * 1024):.1f} / "
                                        f"{total_bytes / (1024 * 1024):.1f} MB"
                                    )
                                else:
                                    task.progress = min(0.95, task.progress + 0.05)
                                    task.size_str = f"{downloaded / (1024 * 1024):.1f} MB"
                                    task.eta_str = "-"

                                task.status = f"⚡ កំពុងទាញយក ({int(task.progress * 100)}%)"
                                self._notify(task)
                                last_notify = now

                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.replace(temp_path, target_path)
                    task.filepath = target_path
                    return True
            except InterruptedError:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return False
            except Exception as e:
                task.error = str(e)
                time.sleep(0.3)

        return False

    def _process_task(self, task: DownloadTask) -> None:
        if self._stop_event.is_set() or task.cancelled:
            task.status = "បានបោះបង់ (Cancelled)"
            self._notify(task)
            return

        task.error = None
        task.progress = 0.05
        task.status = "⚡ កំពុងបំបែក Link ល្បឿនលឿន..."
        self._notify(task)

        video_url, title, photo_id, engine_name = self.resolver.resolve_fast(task.url)

        if self._stop_event.is_set() or task.cancelled:
            task.status = "បានបោះបង់ (Cancelled)"
            self._notify(task)
            return

        if video_url:
            task.engine_used = engine_name
            clean_title = sanitize_filename(title)
            short_id = photo_id[:10] if photo_id else f"ks{task.task_id}"
            filename = f"{clean_title} [{short_id}].mp4"
            target_path = os.path.join(self.output_dir, filename)

            task.title = f"{clean_title} ({short_id})"
            task.progress = 0.10
            task.status = "⚡ កំពុងទាញយកតាមប្រព័ន្ធ IDM Turbo..."
            self._notify(task)

            ok = self._download_idm_multichannel(task, video_url, target_path)
            if ok:
                task.progress = 1.0
                task.eta_str = "0s"
                task.status = "ជោគជ័យ 100% (Completed)"
                self._notify(task)
                return

        if self._stop_event.is_set() or task.cancelled:
            task.status = "បានបោះបង់ (Cancelled)"
        else:
            task.status = "បរាជ័យ (Failed - សូមចុច Retry)"
            if not task.error:
                task.error = "Link ទាមទារ Cookie ឬត្រូវបានបិទ"
        self._notify(task)
