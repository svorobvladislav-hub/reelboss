import os, json, re, random, subprocess, urllib.parse, datetime
import requests, edge_tts, asyncio

WURL    = os.environ["WORKER_URL"].rstrip("/")
WKEY    = os.environ["WORKER_SECRET"]
USER_ID = os.environ["USER_ID"]
CFG  = requests.get(f"{WURL}/api/config", params={"uid": USER_ID},
                    headers={"x-key": WKEY}, timeout=30).json()["u"]

AI_BASE = CFG["ai_base"].rstrip("/")
AI_KEY, MODEL = CFG["ai_key"], CFG["model"]
NICHE = CFG.get("niche", "загадки, факты, страшные истории")
TOKEN = os.environ["BOT_TOKEN"]
ADMIN = str(CFG["id"])
BANNER = CFG.get("banner_file_id", "")
API  = f"https://api.telegram.org/bot{TOKEN}"

def log(m):
    try: requests.post(f"{API}/sendMessage", json={"chat_id": ADMIN, "text": m}, timeout=30)
    except Exception: pass

def ai(prompt):
    r = requests.post(f"{AI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {AI_KEY}"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]}, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

WD = ["понедельник-мотивация","вторник-разбор","среда-интрига","четверг-факты",
      "пятница-мем","суббота-хайп","воскресенье-атмосфера"][datetime.datetime.utcnow().weekday()]

def build(topic):
    last = ""
    for attempt in range(3):
        try:
            raw = ai(f'Сценарий Shorts 45-55 сек. Ниша канала: {NICHE}. Тема: "{topic}". Тон дня: {WD}. '
                     'Ровно 5 сцен. Ответ — ТОЛЬКО JSON без пояснений: '
                     '{"title":"...","scenes":[{"img":"english vertical image prompt","text":"озвучка сцены 1-2 предложения"}]}')
            return json.loads(re.sub(r"^```json|```$", "", raw.strip(), flags=re.M))
        except Exception as e:
            last = e; log(f"🤕 Заминка ({attempt+1}/3), сам чиню…")
    raise RuntimeError(f"AI не ответил 3 раза: {last}")

def make_script():
    try:
        r = requests.get(f"{WURL}/api/reserve", headers={"x-key": WKEY}, timeout=15).json()
        topics = r.get("topics") or []
        if topics: return build(topics[0])
    except Exception: pass
    return build(random.choice(["топ-5 загадок: " + NICHE, "шокирующие факты: " + NICHE,
                                "страшная история: " + NICHE, "а что если: " + NICHE]))

async def tts(text, mp3, srt, idx):
    com = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
    words, audio = [], b""
    async for ch in com.stream():
        if ch["type"] == "audio": audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append((ch["offset"]/1e7, (ch["offset"]+ch["duration"])/1e7, ch["text"]))
    open(mp3, "wb").write(audio)
    with open(srt, "w", encoding="utf-8") as f:
        n = 0
        for i in range(0, len(words), 6):
            g = words[i:i+6]; n += 1
            f.write(f"{n}\n{g[0][0]:.2f} --> {g[-1][1]:.2f}\n" + " ".join(w[2] for w in g) + "\n\n")

def dur(p):
    o = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","csv=p=0",p], capture_output=True, text=True)
    return float(o.stdout.strip())

def dl_image(prompt, path):
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + "?width=1080&height=1920&nologo=true&seed=" + str(random.randint(1,999999)))
    open(path,"wb").write(requests.get(url, timeout=150).content)

def dl_banner():
    if not BANNER: return None
    fp = requests.get(f"{API}/getFile", params={"file_id": BANNER}, timeout=30).json()["result"]["file_path"]
    open("banner.mp4","wb").write(requests.get(f"{API}/file/bot{TOKEN}/{fp}", timeout=120).content)
    return "banner.mp4"

async def main():
    script = make_script()
    scenes = script["scenes"][:6]
    log(f"✍️ Сценарий готов: «{script['title']}». Монтирую…")
    parts, subs, t0 = [], [], 0.0
    for i, sc in enumerate(scenes):
        mp3, srt = f"a{i}.mp3", f"s{i}.srt"
        await tts(sc["text"], mp3, srt, i)
        d = dur(mp3); frames = max(30, int(d*30))
        dl_image(sc["img"], f"i{i}.jpg")
        vf = (f"scale=1080:1920,zoompan=z='min(zoom+0.0012,1.25)':d={frames}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30")
        r = subprocess.run(["ffmpeg","-y","-i",f"i{i}.jpg","-vf",vf,"-i",mp3,
             "-t",str(d),"-c:v","libx264","-c:a","aac",f"p{i}.mp4"], capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["ffmpeg","-y","-loop","1","-t",str(d),"-i",f"i{i}.jpg",
                "-vf","scale=1080:1920","-i",mp3,"-c:v","libx264","-c:a","aac",f"p{i}.mp4"], check=True)
        with open(srt) as f: subs.append((t0, f.read()))
        parts.append(f"file 'p{i}.mp4'"); t0 += d

    open("list.txt","w").write("\n".join(parts))
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i","list.txt","-c","copy","base.mp4"], check=True)
    with open("all.srt","w",encoding="utf-8") as f:
        for off, s in subs:
            for line in s.splitlines():
                m = re.match(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)", line)
                if m:
                    a = off + int(m[1])*3600 + int(m[2])*60 + float(m[3])
                    b = off + int(m[4])*3600 + int(m[5])*60 + float(m[6])
                    f.write(f"{int(a//3600)}:{int(a%3600//60):02d}:{a%60:05.2f} --> "
                            f"{int(b//3600)}:{int(b%3600//60):02d}:{b%60:05.2f}\n")
                elif "-->" in line: continue
                else: f.write(line + "\n")
            f.write("\n")
    vfc = "subtitles=all.srt:force_style='Fontsize=18,Bold=1,MarginV=140'"
    b = dl_banner()
    if b:
        subprocess.run(["ffmpeg","-y","-i","base.mp4","-stream_loop","-1","-i",b,
          "-filter_complex",
          f"[0:v]{vfc}[v];[1:v]scale=1080:-2,fade=t=in:st=5:d=0.5:alpha=1,"
          f"fade=t=out:st=19.5:d=0.5:alpha=1[bn];[v][bn]overlay=(W-w)/2:H-h-260:eof_action=pass",
          "-t",str(t0),"-c:v","libx264","-c:a","copy","final.mp4"], check=True)
    else:
        subprocess.run(["ffmpeg","-y","-i","base.mp4","-vf",vfc,"-c:a","copy","final.mp4"], check=True)

    log("🚀 Готово! Отправляю превью…")
    requests.post(f"{API}/sendVideo", data={"chat_id": ADMIN, "caption": f"🎬 {script['title']}"},
        files={"video": open("final.mp4","rb")}, timeout=300)
    subprocess.run(["ffmpeg","-y","-ss",str(max(1,t0/2)),"-i","final.mp4","-frames:v","1","share.jpg"], check=True)
    requests.post(f"{API}/sendPhoto", data={"chat_id":ADMIN,"caption":"📎 Share-карточка"},
        files={"photo":open("share.jpg","rb")}, timeout=120)
    requests.post(f"{API}/sendMessage", json={"chat_id":ADMIN,"text":"Оцени сценарий — учусь у тебя 🧠",
        "reply_markup":{"inline_keyboard":[[{"text":"🔥 Огонь","callback_data":"vote:1"},
        {"text":"😐 Не то","callback_data":"vote:0"}]]}}, timeout=30)

    if CFG.get("yt_refresh"):
        os.environ["YT_CLIENT_ID"]     = CFG.get("yt_client_id","")
        os.environ["YT_CLIENT_SECRET"] = CFG.get("yt_client_secret","")
        os.environ["YT_REFRESH_TOKEN"] = CFG["yt_refresh"]
        from upload import upload
        vid = upload("final.mp4", script["title"], script["title"], ["shorts"])
        log("🚀 Опубликовано: https://youtube.com/shorts/" + vid)
    else:
        log("ℹ️ YouTube не подключен — залив пропущен.")

    requests.post(f"{WURL}/api/bump", headers={"x-key": WKEY}, json={"uid": ADMIN}, timeout=30)

asyncio.run(main())
