import os, json, time, subprocess, urllib.request, urllib.parse

IG_ID = os.environ["IG_ID"]
TOKEN = os.environ["IG_TOKEN"]
TG = os.environ.get("TG_TOKEN", "")
REPO = os.environ["GITHUB_REPOSITORY"]
PHOTOS, STATE = "photos", "state.json"
API = "https://graph.facebook.com/v21.0"
IMG = (".jpg", ".jpeg")
VID = (".mp4",)

state = json.load(open(STATE)) if os.path.exists(STATE) else {}
state.setdefault("posted", []); state.setdefault("tg_offset", 0)
os.makedirs(PHOTOS, exist_ok=True)

def to_jpg(src, dst):
    from PIL import Image, ImageOps
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
    except Exception:
        pass
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((1080, 1920))
    im.save(dst, "JPEG", quality=90)

def to_mp4(src, dst):
    # vertical 1080x1920 (blurred fill), max 59 s, H.264/AAC = what Instagram wants
    vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20[bg];"
          "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-i", src, "-t", "59", "-filter_complex", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-r", "30",
                    "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart", dst],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# 1) Pull new photos/videos sent to the Telegram channel (as photo, video OR file)
if TG:
    tg = f"https://api.telegram.org/bot{TG}"
    upd = json.loads(urllib.request.urlopen(
        f"{tg}/getUpdates?offset={state['tg_offset']}&allowed_updates=%5B%22channel_post%22%2C%22message%22%5D").read())
    for u in upd.get("result", []):
        state["tg_offset"] = u["update_id"] + 1
        m = u.get("channel_post") or u.get("message") or {}
        doc = m.get("document") or {}
        mime = doc.get("mime_type", "")
        if m.get("photo"):
            f, kind = m["photo"][-1], "img"
        elif m.get("video"):
            f, kind = m["video"], "vid"
        elif mime.startswith("image/"):
            f, kind = doc, "img"
        elif mime.startswith("video/"):
            f, kind = doc, "vid"
        else:
            continue
        if f.get("file_size", 0) > 20_000_000:
            print("Trop lourd (>20 Mo) pour le bot Telegram, ignoré :", doc.get("file_name", "video"))
            continue
        try:
            path = json.loads(urllib.request.urlopen(f"{tg}/getFile?file_id={f['file_id']}").read())["result"]["file_path"]
            raw = "tmp_" + os.path.basename(path)
            urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{TG}/{path}", raw)
            base = os.path.join(PHOTOS, f"tg_{m['date']}_{u['update_id']}")
            if kind == "img":
                to_jpg(raw, base + ".jpg"); print("Nouvelle photo :", base + ".jpg")
            else:
                to_mp4(raw, base + ".mp4"); print("Nouvelle vidéo :", base + ".mp4")
            os.remove(raw)
        except Exception as e:
            print("Fichier ignoré :", e)
    json.dump(state, open(STATE, "w"))

# 2) Pick next: unposted Telegram items first, then the rest
files = sorted(f for f in os.listdir(PHOTOS) if f.lower().endswith(IMG + VID))
if not files:
    raise SystemExit("Aucune photo/vidéo")
todo = [f for f in files if f not in state["posted"]]
if not todo:
    state["posted"] = []; todo = files
todo.sort(key=lambda f: (not f.startswith("tg_"), f))
pick = todo[0]

def call(path, method="POST", **params):
    params["access_token"] = TOKEN
    q = urllib.parse.urlencode(params)
    try:
        if method == "GET":
            r = urllib.request.urlopen(f"{API}/{path}?{q}")
        else:
            r = urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data=q.encode()))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit("Erreur Instagram : " + e.read().decode())

# Media must be on GitHub before Instagram can fetch it -> push first
os.system('git config user.name bot && git config user.email bot@users.noreply.github.com && git add -A && git commit -qm "new media" && git push -q')
url = f"https://raw.githubusercontent.com/{REPO}/main/{PHOTOS}/{urllib.parse.quote(pick)}"
if pick.lower().endswith(VID):
    media = call(f"{IG_ID}/media", video_url=url, media_type="STORIES")
    for _ in range(40):  # wait up to ~4 min for Instagram to process the video
        time.sleep(6)
        st = call(media["id"], method="GET", fields="status_code").get("status_code")
        if st == "FINISHED": break
        if st == "ERROR": raise SystemExit("Instagram a refusé la vidéo : " + pick)
else:
    media = call(f"{IG_ID}/media", image_url=url, media_type="STORIES")
    time.sleep(10)
print(call(f"{IG_ID}/media_publish", creation_id=media["id"]))
state["posted"].append(pick)
json.dump(state, open(STATE, "w"))
print("Story postée :", pick)
