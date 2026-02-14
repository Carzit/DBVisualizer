"""Entry point for packaged builds (exe/app). Defaults to --inbrowser."""
import os
import sys
import argparse
import logging

from dbvisualizer import AppBuilder

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="DB Visualizer")
    parser.add_argument("db_paths", nargs="*", default=[], help="Paths to SQLite database files")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on launch")
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    valid_paths = [p for p in args.db_paths if os.path.exists(p)]

    if not valid_paths:
        logger.info("No DB paths provided. Starting with empty state. "
                     "Use the 'Add Database' panel to upload a .db file.")

    app = AppBuilder(valid_paths).create_ui()
    app.launch(server_port=args.port, inbrowser=not args.no_browser, share=args.share)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
