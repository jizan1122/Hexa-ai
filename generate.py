import os, subprocess, requests

token, chat_id, prompt = os.environ["BOT_TOKEN"], os.environ["CHAT_ID"], os.environ["PROMPT"]

open("text.txt", "w").write(prompt)
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=5",
    "-vf", "drawtext=textfile=text.txt:fontcolor=white:fontsize=48:"
           "x=(w-text_w)/2:y=(h-text_h)/2:"
           "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "-pix_fmt", "yuv420p", "out.mp4"
], check=True)

with open("out.mp4", "rb") as f:
    requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                  data={"chat_id": chat_id}, files={"video": f})