Markdown
# Live Forge

An open-source, network-based instant replay and broadcast engine designed for grassroots esports LAN tournaments. 

Live Forge allows tournament organizers to pull multiple live player perspectives over a local network (via UDP/SRT), buffer them continuously in the background, and instantly trim, render, and push replays to OBS—all without requiring expensive physical capture cards.

## Features
* **Network Video Ingestion:** Pull 10+ player feeds simultaneously over a Gigabit switch using FFmpeg.
* **Zero-Bloat Buffering:** Captures a rolling memory loop. Players' local hard drives are never filled with massive video files.
* **Instant Replay Deck:** Mark IN/OUT points on the fly using hotkeys (F1-F15) to capture hype moments instantly.
* **OBS WebSocket Integration:** Automatically switches OBS scenes to play the replay, then cuts back to live gameplay.
* **vMix-Style NLE Editor:** Build seamless replay sequences with custom transitions (cuts/dissolves) and speed ramps (slow-mo).
* **Hardware Accelerated:** Full support for NVIDIA CUDA, Intel QSV, and Windows DXVA2 video decoding.

## Recommended LAN Hardware
Because this system routes high-bitrate video over your network rather than physical HDMI cables, your LAN infrastructure must be robust:
* **Gigabit Switch:** A 1000 Mbps switch (e.g., TP-Link 24-Port Gigabit) is **mandatory**. A standard 100 Mbps switch will crash under the bandwidth weight of multiple feeds.
* **Production PC:** An NVIDIA GPU (RTX 3060 or better) is highly recommended for stable NVENC encoding and CUDA decoding.
* **Storage:** A fast external SSD (Type-C) dedicated to the Buffer and Events directories to prevent OS drive bottlenecks.

## Installation & Setup

### Prerequisites
1. Python 3.10 or higher.
2. [FFmpeg](https://ffmpeg.org/download.html) installed and added to your System PATH (or placed directly in the project directory).
3. OBS Studio with the WebSocket server enabled (v5).

### Running from Source
1. Clone the repository:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/live-forge.git](https://github.com/YOUR_USERNAME/live-forge.git)
   cd live-forge
Install the required Python packages:

Bash
pip install -r requirements.txt
Launch the engine:

Bash
python app.py

How to Use
Configure Camera Profiles: Click the SETTINGS button to add the UDP/SRT URLs of your player feeds.

Start Buffering: Click START BUFFERING before the match begins to initiate the rolling capture.

Capture a Moment: Press a hotkey (e.g., F10) right after a great play to extract the last 10 seconds from the buffer.

Broadcast: Select your captured clip in the workspace, click 1. PREP to render it, then click 2. PLAY IN OBS to send it to the live stream.

Contributing
Pull requests are welcome! If you are a broadcast engineer or Python developer looking to improve grassroots esports tools, feel free to open an issue or submit a PR.

License
This project is licensed under the MIT License - see the LICENSE file for details.
