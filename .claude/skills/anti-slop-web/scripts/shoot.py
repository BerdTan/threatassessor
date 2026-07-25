#!/usr/bin/env python3
import sys, os, argparse

VIEWPORTS = [("mobile", 390, 844), ("tablet", 768, 1024), ("desktop", 1440, 900)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--out", default=".shots")
    ap.add_argument("--wait", type=int, default=1200)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed. run:")
        print("  pip install playwright && playwright install chromium")
        return 2

    url = args.target
    if not url.startswith("http"):
        url = "file://" + os.path.abspath(url)

    os.makedirs(args.out, exist_ok=True)
    picked = [v for v in VIEWPORTS if not args.only or v[0] in args.only.split(",")]
    written = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, w, h in picked:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=2)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(args.wait)
            fold = os.path.join(args.out, "%s-fold.png" % name)
            page.screenshot(path=fold)
            written.append(fold)
            if name == "desktop":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(600)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(400)
                full = os.path.join(args.out, "desktop-full.png")
                page.screenshot(path=full, full_page=True)
                written.append(full)
            page.close()
        browser.close()

    for f in written:
        print(f)
    print("\nnow OPEN these images and look at them, then grade against")
    print("references/audit-rubric.md section B. Reading the source is not seeing the page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
