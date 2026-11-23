import os, re
import requests

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_PAGE_TOKEN"]
G = "https://graph.facebook.com/v21.0"
LIMIT = int(os.environ.get("LIMIT", "100"))


def resolve_token():
    global TOKEN
    r = requests.get(f"{G}/me/accounts", params={"access_token": TOKEN, "limit": 100}, timeout=30).json()
    for p in r.get("data", []):
        if p.get("id") == PAGE_ID and p.get("access_token"):
            TOKEN = p["access_token"]
            print("OK: Page token niyechi")
            return
    print("Token already Page token ba me/accounts nei")


def clean(msg):
    lines = [l for l in msg.split("\n")
             if not re.match(r"^\s*📰", l) and not re.match(r"^\s*(বিস্তারিত|সূত্র)\s*[:：]", l)]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


resolve_token()
url = f"{G}/{PAGE_ID}/posts"
params = {"fields": "id,message", "limit": 25, "access_token": TOKEN}
seen = fixed = 0
while url and seen < LIMIT:
    r = requests.get(url, params=params, timeout=30).json()
    if "error" in r:
        print("ERROR:", r["error"].get("message"))
        break
    for p in r.get("data", []):
        seen += 1
        msg = p.get("message") or ""
        # shudhu bot er banano post: hashtag ache ar purono line ache
        if "#Star7News" in msg and ("বিস্তারিত" in msg or "সূত্র:" in msg):
            new = clean(msg)
            if new and new != msg:
                u = requests.post(f"{G}/{p['id']}", data={"message": new, "access_token": TOKEN}, timeout=30)
                print("EDIT", p["id"], u.status_code, u.text[:120])
                fixed += u.ok
    url = r.get("paging", {}).get("next")
    params = None
print(f"Dekha: {seen}, Edit hoyeche: {fixed}")
