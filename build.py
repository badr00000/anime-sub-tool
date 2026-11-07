import PyInstaller.__main__
from pathlib import Path
import sys

def build():
    print("Building Anime Subtitle Automation Tool...")
    
    # Get project root
    root_dir = Path(__file__).parent.absolute()
    
    args = [
        str(root_dir / 'main.py'),
        '--name=AnimeSubTool',
        '--windowed',  # Hide console for GUI
        '--icon=app_icon.ico', # New fluid icon
        '--noconfirm', # Overwrite output dir
        '--clean',
        '--add-data=gui;gui', 
        '--add-data=core;core',
        '--add-data=cli;cli',
        '--add-data=utils;utils',
        '--add-data=bin;bin',
        '--add-data=app_icon.ico;.',
    ]
    
    try:
        PyInstaller.__main__.run(args)
        print("\nBuild complete! Executable is in the 'dist' folder.")
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
