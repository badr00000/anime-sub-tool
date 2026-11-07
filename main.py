"""Anime Subtitle Automation Tool v2.0 - Entry Point"""
import sys

def main():
    if len(sys.argv) > 1:
        # CLI mode: any argument means CLI
        try:
            import click
        except ImportError:
            print("Error: The 'click' package is required for the CLI but is not installed.")
            print("Please install it using: pip install click")
            sys.exit(1)
            
        from cli.commands import cli
        cli()
    else:
        # GUI mode: no arguments = launch GUI
        try:
            import PySide6
        except ImportError:
            print("Error: The 'PySide6' package is required for the GUI but is not installed.")
            print("Please install it using: pip install PySide6")
            print("Alternatively, you can use the CLI by providing arguments (e.g., --help).")
            sys.exit(1)
            
        from gui.app import main as gui_main
        gui_main()

if __name__ == '__main__':
    main()
