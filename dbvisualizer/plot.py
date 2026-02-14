import logging
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import matplotlib
import matplotlib.figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use('Agg')

logger = logging.getLogger(__name__)

# Global plot style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({
    'figure.figsize': (12, 7),
    'figure.dpi': 150,
    'font.size': 12,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'lines.linewidth': 2.5,
    'lines.markersize': 8,
})

SERIES_WARNING_THRESHOLD = 20
LEGEND_TRUNCATE_THRESHOLD = 20


@dataclass
class PlotConfig:
    chart_type: str = "LinePlot"
    x_col: str = ""
    y_cols: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    agg_method: str = "mean"


def _smart_sort(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Sort DataFrame by column using smart ordering:
    1. Try pd.to_datetime
    2. Try natsort for natural string ordering (e.g. "2020H2" < "2021H1")
    3. Fall back to original order
    """
    if col not in df.columns:
        return df

    # Try datetime parsing (strict: no fallback to dateutil per-element)
    try:
        dt_values = pd.to_datetime(df[col], format="mixed")
        return df.iloc[dt_values.argsort()]
    except (ValueError, TypeError):
        pass

    # Try natural sort via natsort
    try:
        from natsort import index_natsorted
        return df.iloc[index_natsorted(df[col])]
    except (ImportError, TypeError):
        pass

    # Fallback: simple sort_values
    try:
        return df.sort_values(by=col)
    except TypeError:
        return df


class PlotEngine:
    def render(self, df: pd.DataFrame, config: PlotConfig) -> Tuple[matplotlib.figure.Figure, Optional[str]]:
        """Render chart. Returns (figure, warning_message_or_None)."""
        logger.info(f"Rendering: {config.chart_type}, X={config.x_col}, Y={config.y_cols}, "
                     f"GroupBy={config.group_by}, Data rows={len(df)}")

        warning = None

        if df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, "Dataset is empty after filtering.\nCheck your filter selections.",
                    ha='center', va='center', fontsize=14, color='red')
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
            return fig, warning

        if not config.x_col or not config.y_cols:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, "Please configure X and Y axes", ha='center', va='center', fontsize=14)
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
            return fig, warning

        plot_df = df.copy()

        # Smart sort X axis
        plot_df = _smart_sort(plot_df, config.x_col)

        # Heatmap special path
        if config.chart_type == "HeatmapPlot":
            return self._heatmap_plot(plot_df, config), warning

        n_plots = len(config.y_cols)
        fig, axes = plt.subplots(n_plots, 1, figsize=(11, 6 * max(1, n_plots)), sharex=True, layout='constrained')
        if n_plots == 1:
            axes = [axes]

        for i, y_col in enumerate(config.y_cols):
            ax = axes[i]
            if isinstance(y_col, list):
                y_col = y_col[0]

            if y_col not in plot_df.columns:
                ax.text(0.5, 0.5, f"Column '{y_col}' not found", ha='center', color='red')
                continue

            # Ensure Y is numeric
            plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors='coerce')
            clean_df = plot_df.dropna(subset=[y_col])

            if clean_df.empty:
                ax.text(0.5, 0.5, f"Column '{y_col}' has no valid numeric data", ha='center', color='red')
                continue

            n_series = 0
            try:
                if config.group_by:
                    grp_cols = [c for c in config.group_by if c in clean_df.columns]
                    if grp_cols:
                        agg_df = clean_df.groupby(grp_cols + [config.x_col], as_index=False)[y_col].agg(config.agg_method)
                        n_series = agg_df.groupby(grp_cols).ngroups
                    else:
                        agg_df = clean_df.groupby(config.x_col, as_index=False)[y_col].agg(config.agg_method)
                        grp_cols = []

                    if config.chart_type == "LinePlot":
                        self._line_plot(ax, agg_df, config.x_col, y_col, grp_cols)
                    elif config.chart_type == "BarPlot":
                        self._bar_plot(ax, agg_df, config.x_col, y_col, grp_cols)
                    elif config.chart_type == "ScatterPlot":
                        self._scatter_plot(ax, agg_df, config.x_col, y_col, grp_cols)
                else:
                    single_df = clean_df.groupby(config.x_col, as_index=False)[y_col].agg(config.agg_method)
                    n_series = 1

                    if config.chart_type == "LinePlot":
                        ax.plot(single_df[config.x_col], single_df[y_col], marker='o', label=y_col)
                    elif config.chart_type == "BarPlot":
                        x_pos = range(len(single_df))
                        ax.bar(x_pos, single_df[y_col], label=y_col, alpha=0.8)
                        ax.set_xticks(x_pos)
                        ax.set_xticklabels(single_df[config.x_col], rotation=45, ha='right')
                    elif config.chart_type == "ScatterPlot":
                        ax.scatter(single_df[config.x_col], single_df[y_col], label=y_col, s=80)

            except Exception as e:
                logger.error(f"Plot Error for {y_col}: {e}", exc_info=True)
                ax.text(0.5, 0.5, f"Error: {str(e)}", ha='center', color='red')

            ax.set_xlabel(config.x_col, fontsize=12)
            ax.set_ylabel(y_col, fontsize=12)
            ax.set_title(f"{y_col} vs {config.x_col}", fontsize=14)
            self._apply_legend(ax, n_series)
            ax.grid(True, alpha=0.3)

            # Series warning
            if n_series > SERIES_WARNING_THRESHOLD:
                warning = (f"Warning: {n_series} series detected (>{SERIES_WARNING_THRESHOLD}). "
                           f"Consider narrowing your filters for better readability.")

        return fig, warning

    @staticmethod
    def _apply_legend(ax, n_series: int):
        """Adaptive legend positioning + truncation based on series count."""
        if n_series <= 0:
            return

        handles, labels = ax.get_legend_handles_labels()

        # Truncate if too many
        if len(handles) > LEGEND_TRUNCATE_THRESHOLD:
            from matplotlib.patches import Patch
            n_hidden = len(handles) - LEGEND_TRUNCATE_THRESHOLD
            handles = handles[:LEGEND_TRUNCATE_THRESHOLD]
            labels = labels[:LEGEND_TRUNCATE_THRESHOLD]
            handles.append(Patch(facecolor='none', edgecolor='none'))
            labels.append(f"... and {n_hidden} more")

        n_display = len(handles)
        if n_display <= 6:
            ax.legend(handles, labels, loc='upper right')
        elif n_display <= 15:
            ax.legend(handles, labels, bbox_to_anchor=(1.01, 1), loc='upper left', borderaxespad=0.)
        else:
            ncol = max(2, n_display // 8)
            ax.legend(handles, labels, bbox_to_anchor=(0.5, -0.15), loc='upper center',
                      ncol=ncol, borderaxespad=0.)

    def _line_plot(self, ax, df, x, y, g):
        if not g:
            ax.plot(df[x], df[y], marker='o', label=y)
            return
        for group_val, group_df in df.groupby(g):
            if isinstance(group_val, tuple):
                label = " | ".join([f"{k}={v}" for k, v in zip(g, group_val)])
            else:
                label = f"{g[0]}={group_val}"
            ax.plot(group_df[x], group_df[y], marker='o', label=label)

    def _bar_plot(self, ax, df, x, y, g):
        if not g:
            ax.bar(range(len(df)), df[y], alpha=0.8)
            ax.set_xticks(range(len(df)))
            ax.set_xticklabels(df[x], rotation=45, ha='right')
            return
        grouped = list(df.groupby(g))
        n_groups = len(grouped)
        if n_groups == 0:
            return
        width = 0.8 / n_groups
        x_vals = sorted(df[x].unique())
        x_map = {v: i for i, v in enumerate(x_vals)}

        for i, (group_val, group_df) in enumerate(grouped):
            if isinstance(group_val, tuple):
                label = " | ".join([f"{k}={v}" for k, v in zip(g, group_val)])
            else:
                label = f"{g[0]}={group_val}"
            offset = width * (i - n_groups / 2 + 0.5)
            positions = [x_map.get(v, 0) + offset for v in group_df[x]]
            ax.bar(positions, group_df[y], width, label=label, alpha=0.8)

        ax.set_xticks(range(len(x_vals)))
        ax.set_xticklabels(x_vals, rotation=45, ha='right')

    def _scatter_plot(self, ax, df, x, y, g):
        hue_col = g[0] if g else None
        style_col = g[1] if len(g) > 1 else None
        sns.scatterplot(data=df, x=x, y=y, hue=hue_col, style=style_col, s=80, ax=ax)

    def _heatmap_plot(self, df, config):
        if not config.group_by:
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "Heatmap requires at least 1 GroupBy column", ha='center')
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
            return fig

        try:
            pivoted = df.pivot_table(
                index=config.group_by[0],
                columns=config.x_col,
                values=config.y_cols[0],
                aggfunc=config.agg_method,
            )
            fig, ax = plt.subplots(figsize=(12, max(6, len(pivoted) * 0.5 + 2)), layout='constrained')
            sns.heatmap(pivoted, annot=True, cmap="viridis", fmt=".4f", ax=ax)
            return fig
        except Exception as e:
            logger.error(f"Heatmap error: {e}", exc_info=True)
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, f"Heatmap Error: {e}", ha='center', color='red')
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
            return fig

    @staticmethod
    def export_figure(fig: matplotlib.figure.Figure, fmt: str = "png") -> Optional[str]:
        """Export figure to a temp file. Returns the file path or None."""
        if fig is None:
            return None
        suffix = f".{fmt}"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        fig.savefig(tmp.name, format=fmt, bbox_inches="tight", dpi=200)
        tmp.close()
        logger.info(f"Exported chart to {tmp.name}")
        return tmp.name
