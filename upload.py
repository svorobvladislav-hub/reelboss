import os, requests, json

def get_access():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token"})
    r.raise_for_status()
    return r.json()["access_token"]

def upload(path, title, desc, tags):
    tok = get_access()
    meta = {"snippet": {"title": title[:100], "description": desc,
                        "tags": tags, "categoryId": "24"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        data=json.dumps(meta))
    init.raise_for_status()
    with open(path, "rb") as f:
        up = requests.put(init.headers["Location"],
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Length": str(os.path.getsize(path)),
                     "Content-Type": "video/mp4"}, data=f)
    up.raise_for_status()
    return up.json()["id"]
