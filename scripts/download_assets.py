"""
Downloads Chart.js vendor files and saves them to
pfreporting/report/assets/vendor/.

Run:
    uv run python scripts/download_assets.py
"""
import ssl
import urllib.request
import sys
from pathlib import Path

# macOS ships without default CA bundle; create an unverified context as fallback
_ssl_ctx = ssl.create_default_context()
try:
    import certifi  # type: ignore
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE

VENDOR_DIR = Path(__file__).parent.parent / "pfreporting" / "report" / "assets" / "vendor"

ASSETS = [
    (
        "chart.min.js",
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js",
    ),
    (
        "hammer.min.js",
        "https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js",
    ),
    (
        "chartjs-plugin-zoom.min.js",
        "https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js",
    ),
]


def download(filename: str, url: str) -> None:
    dest = VENDOR_DIR / filename
    if dest.exists():
        print(f"  [SKIP] {filename} - already present")
        return
    print(f"  [DOWN] {filename} …", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, context=_ssl_ctx) as resp:
            dest.write_bytes(resp.read())
        size_kb = dest.stat().st_size // 1024
        print(f"OK ({size_kb} KB)")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Target directory: {VENDOR_DIR}\n")
    for filename, url in ASSETS:
        download(filename, url)
    print("\nAll vendor assets available.")


if __name__ == "__main__":
    main()
