import os
import argparse
import logging

from dbvisualizer import AppBuilder

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DB Visualizer")
    parser.add_argument("db_paths", nargs="*", default=[], help="Paths to SQLite database files")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--inbrowser", action="store_true", help="Open in browser on launch")
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    valid_paths = [p for p in args.db_paths if os.path.exists(p)]

    if not valid_paths:
        logger.warning("No valid DB paths provided. Starting with empty state.")
        logger.info("Usage: python main.py path1.db path2.db [--port 7860] [--share]")

    app = AppBuilder(valid_paths).create_ui()
    app.launch(server_port=args.port, inbrowser=args.inbrowser, share=args.share)
