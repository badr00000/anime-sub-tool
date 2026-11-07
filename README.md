# 🎬 Anime Subtitle Automation Tool v2.0

A powerful, smart, and fully automated batch tool designed to seamlessly merge MKV anime videos with downloaded subtitle files. It uses fuzzy string matching (via `anitopy` and `rapidfuzz`) to automatically link confusing episode names, and executes blistering fast multi-threaded processing using a bundled `MKVToolNix` engine.

![Anime Sub Tool](https://via.placeholder.com/800x400.png?text=Anime+Subtitle+Automation+Tool)

## ✨ Key Features

- **🧠 Smart AI Matching:** Automatically matches differently named video and subtitle files using advanced parsing (`anitopy`) and fuzzy text matching (`rapidfuzz`). 
  - *Example: `[Cleo]Mousou_Dairinin_-_01` will perfectly match `[Scarlet] Paranoia Agent - 01`.*
- **⚡ Blazing Fast Multi-Threading:** Process multiple episodes simultaneously. Utilize up to 100% of your CPU for massive batch operations.
- **👁️ Watch Folder Daemon:** Automatically monitors a folder in the background. Just drop new `.mkv` files into the folder and they will be processed instantly!
- **🎛️ Advanced Custom Filters:** 
  - Keep specific audio tracks (e.g. `jpn, eng`).
  - Strip or keep specific subtitle tracks.
- **💾 Configuration Presets:** Save your favorite filters, thread counts, and configurations as profiles to load them with a single click.
- **📦 Fully Portable:** No need to install `MKVToolNix`! The required binaries (`mkvmerge` and `mkvpropedit`) are bundled internally. Just run the `.exe` anywhere.

## 🚀 How to Use

1. **Select Folder:** Choose the folder containing your MKV episodes and Subtitle files.
2. **Scan:** Click "Scan Folder". The tool will pair them up with 100% confidence.
3. **Review:** Check the preview window to see exactly what audio tracks will be kept and what subtitles will be injected.
4. **Process:** Click "Start Processing" and watch the magic happen.

*Alternatively, check the "Enable Watch Folder" box to let the tool run in the background and process files automatically as you download them!*

## 🛠️ Build from Source

Requirements: Python 3.11+

```bash
# Clone the repository
git clone https://github.com/yourusername/anime-sub-tool.git
cd anime-sub-tool

# Install requirements
pip install -r requirements.txt

# Run the application
python main.py
```

### Packaging into a Portable EXE

To build a single self-contained `.exe` (Python, Qt and the bundled MKVToolNix binaries all inside), run:

```bash
py -3.11 -m pip install pyinstaller
py -3.11 build.py
```

The result is one file: `dist/AnimeSubTool.exe`. Copy it anywhere (for example the Desktop) and double-click it; nothing else needs to be installed. The first launch takes a few seconds because the bundle unpacks itself to a temporary folder.

## ⚖️ License & Acknowledgements
- UI Built with [PySide6](https://pypi.org/project/PySide6/).
- Anime parsing powered by [anitopy](https://github.com/kuroahna/anitopy).
- Fuzzy matching by [RapidFuzz](https://github.com/maxbachmann/RapidFuzz).
- Powered by [MKVToolNix](https://mkvtoolnix.download/) (Bundled under GPLv2).
