# DBVisualizer

A general-purpose SQLite visualization tool built with Gradio and Matplotlib.
Load any `.db` file, pick columns, apply filters, and generate interactive charts — all from a browser UI.

## Features

- **Multi-DB support** — load multiple SQLite databases, switch between tables
- **4 chart types** — Line, Bar, Scatter, Heatmap
- **Dynamic filters** — auto-generated checkbox filters for every categorical column
- **GroupBy + Aggregation** — group by one or more columns; aggregate with mean / max / min / sum / median
- **Aggregation insight** — status bar shows whether aggregation is collapsing rows and which ungrouped columns cause variation
- **Smart X-axis sorting** — auto-detects dates and natural-sorts period strings (e.g. `2023Q1 < 2023Q2 < 2024Q1`)
- **Adaptive legend** — repositions based on series count; truncates at 20 entries to preserve chart area
- **Series warning** — alerts when GroupBy produces >20 series
- **PNG / SVG export** — download charts via temp files
- **File upload** — upload `.db` / `.sqlite` / `.sqlite3` files directly from the browser
- **Packagable** — build scripts for Windows `.exe` and macOS `.dmg`

## Quick Start

### Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recommended package manager)

### Install & Run

```bash
# Clone the repository
git clone <repo-url>
cd DBVisualizer

# Install dependencies
uv sync

# Run with a database file
uv run python main.py examples/demo.db --inbrowser

# Or run without arguments (upload DB from the UI)
uv run python main.py --inbrowser
```

The app starts a local Gradio server at `http://localhost:7860`.

### CLI Options

| Flag | Description |
|------|-------------|
| `db_paths` | One or more paths to SQLite database files (positional) |
| `--port PORT` | Server port (default: `7860`) |
| `--inbrowser` | Automatically open in browser on launch |
| `--share` | Create a public Gradio share link |

## Project Structure

```
DBVisualizer/
├── main.py                    # CLI entry point
├── dbvisualizer/
│   ├── __init__.py            # Package exports
│   ├── __main__.py            # Packaged-build entry point (defaults to --inbrowser)
│   ├── data.py                # DBManager, ColumnInfo, TableAnalyzer, DataFilter
│   ├── plot.py                # PlotConfig, PlotEngine, smart sort, adaptive legend
│   └── ui.py                  # AppBuilder (Gradio UI + event handlers)
├── scripts/
│   ├── build_win.py           # Build Windows .exe (PyInstaller)
│   └── build_macos.sh         # Build macOS .app + .dmg (PyInstaller + hdiutil)
├── examples/
│   └── demo.db                # Sample database (Sales + SensorReadings tables)
├── pyproject.toml
└── uv.lock
```

### Module Overview

| Module | Responsibility |
|--------|---------------|
| `data.py` | Database connection, table loading, column type analysis, DataFrame filtering |
| `plot.py` | Chart rendering (Line/Bar/Scatter/Heatmap), X-axis smart sort, adaptive legend, figure export |
| `ui.py` | Gradio layout (Accordions for config/filters/export), event wiring, aggregation insight |

## Usage Guide

### 1. Load Data

Select a database from the **Database** dropdown, then pick a **Table**. The app auto-detects column types and populates the config dropdowns.

To add a new database, expand the **Add Database** accordion in the top bar and upload a `.db` / `.sqlite` / `.sqlite3` file.

### 2. Configure Chart

In the left sidebar:

- **Chart Type** — choose from LinePlot, BarPlot, ScatterPlot, HeatmapPlot
- **X Axis** — any column
- **Y Axis** — one or more numeric columns (creates subplots)
- **Group By** — one or more columns to split series
- **Aggregation** — how to aggregate Y values within each group

### 3. Apply Filters

Expand the **Filters** accordion. Each categorical column appears as a checkbox group (default: all selected). Deselect values to exclude them. Changes take effect when you click **DRAW CHART**.

### 4. Draw & Export

Click **DRAW CHART** to render. The status bar shows:
- Row count after filtering
- Active filter summary
- Aggregation insight (whether rows are being collapsed and by which columns)

Expand the **Export** accordion to download the chart as PNG or SVG.

## Building Distributables

### Windows (.exe)

```bash
uv run python scripts/build_win.py
```

Output: `dist/DBVisualizer/DBVisualizer.exe`

### macOS (.app + .dmg)

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

Output: `dist/DBVisualizer.app` and `dist/DBVisualizer.dmg`

Both scripts auto-install `pyinstaller` as a dev dependency if not present. The packaged build defaults to opening the browser on launch (`--no-browser` to disable).

## Demo Database

`examples/demo.db` contains two tables for testing:

| Table | Rows | Columns | Good for |
|-------|------|---------|----------|
| **Sales** | 72 | Region, Product, Quarter, Revenue, Units | GroupBy bar/line charts |
| **SensorReadings** | 360 | SensorID, Location, Temperature, Humidity, Pressure | Multi-series line, heatmap |

## Dependencies

| Package | Role |
|---------|------|
| [Gradio](https://www.gradio.app/) | Web UI framework |
| [Matplotlib](https://matplotlib.org/) | Chart rendering |
| [Seaborn](https://seaborn.pydata.org/) | Scatter plots and heatmaps |
| [Pandas](https://pandas.pydata.org/) | Data manipulation |
| [NumPy](https://numpy.org/) | Numeric operations |
| [natsort](https://github.com/SethMMorton/natsort) | Natural string sorting for X-axis |

## License

MIT
