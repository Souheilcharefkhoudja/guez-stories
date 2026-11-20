import os, json, time, urllib.request, urllib.parse

IG_ID = os.environ["IG_ID"]            # Instagram business account id
TOKEN = os.environ["IG_TOKEN"]         # Page access token (never expires)
REPO = os.environ["GITHUB_REPOSITORY"] # set automatically by GitHub
PHOTOS = "photos"
STATE = "state.json"
API = "https://graph.facebook.com/v21.0"

def call(path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data=data))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit("Erreur Instagram : " + e.read().decode())

files = sorted(f for f in os.listdir(PHOTOS) if f.lower().endswith((".jpg", ".jpeg")))
if not files:
    raise SystemExit("Aucune photo .jpg dans photos/")

state = json.load(open(STATE)) if os.path.exists(STATE) else {"i": 0}
i = state["i"] % len(files)
url = f"https://raw.githubusercontent.com/{REPO}/main/{PHOTOS}/{urllib.parse.quote(files[i])}"

media = call(f"{IG_ID}/media", image_url=url, media_type="STORIES")
time.sleep(10)  # let Instagram fetch the image
print(call(f"{IG_ID}/media_publish", creation_id=media["id"]))

state["i"] = i + 1
json.dump(state, open(STATE, "w"))
print("Story postée :", files[i])
