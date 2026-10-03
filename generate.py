import os, json, math, asyncio, subprocess, requests
from PIL import Image, ImageDraw, ImageFont, ImageColor

W, H, FPS, S = 1280, 720, 15, 2          # S = supersampling for smooth lines
VOICE = "en-US-GuyNeural"
BGS = ["#cfe8ff", "#ffe9b8", "#d9f2d0", "#f9d4d4", "#e3d7f7", "#ffd9ec"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# pose: (left_arm, right_arm, left_leg, right_leg, face)   angles: 0=down, 90=sideways, 180=up
POSES = {
    "stand":   (20, 20, 8, 8, "happy"),
    "wave":    (20, 140, 8, 8, "happy"),
    "point":   (20, 95, 8, 8, "normal"),
    "think":   (20, 150, 8, 8, "think"),
    "shocked": (135, 135, 10, 10, "shock"),
    "sad":     (8, 8, 5, 5, "sad"),
    "walk":    (25, 25, 0, 0, "happy"),
}


def font(size):
    try:
        return ImageFont.truetype(FONT, size * S)
    except Exception:
        return ImageFont.load_default()


def wrap(d, text, f, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= max_w * S:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def line(d, p, q, w=8):
    d.line([p[0] * S, p[1] * S, q[0] * S, q[1] * S], fill="black", width=w * S)
    for x, y in (p, q):
        r = w * S / 2
        d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill="black")


def end(p, L, a, dirn):
    r = math.radians(a)
    return (p[0] + dirn * L * math.sin(r), p[1] + L * math.cos(r))


def draw_frame(t, prog, idx, title, narration, pose):
    bg = BGS[idx % len(BGS)]
    img = Image.new("RGB", (W * S, H * S), bg)
    d = ImageDraw.Draw(img)
    gy = 540
    floor = tuple(int(c * 0.85) for c in ImageColor.getrgb(bg))
    d.rectangle([0, gy * S, W * S, H * S], fill=floor)

    la, ra, ll, rl, face = POSES.get(pose, POSES["stand"])
    cx = 640
    if pose == "walk":
        sw = 28 * math.sin(2 * math.pi * 1.6 * t)
        ll, rl = sw, -sw
        cx = 380 + 520 * prog
    elif pose == "wave":
        ra = 140 + 25 * math.sin(2 * math.pi * 2.5 * t)
    elif pose == "shocked":
        cx += 3 * math.sin(40 * t)
    else:
        la += 5 * math.sin(2 * math.pi * 0.8 * t)
        ra += 5 * math.sin(2 * math.pi * 0.8 * t + 1)

    bob = 4 * math.sin(2 * math.pi * 1.2 * t)
    leg, torso, hr, arm = 150, 130, 48, 115
    hip = (cx, gy - leg + bob)
    neck = (cx, hip[1] - torso)
    head = (cx, neck[1] - hr + (10 if pose == "sad" else 0))
    sh = (cx, neck[1] + 18)

    line(d, hip, end(hip, leg, ll, -1))
    line(d, hip, end(hip, leg, rl, 1))
    line(d, neck, hip)
    line(d, sh, end(sh, arm, la, -1))
    line(d, sh, end(sh, arm, ra, 1))

    # head
    hx, hy, r = head[0] * S, head[1] * S, hr * S
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill="white", outline="black", width=7 * S)
    ex = 16 * S
    er = (9 if face == "shock" else 5) * S
    for sx in (-ex, ex):
        d.ellipse([hx + sx - er, hy - 8 * S - er, hx + sx + er, hy - 8 * S + er],
                  fill="black" if face != "shock" else "white",
                  outline="black", width=3 * S)
    my = hy + 18 * S
    if face == "happy":
        d.arc([hx - 16 * S, my - 14 * S, hx + 16 * S, my + 10 * S], 20, 160, fill="black", width=4 * S)
    elif face == "sad":
        d.arc([hx - 14 * S, my, hx + 14 * S, my + 22 * S], 200, 340, fill="black", width=4 * S)
    elif face == "shock":
        d.ellipse([hx - 8 * S, my - 6 * S, hx + 8 * S, my + 12 * S], outline="black", width=4 * S)
    else:
        d.line([hx - 12 * S, my, hx + 12 * S, my], fill="black", width=4 * S)

    # title (top)
    ft = font(64)
    tw = d.textlength(title, font=ft)
    d.text(((W * S - tw) / 2, 35 * S), title, font=ft, fill="#1a1a1a")

    # subtitles (bottom)
    fs = font(30)
    lines = wrap(d, narration, fs, 1150)[:3]
    box_h = 12 + 38 * len(lines)
    top = H - box_h - 8
    d.rounded_rectangle([60 * S, top * S, (W - 60) * S, (H - 8) * S],
                        radius=14 * S, fill="white", outline="black", width=3 * S)
    for k, ln in enumerate(lines):
        lw = d.textlength(ln, font=fs)
        d.text(((W * S - lw) / 2, (top + 8 + 38 * k) * S), ln, font=fs, fill="#111")
    return img.reduce(S)


def get_script(topic, key):
    prompt = (
        f'Write a calm, curious ~60 second explainer video script about "{topic}", '
        "in a friendly storytelling tone. Return ONLY a JSON list of 6 to 8 scenes: "
        '[{"title": "2-4 word on-screen headline", '
        '"narration": "1-2 sentences, max 30 words", '
        '"pose": "one of: stand, wave, point, think, shocked, sad, walk"}]'
    )
    for _ in range(3):
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json"}},
                timeout=60)
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            txt = txt.strip().removeprefix("```json").removesuffix("```").strip()
            scenes = json.loads(txt)
            if isinstance(scenes, list) and scenes:
                return scenes[:8]
        except Exception as e:
            print("script retry:", e)
    raise RuntimeError("Could not get script from Gemini")


def probe(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                   "format=duration", "-of", "csv=p=0", path])
    return float(out)


def main():
    import edge_tts
    token, chat = os.environ["BOT_TOKEN"], os.environ["CHAT_ID"]
    topic, key = os.environ["PROMPT"], os.environ["GEMINI_KEY"]

    def tg(text):
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text})

    try:
        tg(f"Generating video about: {topic}\nThis takes a few minutes.")
        scenes = get_script(topic, key)
        clips = []
        for i, s in enumerate(scenes):
            narration = s.get("narration", "")
            title = s.get("title", "")
            pose = s.get("pose", "stand")
            asyncio.run(edge_tts.Communicate(narration, VOICE).save(f"a{i}.mp3"))
            dur = probe(f"a{i}.mp3") + 0.5
            n = int(dur * FPS)
            p = subprocess.Popen([
                "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", f"a{i}.mp3",
                "-af", "apad", "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", f"c{i}.mp4"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            for k in range(n):
                frame = draw_frame(k / FPS, k / max(n - 1, 1), i, title, narration, pose)
                p.stdin.write(frame.tobytes())
            p.stdin.close()
            if p.wait() != 0:
                raise RuntimeError(f"ffmpeg failed on scene {i}")
            clips.append(f"c{i}.mp4")

        with open("list.txt", "w") as f:
            f.write("".join(f"file '{c}'\n" for c in clips))
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                        "-c", "copy", "final.mp4"], check=True, stderr=subprocess.DEVNULL)

        with open("final.mp4", "rb") as f:
            requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                          data={"chat_id": chat}, files={"video": f}, timeout=300)
    except Exception as e:
        tg(f"Sorry, generation failed: {e}")
        raise


if __name__ == "__main__":
    main()
