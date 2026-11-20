import os, json, time, urllib.request, urllib.parse

IG_ID = os.environ["IG_ID"]
TOKEN = os.environ["IG_TOKEN"]
TG = os.environ.get("TG_TOKEN", "")
REPO = os.environ["GITHUB_REPOSITORY"]
PHOTOS, STATE = "photos", "state.json"
API = "https://graph.facebook.com/v21.0"

state = json.load(open(STATE)) if os.path.exists(STATE) else {}
state.setdefault("posted", []); state.setdefault("tg_offset", 0)

# 1) Pull new photos sent to the Telegram channel
if TG:
    tg = f"https://api.telegram.org/bot{TG}"
    upd = json.loads(urllib.request.urlopen(
        f"{tg}/getUpdates?offset={state['tg_offset']}&allowed_updates=%5B%22channel_post%22%2C%22message%22%5D").read())
    for u in upd.get("result", []):
        state["tg_offset"] = u["update_id"] + 1
        m = u.get("channel_post") or u.get("message") or {}
        fid = None
        if m.get("photo"):
            fid = m["photo"][-1]["file_id"]
        elif m.get("document", {}).get("mime_type", "").startswith("image/jpeg"):
            fid = m["document"]["file_id"]
        if not fid:
            continue
        path = json.loads(urllib.request.urlopen(f"{tg}/getFile?file_id={fid}").read())["result"]["file_path"]
        name = f"tg_{m['date']}_{u['update_id']}.jpg"
        urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{TG}/{path}", os.path.join(PHOTOS, name))
        print("Nouvelle photo Telegram :", name)
    json.dump(state, open(STATE, "w"))

# 2) Pick next photo: Telegram photos not yet posted first, then the rest
files = sorted(f for f in os.listdir(PHOTOS) if f.lower().endswith((".jpg", ".jpeg")))
if not files:
    raise SystemExit("Aucune photo .jpg")
todo = [f for f in files if f not in state["posted"]]
if not todo:
    state["posted"] = []; todo = files
todo.sort(key=lambda f: (not f.startswith("tg_"), f))
pick = todo[0]

def call(path, **params):
    params["access_token"] = TOKEN
    try:
        r = urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data=urllib.parse.urlencode(params).encode()))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit("Erreur Instagram : " + e.read().decode())

# Photo must be on GitHub before Instagram can fetch it -> push first
os.system(f'git config user.name bot && git config user.email bot@users.noreply.github.com && git add -A && git commit -qm "new photos" && git push -q')
url = f"https://raw.githubusercontent.com/{REPO}/main/{PHOTOS}/{urllib.parse.quote(pick)}"
media = call(f"{IG_ID}/media", image_url=url, media_type="STORIES")
time.sleep(10)
print(call(f"{IG_ID}/media_publish", creation_id=media["id"]))
state["posted"].append(pick)
json.dump(state, open(STATE, "w"))
print("Story postée :", pick)
