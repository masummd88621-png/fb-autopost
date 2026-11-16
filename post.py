import os, json
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_PAGE_TOKEN"]
RSS_URL = os.environ["RSS_URL"]
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "3"))
STATE = "posted.json"
API = f"https://graph.facebook.com/v21.0/{PAGE_ID}/feed"


def fetch_items():
    items = []
    for url in RSS_URL.replace("\n", ",").split(","):
        url = url.strip()
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            print("RSS error:", url, e)
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if link:
                items.append({"title": title, "link": link})
    return items


def post(item):
    data = urllib.parse.urlencode({
        "message": item["title"],
        "link": item["link"],
        "access_token": TOKEN,
    }).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(API, data=data), timeout=30)
        print("Posted:", item["title"], r.read().decode())
        return True
    except Exception as e:
        body = getattr(e, "read", lambda: b"")().decode()
        print("FAILED:", item["title"], e, body)
        return False


def main():
    first_run = not os.path.exists(STATE)
    posted = set(json.load(open(STATE))) if not first_run else set()
    items = fetch_items()
    new = [i for i in items if i["link"] not in posted]

    if first_run:
        to_post = new[:2]
        posted.update(i["link"] for i in new)
    else:
        to_post = list(reversed(new))[:MAX_PER_RUN]

    for it in to_post:
        if post(it):
            posted.add(it["link"])
        elif not first_run:
            posted.discard(it["link"])

    json.dump(sorted(posted), open(STATE, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
