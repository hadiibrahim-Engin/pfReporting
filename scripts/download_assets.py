"""
Downloads vendor JS/CSS files and saves them to pfreporting/report/assets/.

Bundled files (Chart.js, Hammer.js, chartjs-plugin-zoom) go to assets/vendor/.
Optional CDN files (Alpine.js, Tailwind, jQuery, DataTables, ECharts) go to
assets/ and assets/datatables/ — these are used by the multi-page report format
for offline operation. The single-file format continues to use CDN links.

Run:
    uv run python scripts/download_assets.py
"""
import ssl
import urllib.request
import sys
from pathlib import Path

_ssl_ctx = ssl.create_default_context()
try:
    import certifi  # type: ignore
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE

_ASSETS_DIR = Path(__file__).parent.parent / "pfreporting" / "report" / "assets"

VENDOR_ASSETS = [
    (
        "vendor/chart.min.js",
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js",
    ),
    (
        "vendor/hammer.min.js",
        "https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js",
    ),
    (
        "vendor/chartjs-plugin-zoom.min.js",
        "https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js",
    ),
    (
        "vendor/echarts.min.js",
        "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js",
    ),
]

CDN_ASSETS = [
    (
        "alpine.min.js",
        "https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js",
    ),
    (
        "tailwind.min.js",
        "https://cdn.tailwindcss.com",
    ),
    (
        "datatables/jquery.min.js",
        "https://code.jquery.com/jquery-3.7.1.min.js",
    ),
    (
        "datatables/dataTables.min.js",
        "https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js",
    ),
    (
        "datatables/dataTables.tailwindcss.min.js",
        "https://cdn.datatables.net/1.13.8/js/dataTables.tailwindcss.min.js",
    ),
    (
        "datatables/dataTables.tailwindcss.min.css",
        "https://cdn.datatables.net/1.13.8/css/dataTables.tailwindcss.min.css",
    ),
]


def download(rel_path: str, url: str) -> None:
    dest = _ASSETS_DIR / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  [SKIP] {rel_path} - already present")
        return
    print(f"  [DOWN] {rel_path} …", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, context=_ssl_ctx) as resp:
            dest.write_bytes(resp.read())
        size_kb = dest.stat().st_size // 1024
        print(f"OK ({size_kb} KB)")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    print(f"Target directory: {_ASSETS_DIR}\n")
    print("--- Bundled vendor assets (Chart.js / Hammer / zoom / ECharts) ---")
    for rel_path, url in VENDOR_ASSETS:
        download(rel_path, url)

    print("\n--- Optional CDN assets (Alpine / Tailwind / jQuery / DataTables) ---")
    print("    These enable offline use with --format multi\n")
    for rel_path, url in CDN_ASSETS:
        download(rel_path, url)

    print("\nAll assets available.")


if __name__ == "__main__":
    main()
