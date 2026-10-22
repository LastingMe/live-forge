import os
import io
import re
import glob
import shutil
import subprocess
import threading
import time
from datetime import datetime
from PIL import Image

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
PLAY_FPS = 30           
MASTER_SECONDS = 20     

def get_ffmpeg_exe() -> str:
    if shutil.which("ffmpeg"): return "ffmpeg"
    if os.path.exists("ffmpeg.exe"): return os.path.abspath("ffmpeg.exe")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError: return "ffmpeg"

FFMPEG_BIN = get_ffmpeg_exe()

def _run(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)

def probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG_BIN, "-i", path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr.decode("utf-8", "ignore"))
    if not m: return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

def pop_jpeg(buf: bytes):
    s = buf.find(b"\xff\xd8")
    if s == -1: return None, buf[-1:]
    e = buf.find(b"\xff\xd9", s + 2)
    if e == -1: return None, buf[s:]
    return buf[s:e + 2], buf[e + 2:]

class ReplayChannel:
    def __init__(self, channel_id: str, input_source: str, buffer_dir: str, buffer_seconds: int = 30, config: dict = None):
        self.channel_id = channel_id
        self.input_source = input_source
        self.buffer_seconds = buffer_seconds
        self.config = config or {}
        self.channel_dir = os.path.abspath(os.path.join(buffer_dir, self.channel_id))
        os.makedirs(self.channel_dir, exist_ok=True)
        self.process = None
        self.is_running = False
        self.latest_pil_image = None

    def start_buffering(self):
        self.stop_buffering()
        self.latest_pil_image = None
        for f in glob.glob(os.path.join(self.channel_dir, "*.ts")):
            try: os.remove(f)
            except OSError: pass

        pattern = os.path.join(self.channel_dir, "seg_%03d.ts")
        hwaccel = self.config.get("hwaccel", "None")
        fps = self.config.get("fps", "30")
        custom_flags = self.config.get("custom_flags", "")

        input_args = []
        if hwaccel == "CUDA (NVIDIA)": input_args += ["-hwaccel", "cuda"]
        elif hwaccel == "QSV (Intel)": input_args += ["-hwaccel", "qsv"]
        elif hwaccel == "DXVA2 (Windows)": input_args += ["-hwaccel", "dxva2"]

        if custom_flags:
            input_args += custom_flags.split()

        if self.input_source == "test":
            input_args += ["-f", "lavfi", "-i", f"smptebars=size=1280x720:rate={fps}"]
        elif self.input_source == "local_desktop":
            input_args += ["-f", "gdigrab", "-framerate", fps, "-i", "desktop"]
        elif self.input_source.startswith("dshow:"):
            input_args += ["-f", "dshow", "-framerate", fps, "-i", f"video={self.input_source[6:]}"]
        else:
            input_args += ["-i", self.input_source]

        cmd = [
            FFMPEG_BIN, "-y", *input_args,
            "-vf", "scale=1280:720",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-g", fps, "-sc_threshold", "0",
            "-f", "segment", "-segment_time", "1",
            "-segment_wrap", str(self.buffer_seconds), pattern,
            "-vf", "fps=12,scale=320:180",
            "-c:v", "mjpeg", "-q:v", "5", "-f", "image2pipe", "-",
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 6, creationflags=NO_WINDOW)
        self.is_running = True
        threading.Thread(target=self._read_live_frames, args=(self.process,), daemon=True).start()

    def _read_live_frames(self, proc):
        buf = b""
        while self.is_running and proc.stdout:
            chunk = proc.stdout.read(16384)
            if not chunk: break
            buf += chunk
            while True:
                jpg, buf = pop_jpeg(buf)
                if jpg is None: break
                try:
                    img = Image.open(io.BytesIO(jpg))
                    img.load()
                    self.latest_pil_image = img
                except Exception: pass

    def stop_buffering(self):
        self.is_running = False
        if self.process:
            try: self.process.terminate()
            except Exception: pass
            self.process = None

    def get_segment_count(self) -> int:
        return len(glob.glob(os.path.join(self.channel_dir, "seg_*.ts")))

    def snapshot(self, out_path: str, max_seconds: int = MASTER_SECONDS) -> float:
        segs = glob.glob(os.path.join(self.channel_dir, "seg_*.ts"))
        if len(segs) < 2: return 0.0
        segs.sort(key=os.path.getmtime)
        done = segs[:-1][-max_seconds:]
        list_path = out_path + ".txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for s in done: f.write(f"file '{s.replace(chr(92), '/')}'\n")
        _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-movflags", "+faststart", out_path])
        if not (os.path.exists(out_path) and os.path.getsize(out_path) > 0): return 0.0
        return probe_duration(out_path)

class ClipPlayer:
    def __init__(self):
        self.process = None
        self.latest_pil_image = None
        self.serial = 0               
        self.is_playing = False       
        self.finished = False
        self.paused = False
        self.path = None
        self.start = 0.0
        self.end = None
        self.speed = 1.0
        self.frames = 0
        self._hold_first = False
        self._gen = 0

    def position(self) -> float:
        return self.start + self.frames * self.speed / PLAY_FPS

    def play(self, path, start=0.0, end=None, speed=1.0, paused=False, size=(480, 270)):
        self._kill()
        self._gen += 1
        gen = self._gen
        self.path, self.start, self.end, self.speed = path, max(0.0, start), end, speed
        self.frames = 0
        self.finished = False
        self.paused = False
        self._hold_first = paused
        self.is_playing = True

        cmd = [FFMPEG_BIN, "-ss", f"{self.start:.3f}"]
        if end is not None: cmd += ["-t", f"{max(0.05, end - self.start):.3f}"]
        cmd += ["-i", path, "-vf", f"setpts={1.0 / speed}*PTS,fps={PLAY_FPS},scale={size[0]}:{size[1]}", "-an", "-c:v", "mjpeg", "-q:v", "4", "-f", "image2pipe", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 6, creationflags=NO_WINDOW)
        self.process = proc
        threading.Thread(target=self._reader, args=(proc, gen), daemon=True).start()

    def _reader(self, proc, gen):
        buf = b""
        next_t = time.perf_counter()
        while gen == self._gen:
            chunk = proc.stdout.read(16384)
            if not chunk: break
            buf += chunk
            while gen == self._gen:
                jpg, buf = pop_jpeg(buf)
                if jpg is None: break
                try:
                    img = Image.open(io.BytesIO(jpg))
                    img.load()
                except Exception: continue
                while self.paused and gen == self._gen:
                    time.sleep(0.02)
                    next_t = time.perf_counter()
                next_t += 1.0 / PLAY_FPS
                delay = next_t - time.perf_counter()
                if delay > 0: time.sleep(delay)
                if gen != self._gen: return
                self.latest_pil_image = img
                self.frames += 1
                self.serial += 1
                if self._hold_first:
                    self._hold_first = False
                    self.paused = True
        if gen == self._gen:
            self.is_playing = False
            self.finished = True

    def _kill(self):
        if self.process:
            try: self.process.terminate()
            except Exception: pass
            self.process = None

    def stop(self):
        self._gen += 1
        self._kill()
        self.is_playing = False
        self.paused = False

class ReplayEngine:
    def __init__(self, base_buffer_dir="buffer", base_events_dir="events"):
        self.base_buffer_dir = os.path.abspath(base_buffer_dir)
        self.base_events_dir = os.path.abspath(base_events_dir)
        os.makedirs(self.base_buffer_dir, exist_ok=True)
        os.makedirs(self.base_events_dir, exist_ok=True)
        self.channels: dict[str, ReplayChannel] = {}
        self.events: list[dict] = []
        self.player = ClipPlayer()
        self._counter = 0
        self.program_out_file = os.path.join(self.base_events_dir, "LIVE_REPLAY_OUT.mp4")
        self.settings = {}

    def configure_mode(self, mode: str, source_type: str = "LOCAL Screen"):
        self.stop_all()
        self.channels.clear()
        
        if mode == "CUSTOM Config":
            saved = self.settings.get('saved_feeds', [])
            for f in saved:
                self.add_channel(f["name"], f["url"], f.get("config", {}))
            return
            
        default_modes = {
            "ONLINE Profile": {"count": 3, "prefix": "OBS_", "start_port": 9001},
            "LAN Profile": {"count": 10, "prefix": "Player_", "start_port": 9001}
        }
        default_sources = {
            "NETWORK Stream": "udp://0.0.0.0:{port}?overrun_nonfatal=1&fifo_size=50000000",
            "LOCAL Screen": "local_desktop",
            "TEST Bars": "test"
        }

        modes_dict = self.settings.get('modes', default_modes)
        sources_dict = self.settings.get('sources', default_sources)
        
        mode_cfg = modes_dict.get(mode, {"count": 1, "prefix": "Cam_", "start_port": 9000})
        count = int(mode_cfg.get("count", 1))
        prefix = mode_cfg.get("prefix", "Cam_")
        start_port = int(mode_cfg.get("start_port", 9000))
        
        src_template = sources_dict.get(source_type, "test")

        def_hw = self.settings.get('default_hwaccel', 'None')
        def_fps = self.settings.get('default_fps', '30')
        def_flags = self.settings.get('default_flags', '')
        config = {"hwaccel": def_hw, "fps": def_fps, "custom_flags": def_flags}
        
        for i in range(1, count + 1):
            name = f"{prefix}{i}"
            port = start_port + i - 1
            if src_template == "test": src = "test"
            elif src_template == "local_desktop": src = "local_desktop"
            else: src = src_template.replace("{port}", str(port))
            self.add_channel(name, src, config)

    def add_channel(self, name: str, src: str, config: dict = None) -> bool:
        if not name or name in self.channels: return False
        buf_sec = self.settings.get('buffer_seconds', 30)
        ch = ReplayChannel(name, src, self.base_buffer_dir, buf_sec, config)
        self.channels[name] = ch
        return True

    def remove_channel(self, name: str):
        ch = self.channels.pop(name, None)
        if ch: ch.stop_buffering()

    def start_all(self):
        for ch in self.channels.values(): ch.start_buffering()

    def stop_all(self):
        for ch in self.channels.values(): ch.stop_buffering()

    def get_buffer_health(self) -> int:
        if not self.channels: return 0
        return next(iter(self.channels.values())).get_segment_count()

    def next_id(self) -> str:
        self._counter += 1
        return f"E{self._counter:03d}"

    def delete_files(self, paths):
        paths = [p for p in paths if os.path.abspath(p).startswith(self.base_events_dir)]
        def work():
            dirs = set()
            for p in paths:
                dirs.add(os.path.dirname(p))
                for q in (p, p + ".txt"):
                    for _ in range(10):
                        try:
                            if os.path.exists(q): os.remove(q)
                            break
                        except OSError: time.sleep(0.5)
            for d in dirs:
                try: os.rmdir(d)          
                except OSError: pass
        threading.Thread(target=work, daemon=True).start()

    def mark_live(self, duration: float):
        ts = datetime.now().strftime("%H-%M-%S")
        eid = self.next_id()
        edir = os.path.join(self.base_events_dir, f"{eid}_{ts}")
        os.makedirs(edir, exist_ok=True)
        lens, masters, threads = {}, {}, []

        def work(name, ch):
            out = os.path.join(edir, f"{name}.mp4")
            d = ch.snapshot(out, max_seconds=int(duration) + 1)
            if d > 0:
                masters[name] = out
                lens[name] = d

        for name, ch in list(self.channels.items()):
            t = threading.Thread(target=work, args=(name, ch))
            t.start()
            threads.append(t)
        for t in threads: t.join()
        if not masters: return None

        length = min(lens.values())
        offsets = {n: lens[n] - length for n in masters}
        ev = {
            "id": eid, "label": eid, "time": ts,
            "tags": [],
            "masters": dict(sorted(masters.items())),
            "offsets": offsets, "length": length,
            "in": max(0.0, length - duration), "out": length,
        }
        self.events.append(ev)
        return ev

    def mark_from(self, ref: dict, pos: float, duration: float):
        eid = self.next_id()
        ev = dict(ref)
        ev.update({"id": eid, "label": eid, "tags": [], "in": max(0.0, pos - duration), "out": max(0.1, min(pos, ref["length"]))})
        self.events.append(ev)
        return ev

    def angle_range(self, ev: dict, angle: str):
        off = ev["offsets"].get(angle, 0.0)
        return ev["masters"][angle], off + ev["in"], off + ev["out"]

    def render_clip(self, path, start, end, speed, out_path):
        _run([FFMPEG_BIN, "-y", "-ss", f"{start:.3f}", "-t", f"{max(0.05, end - start):.3f}", "-i", path,
              "-vf", f"setpts={1.0 / speed}*PTS,scale=1280:720,fps=60",
              "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-movflags", "+faststart", out_path])
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0

    def render_mosaic(self, ev: dict, angles: list, start: float, end: float, speed: float, out_path: str):
        if not angles: return False
        inputs = []
        for a in angles:
            path = ev["masters"][a]
            off = ev["offsets"].get(a, 0.0)
            inputs.extend(["-ss", f"{off + start:.3f}", "-t", f"{max(0.05, end - start):.3f}", "-i", path])
            
        n = len(angles)
        if n == 1:
            filter_complex = f"[0:v]setpts={1.0/speed}*PTS,scale=1280:720,fps=60[v]"
        elif n == 2:
            filter_complex = f"[0:v]setpts={1.0/speed}*PTS,scale=640:360[v0]; [1:v]setpts={1.0/speed}*PTS,scale=640:360[v1]; [v0][v1]hstack=inputs=2[top]; [top]pad=1280:720:0:180:black[v]"
        elif n == 3:
            filter_complex = f"[0:v]setpts={1.0/speed}*PTS,scale=640:360[v0]; [1:v]setpts={1.0/speed}*PTS,scale=640:360[v1]; [2:v]setpts={1.0/speed}*PTS,scale=640:360[v2]; color=c=black:s=640x360[v3]; [v0][v1]hstack=inputs=2[top]; [v2][v3]hstack=inputs=2[bottom]; [top][bottom]vstack=inputs=2[v]"
        else:
            filter_complex = f"[0:v]setpts={1.0/speed}*PTS,scale=640:360[v0]; [1:v]setpts={1.0/speed}*PTS,scale=640:360[v1]; [2:v]setpts={1.0/speed}*PTS,scale=640:360[v2]; [3:v]setpts={1.0/speed}*PTS,scale=640:360[v3]; [v0][v1]hstack=inputs=2[top]; [v2][v3]hstack=inputs=2[bottom]; [top][bottom]vstack=inputs=2[v]"
                
        cmd = [FFMPEG_BIN, "-y", *inputs, "-filter_complex", filter_complex, "-map", "[v]", 
               "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
        
        _run(cmd)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0

    def _publish(self, tmp):
        try:
            os.replace(tmp, self.program_out_file)
            return self.program_out_file
        except OSError:       
            alt = os.path.join(self.base_events_dir, f"REPLAY_{datetime.now().strftime('%H%M%S')}.mp4")
            os.replace(tmp, alt)
            return alt

    def render_program(self, path, start, end, speed):
        tmp = self.program_out_file + ".tmp.mp4"
        if self.render_clip(path, start, end, speed, tmp): return self._publish(tmp)
        return ""

    def render_program_mosaic(self, ev: dict, angles: list, start: float, end: float, speed: float):
        tmp = self.program_out_file + ".tmp.mp4"
        if self.render_mosaic(ev, angles, start, end, speed, tmp): return self._publish(tmp)
        return ""

    def render_playlist(self, items: list, transition: str = "CUT", trans_dur: float = 0.5):
        """vMix-style Playlist Stitcher supporting CUT or DISSOLVE transitions."""
        if not items: return ""
        work = os.path.join(self.base_events_dir, "_playlist")
        os.makedirs(work, exist_ok=True)
        
        # 1. Render each individual segment to a standardized container
        parts = []
        durs = []
        for i, it in enumerate(items):
            out = os.path.join(work, f"part_{i:03d}.mp4")
            if self.render_clip(it["path"], it["start"], it["end"], it["speed"], out):
                parts.append(out)
                durs.append((it["end"] - it["start"]) / it["speed"])
        
        if not parts: return ""
        tmp = self.program_out_file + ".tmp.mp4"

        # CUT transition: fast concat
        if transition == "CUT" or len(parts) == 1:
            lst = os.path.join(work, "list.txt")
            with open(lst, "w", encoding="utf-8") as f:
                for p in parts: f.write(f"file '{p.replace(chr(92), '/')}'\n")
            _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", tmp])
            return self._publish(tmp) if os.path.exists(tmp) else ""

        # DISSOLVE transition: xfade filter graph
        inputs = []
        for p in parts: inputs.extend(["-i", p])
        
        filter_str = ""
        last_v = "[0:v]"
        cum_offset = 0.0
        
        for i in range(1, len(parts)):
            cum_offset += durs[i-1] - trans_dur
            next_v = f"[v_mix_{i}]" if i < len(parts) - 1 else "[v_out]"
            filter_str += f"{last_v}[{i}:v]xfade=transition=fade:duration={trans_dur:.2f}:offset={max(0.1, cum_offset):.2f}{next_v};"
            last_v = next_v
            
        cmd = [FFMPEG_BIN, "-y", *inputs, "-filter_complex", filter_str, "-map", "[v_out]",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp]
        _run(cmd)
        
        if os.path.exists(tmp): return self._publish(tmp)
        
        # Fallback to Cut if xfade fails
        lst = os.path.join(work, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts: f.write(f"file '{p.replace(chr(92), '/')}'\n")
        _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", tmp])
        return self._publish(tmp) if os.path.exists(tmp) else ""