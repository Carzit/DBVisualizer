import logging
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

SERIES_WARNING_THRESHOLD = 20
SPLIT_WARNING_THRESHOLD = 30

# Fixed per-subplot dimensions (pixels)
CELL_W = 520
CELL_H = 400


@dataclass
class PlotConfig:
    chart_type: str = "LinePlot"
    x_col: str = ""
    y_cols: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    split_by: List[str] = field(default_factory=list)
    agg_method: str = "mean"


def _smart_sort(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Sort DataFrame by column using smart ordering:
    1. Try pd.to_datetime
    2. Try natsort for natural string ordering (e.g. "2020H2" < "2021H1")
    3. Fall back to original order
    """
    if col not in df.columns:
        return df

    try:
        dt_values = pd.to_datetime(df[col], format="mixed")
        return df.iloc[dt_values.argsort()]
    except (ValueError, TypeError):
        pass

    try:
        from natsort import index_natsorted
        return df.iloc[index_natsorted(df[col])]
    except (ImportError, TypeError):
        pass

    try:
        return df.sort_values(by=col)
    except TypeError:
        return df


def _make_group_label(grp_cols: list, group_val) -> str:
    if isinstance(group_val, tuple):
        return " | ".join(f"{k}={v}" for k, v in zip(grp_cols, group_val))
    return f"{grp_cols[0]}={group_val}"


def _make_split_label(split_cols: list, split_key) -> str:
    if isinstance(split_key, tuple):
        return " | ".join(f"{k}={v}" for k, v in zip(split_cols, split_key))
    return f"{split_cols[0]}={split_key}"


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=16, color="red"))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


class PlotEngine:
    def render(self, df: pd.DataFrame, config: PlotConfig) -> Tuple[go.Figure, Optional[str]]:
        """Render chart. Returns (plotly figure, warning_message_or_None)."""
        logger.info(f"Rendering: {config.chart_type}, X={config.x_col}, Y={config.y_cols}, "
                     f"GroupBy={config.group_by}, SplitBy={config.split_by}, Data rows={len(df)}")

        warning = None

        if df.empty:
            return _empty_fig("Dataset is empty after filtering.\nCheck your filter selections."), warning

        if not config.x_col or not config.y_cols:
            return _empty_fig("Please configure X and Y axes"), warning

        plot_df = df.copy()
        plot_df = _smart_sort(plot_df, config.x_col)

        # Heatmap special path (no split_by support)
        if config.chart_type == "HeatmapPlot":
            return self._heatmap_plot(plot_df, config), warning

        # Determine split groups
        split_cols = [c for c in config.split_by if c in plot_df.columns]
        if split_cols:
            split_groups = list(plot_df.groupby(split_cols, sort=True))
            n_split = len(split_groups)
            if n_split > SPLIT_WARNING_THRESHOLD:
                warning = (f"Warning: Split By produces {n_split} columns "
                           f"(>{SPLIT_WARNING_THRESHOLD}). Consider fewer split values.")
        else:
            split_groups = [(None, plot_df)]
            n_split = 1

        n_rows = len(config.y_cols)
        n_cols = n_split

        # Build subplot titles: top row gets split labels
        subplot_titles = []
        for i, y_col in enumerate(config.y_cols):
            for j, (split_key, _) in enumerate(split_groups):
                if n_split == 1:
                    subplot_titles.append(f"{y_col} vs {config.x_col}")
                elif i == 0:
                    subplot_titles.append(_make_split_label(split_cols, split_key))
                else:
                    subplot_titles.append("")

        fig = make_subplots(
            rows=n_rows, cols=n_cols,
            shared_xaxes=True, shared_yaxes=True,
            subplot_titles=subplot_titles,
            vertical_spacing=0.08 if n_rows > 1 else 0.05,
            horizontal_spacing=0.04 if n_cols > 1 else 0.05,
        )

        # Track which legend groups have been shown (to avoid duplicate entries)
        shown_legend_groups = set()

        for j, (split_key, split_df) in enumerate(split_groups):
            for i, y_col in enumerate(config.y_cols):
                if isinstance(y_col, list):
                    y_col = y_col[0]

                if y_col not in split_df.columns:
                    fig.add_annotation(
                        text=f"Column '{y_col}' not found", row=i + 1, col=j + 1,
                        xref="paper", yref="paper", showarrow=False,
                        font=dict(color="red"),
                    )
                    continue

                cell_df = split_df.copy()
                cell_df[y_col] = pd.to_numeric(cell_df[y_col], errors='coerce')
                clean_df = cell_df.dropna(subset=[y_col])

                if clean_df.empty:
                    fig.add_annotation(
                        text="No valid data", row=i + 1, col=j + 1,
                        xref="paper", yref="paper", showarrow=False,
                        font=dict(color="red"),
                    )
                    continue

                n_series = 0
                try:
                    grp_cols = [c for c in config.group_by if c in clean_df.columns] if config.group_by else []
                    if grp_cols:
                        agg_df = clean_df.groupby(grp_cols + [config.x_col], as_index=False)[y_col].agg(config.agg_method)
                        n_series = agg_df.groupby(grp_cols).ngroups

                        for group_val, group_df in agg_df.groupby(grp_cols):
                            label = _make_group_label(grp_cols, group_val)
                            show_legend = label not in shown_legend_groups
                            shown_legend_groups.add(label)
                            self._add_trace(fig, group_df, config.x_col, y_col,
                                            config.chart_type, label, show_legend,
                                            row=i + 1, col=j + 1)
                    else:
                        agg_df = clean_df.groupby(config.x_col, as_index=False)[y_col].agg(config.agg_method)
                        n_series = 1
                        label = y_col
                        show_legend = label not in shown_legend_groups
                        shown_legend_groups.add(label)
                        self._add_trace(fig, agg_df, config.x_col, y_col,
                                        config.chart_type, label, show_legend,
                                        row=i + 1, col=j + 1)

                except Exception as e:
                    logger.error(f"Plot Error for {y_col}: {e}", exc_info=True)
                    fig.add_annotation(
                        text=f"Error: {str(e)}", row=i + 1, col=j + 1,
                        xref="paper", yref="paper", showarrow=False,
                        font=dict(color="red"),
                    )

                if n_series > SERIES_WARNING_THRESHOLD:
                    warning = (f"Warning: {n_series} series detected (>{SERIES_WARNING_THRESHOLD}). "
                               f"Consider narrowing your filters for better readability.")

        # Axis labels: only on edges
        for i, y_col in enumerate(config.y_cols):
            fig.update_yaxes(title_text=y_col, row=i + 1, col=1)
        for j in range(n_cols):
            fig.update_xaxes(title_text=config.x_col, row=n_rows, col=j + 1)

        fig.update_layout(
            width=CELL_W * n_cols,
            height=CELL_H * n_rows,
            template="plotly_white",
            legend=dict(
                bgcolor="rgba(255,255,255,0.5)",
                borderwidth=0,
            ),
            margin=dict(l=60, r=30, t=40, b=50),
        )

        return fig, warning

    @staticmethod
    def _add_trace(fig: go.Figure, df: pd.DataFrame, x_col: str, y_col: str,
                   chart_type: str, label: str, show_legend: bool,
                   row: int, col: int):
        """Add a single trace to the subplot grid."""
        x = df[x_col]
        y = df[y_col]

        if chart_type == "LinePlot":
            fig.add_trace(
                go.Scatter(x=x, y=y, mode='lines+markers', name=label,
                           legendgroup=label, showlegend=show_legend),
                row=row, col=col,
            )
        elif chart_type == "BarPlot":
            fig.add_trace(
                go.Bar(x=x, y=y, name=label,
                       legendgroup=label, showlegend=show_legend),
                row=row, col=col,
            )
        elif chart_type == "ScatterPlot":
            fig.add_trace(
                go.Scatter(x=x, y=y, mode='markers', name=label,
                           legendgroup=label, showlegend=show_legend,
                           marker=dict(size=8)),
                row=row, col=col,
            )

    def _heatmap_plot(self, df: pd.DataFrame, config: PlotConfig) -> go.Figure:
        if not config.group_by:
            return _empty_fig("Heatmap requires at least 1 GroupBy column")

        try:
            pivoted = df.pivot_table(
                index=config.group_by[0],
                columns=config.x_col,
                values=config.y_cols[0],
                aggfunc=config.agg_method,
            )
            fig = go.Figure(data=go.Heatmap(
                z=pivoted.values,
                x=[str(c) for c in pivoted.columns],
                y=[str(r) for r in pivoted.index],
                colorscale="Viridis",
                texttemplate="%{z:.4f}",
            ))
            fig.update_layout(
                template="plotly_white",
                width=max(600, len(pivoted.columns) * 60 + 150),
                height=max(400, len(pivoted.index) * 30 + 150),
                margin=dict(l=60, r=30, t=40, b=50),
            )
            return fig
        except Exception as e:
            logger.error(f"Heatmap error: {e}", exc_info=True)
            return _empty_fig(f"Heatmap Error: {e}")

    @staticmethod
    def export_figure(fig: go.Figure, fmt: str = "png") -> Optional[str]:
        """Export figure to a temp file. Returns the file path or None."""
        if fig is None:
            return None
        suffix = f".{fmt}"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()
        if fmt == "svg":
            fig.write_image(tmp.name, format="svg")
        else:
            fig.write_image(tmp.name, format="png", scale=2)
        logger.info(f"Exported chart to {tmp.name}")
        return tmp.name
