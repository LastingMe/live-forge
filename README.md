# Live Forge 🎬

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![OBS](https://img.shields.io/badge/OBS-v28+-black.svg?logo=obs-studio)

> **An open-source, hardware-accelerated broadcast replay system built specifically for tier-1 live esports operations and LAN tournaments.**

*(📸 Add a screenshot of your CustomTkinter dashboard here by replacing this text with `![Dashboard View](link_to_image.png)`)*

Traditional replay software either costs thousands of dollars or locks up your UI during heavy rendering. **Live Forge** solves this by leveraging decoupled FFmpeg subprocesses to isolate heavy video ingestion and encoding from the Python control interface. Your broadcast dashboard remains completely responsive—never dropping frames or freezing during high-pressure tournament matches.

---

## 🔥 Key Features

* **Non-Blocking UI Architecture:** A thread-safe, queue-based backend completely separates the CustomTkinter UI from the FFmpeg segmenting engine.
* **Rolling Multi-Angle Buffers:** Continuously ingest UDP network streams or local desktop captures with automatic `.ts` file segmenting and smart cache cleanup.
* **vMix-Style Storyboard:** Trim, tag, sequence, and queue multi-angle clips dynamically on a timeline grid.
* **Automated OBS Routing:** Native OBS WebSocket v5 integration automatically switches between your `LIVE_GAME` and `REPLAY` scenes with a single click.
* **Hardware Acceleration Out-of-the-Box:** Native encoding support for CUDA (NVIDIA), QSV (Intel), and DXVA2 (Windows).
* **Rapid Deployment Profiles:** Instantly spin up a 10-player LAN grid or a standard 3-angle online broadcast environment using built-in presets.

---

## ⚙️ Prerequisites

Before installing Live Forge, ensure your broadcast rig has the following:
1. **[Python 3.10+](https://www.python.org/)**
2. **[FFmpeg](https://ffmpeg.org/download.html)** (Must be installed and added to your system's `PATH` environment variable)
3. **OBS Studio v28+** (for native WebSocket v5 support)

---

## 🚀 Installation

1. **Clone the repository** to your local broadcast machine:
   ```bash
   git clone [https://github.com/LastingMe/live-forge.git](https://github.com/LastingMe/live-forge.git)
   cd live-forge
Install the required dependencies:

    ```Bash
    pip install -r requirements.txt ```
   📡 OBS Integration Setup 
To allow Live Forge to automatically trigger your replays on stream, configure OBS as follows:

In OBS, navigate to Tools > WebSocket Server Settings.

Enable the WebSocket server on port 4455. (Note: Leave the password blank, or update the app.py script if you require a custom password).

Create a Media Source in your designated Replay scene and name it exactly Instant Replay Video.

🎮 Usage
Launch the control deck from your terminal:

Bash
python app.py
Workflow
Preview Pane: Displays lightweight MJPEG frames of your rolling buffers for zero-latency monitoring.

Prep to OBS (📤): Renders your sequenced clips using XFADE transitions into a single broadcast-ready .mp4 file.

Push Live (🔴): Automatically updates the OBS Media Source, cuts to the replay scene for the exact duration of the clip, and seamlessly cuts back to the live game.

🤝 Contributing
Pull requests are welcome! If you are a tournament organizer or broadcast engineer with ideas for new features (like instant slow-motion rendering or transition stingers), feel free to open an issue to discuss what you would like to change.

📄 License
This project is licensed under the MIT License - see the LICENSE file for details.


<FollowUp> Have you saved this to the README file? Let me know if you need the exact terminal commands to commit this update to your GitHub repository!</FollowUp>
