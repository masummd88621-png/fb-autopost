import os, io, re, json, glob, html
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_PAGE_TOKEN"]
RSS_URL = os.environ["RSS_URL"]
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "3"))
FIRST_RUN_POSTS = 1
STATE = "posted.json"
TEMPLATE = "template.jpg"
SCALE = 1.2
GRAPH = f"https://graph.facebook.com/v21.0/{PAGE_ID}"
UA = {"User-Agent": "Mozilla/5.0"}

# ---- Caption template: nijer moto change koro ----
CAPTION = "{title}\n\n📰 বিস্তারিত: {link}\n\nসূত্র: {source}\n\n#Star7News #স্টার৭নিউজ"

SOURCES = {"prothomalo.com": "প্রথম আলো", "kalerkantho.com": "কালের কণ্ঠ"}


def source_name(link):
    host = urlparse(link).netloc.replace("www.", "")
    for k, v in SOURCES.items():
        if k in host:
            return v
    return host


# ---------------- RSS ----------------
def find_image(it, link):
    for el in it.iter():
        tag = el.tag.split("}")[-1]
        url = el.get("url")
        if tag in ("content", "thumbnail", "enclosure") and url:
            typ = (el.get("type") or el.get("medium") or "").lower()
            if "image" in typ or re.search(r"\.(jpe?g|png|webp)", url, re.I):
                return url
    blob = ET.tostring(it, encoding="unicode")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', blob.replace("&lt;", "<").replace("&quot;", '"'))
    if m:
        return m.group(1).replace("&amp;", "&")
    try:
        page = requests.get(link, headers=UA, timeout=30).text
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', page)
        if m:
            return m.group(1).replace("&amp;", "&")
    except Exception as e:
        print("og:image error:", e)
    return None


def parse_xml(raw):
    txt = raw.decode("utf-8", "replace").lstrip("\ufeff")
    txt = re.sub(r"^\s*<\?xml[^>]*\?>", "", txt)
    txt = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", txt)
    return ET.fromstring(txt.encode("utf-8"))


def fetch_items():
    items = []
    for url in RSS_URL.replace("\n", ",").split(","):
        url = url.strip()
        if not url:
            continue
        try:
            root = parse_xml(requests.get(url, headers=UA, timeout=30).content)
        except Exception as e:
            print("RSS error:", url, e)
            continue
        for it in root.iter("item"):
            title = html.unescape(it.findtext("title") or "").replace("\xa0", " ").strip()
            link = (it.findtext("link") or "").strip()
            if link:
                items.append({"title": title, "link": link, "_it": it})
    return items


# ---------------- Photocard ----------------
def find_font():
    for p in ["/usr/share/fonts/**/NotoSansBengali-Bold.ttf",
              "/usr/share/fonts/**/NotoSerifBengali-Bold.ttf",
              "/usr/share/fonts/**/NotoSansBengali*.ttf",
              "/usr/share/fonts/**/Lohit-Bengali.ttf",
              "/usr/share/fonts/**/FreeSans.ttf"]:
        f = glob.glob(p, recursive=True)
        if f:
            return f[0]
    raise RuntimeError("Bengali font pawa jayni")


def find_template():
    if os.path.exists(TEMPLATE):
        return TEMPLATE
    c = sorted(glob.glob("template*")) + sorted(glob.glob("*.jp*g")) + sorted(glob.glob("*.png"))
    if c:
        return c[0]
    raise RuntimeError("template.jpg repo te nei, upload koro")


def load_template():
    im = Image.open(find_template()).convert("RGB")
    im = im.resize((int(im.width * SCALE), int(im.height * SCALE)), Image.LANCZOS)
    a = np.array(im).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    gd = g - np.maximum(r, b)
    alpha = 255 - np.clip((gd - 25) * 255 / 75, 0, 255)
    a[..., 1] = np.where((gd > 0) & (alpha > 0), np.minimum(g, np.maximum(r, b)), g)
    rgba = np.dstack([a, alpha]).astype("uint8")
    ys, xs = np.where(alpha < 128)
    return Image.fromarray(rgba, "RGBA"), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x = (img.width - w) // 2
    y = int((img.height - h) * 0.35)
    return img.crop((x, y, x + w, y + h))


def wrap_fit(draw, text, fp, maxw, maxh, start=64, minsize=30):
    size = start
    while size >= minsize:
        font = ImageFont.truetype(fp, size)
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lh = int(size * 1.3)
        if len(lines) * lh <= maxh and len(lines) <= 5:
            return font, lines, lh
        size -= 2
    return ImageFont.truetype(fp, minsize), lines[:5], int(minsize * 1.3)


def make_card(photo_bytes, headline):
    tpl, (x0, y0, x1, y1) = load_template()
    W, H = tpl.size
    canvas = Image.new("RGB", (W, H), (10, 20, 40))
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    canvas.paste(cover(photo, x1 - x0, y1 - y0), (x0, y0))
    canvas.paste(tpl, (0, 0), tpl)
    d = ImageDraw.Draw(canvas)
    top = int(y1 + H * 0.06)
    area_h = H - top - int(H * 0.04)
    font, lines, lh = wrap_fit(d, headline, find_font(), W - 90, area_h)
    y = top + max(0, (area_h - len(lines) * lh) // 2)
    for ln in lines:
        d.text(((W - d.textlength(ln, font=font)) / 2, y), ln, font=font, fill="white")
        y += lh
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=92)
    return out.getvalue()


# ---------------- Facebook ----------------
def post(item):
    caption = CAPTION.format(title=item["title"], link=item["link"], source=source_name(item["link"]))
    try:
        img_url = find_image(item["_it"], item["link"])
        if img_url:
            photo = requests.get(img_url, headers=UA, timeout=30).content
            card = make_card(photo, item["title"])
            r = requests.post(f"{GRAPH}/photos",
                              data={"caption": caption, "access_token": TOKEN},
                              files={"source": ("card.jpg", card, "image/jpeg")}, timeout=60)
        else:
            print("Chhobi pawa jayni, link post korchi:", item["title"])
            r = requests.post(f"{GRAPH}/feed",
                              data={"message": caption, "link": item["link"], "access_token": TOKEN},
                              timeout=30)
        print("Response:", r.status_code, r.text[:300])
        return r.ok
    except Exception as e:
        print("FAILED:", item["title"], repr(e))
        return False


def main():
    print("raqm:", features.check("raqm"), "| font:", find_font())
    first_run = not os.path.exists(STATE)
    posted = set(json.load(open(STATE))) if not first_run else set()
    new = [i for i in fetch_items() if i["link"] not in posted]
    if first_run:
        to_post = new[:FIRST_RUN_POSTS]
        posted.update(i["link"] for i in new)
    else:
        to_post = list(reversed(new))[:MAX_PER_RUN]
    for it in to_post:
        if post(it):
            posted.add(it["link"])
            print("Posted:", it["title"])
        else:
            posted.discard(it["link"])
    json.dump(sorted(posted), open(STATE, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
