import sys, asyncio, base64, time, io, socket, argparse, subprocess, platform
from typing import Set

try:
    import mss
    from PIL import Image
    import websockets
    import requests
except ImportError as e:
    pkg = str(e).split("'")[1] if "'" in str(e) else str(e)
    print(f"\n  Module manquant : {pkg}")
    print("  pip install mss Pillow websockets requests\n")
    sys.exit(1)

ESP32_URL   = "http://prime-studio.local/screenhost"
WS_PORT     = 8765           # Port EXCLUSIF slot 1
SLOT_ID     = 1
DEFAULT_FPS = 15
DEFAULT_QUAL = 90
DEFAULT_MON  = 1
TARGET_W     = 450
TARGET_H     = 300
CLIENTS: Set = set()

# def check_screen_permission():
    # if platform.system() != "Darwin":
        # return True
    # try:
        # import mss as _mss
        # with _mss.mss() as s:
            # s.grab(s.monitors[0])
        # return True
    # except Exception:
        # return False

# def request_screen_permission():
    # """Ouvre automatiquement les réglages si permission refusée."""
    # print("  ⚠️  Permission enregistrement écran requise.", flush=True)
    # print("  → Ouverture des Réglages Système…", flush=True)
    # subprocess.run([
        # "open",
        # "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    # ], capture_output=True)
    # print("  → Autorise cette app dans Confidentialité → Enregistrement d'écran", flush=True)
    # print("  → Puis relance le programme.\n", flush=True)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

def get_hostname():
    try:
        h = socket.gethostname()
        # Retire .local si présent
        return h.replace(".local", "").replace(".Local", "")
    except: return "inconnu"

def register_ip(ip, hostname):
    try:
        r = requests.post(ESP32_URL,
            json={"ip": ip, "port": WS_PORT, "hostname": hostname, "slot": SLOT_ID},
            timeout=5)
        return r.status_code == 200
    except Exception as e:
        print(f"  ⚠️  ESP32 injoignable : {e}", flush=True)
        return False

async def handler(ws):
    CLIENTS.add(ws)
    addr = ws.remote_address
    print(f"  ✅  [SLOT 1] {addr[0]}:{addr[1]} ({len(CLIENTS)} actif(s))", flush=True)
    try: await ws.wait_closed()
    finally:
        CLIENTS.discard(ws)
        print(f"  ⚠️  [SLOT 1] Déconnecté {addr[0]}", flush=True)

async def stream_loop(fps, quality, monitor_idx):
    interval = 1.0 / fps
    with mss.mss() as sct:
        mon = sct.monitors[min(monitor_idx, len(sct.monitors)-1)]
        print(f"  📺  [SLOT 1] {mon['width']}x{mon['height']}", flush=True)
        print("  ⏳  En attente de clients...\n", flush=True)
        while True:
            t0 = time.perf_counter()
            if CLIENTS:
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)
                canvas = Image.new("RGB", (TARGET_W, TARGET_H), (0,0,0))
                canvas.paste(img, ((TARGET_W-img.width)//2, (TARGET_H-img.height)//2))
                buf = io.BytesIO()
                canvas.save(buf, format="JPEG", quality=quality, optimize=True)
                payload = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                await asyncio.gather(
                    *[ws.send(payload) for ws in list(CLIENTS)],
                    return_exceptions=True
                )
            await asyncio.sleep(max(0.0, interval - (time.perf_counter()-t0)))

async def main(fps, quality, monitor_idx):
    ip       = get_local_ip()
    hostname = get_hostname()

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║  SCREEN STREAM — SLOT 1 (port 8765)      ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║  Appareil : {hostname:<28} ║")
    print(f"║  IP       : {ip:<28} ║")
    print(f"║  WS Port  : 8765                         ║")
    print(f"║  Endpoint : /screenhost                  ║")
    print(f"╚══════════════════════════════════════════╝\n")

    # if not check_screen_permission():
        # request_screen_permission()
        # sys.exit(1)

    print("  Enregistrement ESP32... ", end="", flush=True)
    ok = register_ip(ip, hostname)
    print("OK ✅" if ok else "ECHEC ⚠️  (ESP32 non connecté)", flush=True)
    print()

    async with websockets.serve(
        handler, "0.0.0.0", WS_PORT,
        origins=None,
        max_size=10*1024*1024,
        ping_interval=20,
        ping_timeout=10
    ):
        await stream_loop(fps, quality, monitor_idx)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fps",     type=int, default=DEFAULT_FPS)
    p.add_argument("--quality", type=int, default=DEFAULT_QUAL)
    p.add_argument("--monitor", type=int, default=DEFAULT_MON)
    a = p.parse_args()
    try:
        asyncio.run(main(a.fps, a.quality, a.monitor))
    except KeyboardInterrupt:
        print("\n  Arret.\n")