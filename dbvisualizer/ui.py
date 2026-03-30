import logging
from typing import List

import pandas as pd
import gradio as gr

from dbvisualizer.data import DBManager, TableAnalyzer, DataFilter, ColumnInfo
from dbvisualizer.plot import PlotConfig, PlotEngine, _empty_fig

logger = logging.getLogger(__name__)


def _aggregation_insight(df: pd.DataFrame, x_col: str, y_cols: list,
                         group_by: list, agg_method: str) -> str:
    """Analyze whether aggregation actually collapses rows, and if so, which
    ungrouped columns are causing multiple values per group."""
    if df.empty or not x_col or not y_cols:
        return ""
    valid_y = [c for c in y_cols if c in df.columns]
    if not valid_y:
        return ""

    key_cols = [c for c in ([x_col] + group_by) if c in df.columns]
    if not key_cols:
        return ""

    try:
        group_sizes = df.groupby(key_cols, sort=False).size()
    except (ValueError, TypeError):
        return ""

    max_size = int(group_sizes.max())
    if max_size <= 1:
        return f"**Aggregation ({agg_method}):** not needed — each group already has a single value."

    # Aggregation IS happening — find which other columns vary within groups
    ignored = {s.lower() for s in TableAnalyzer.IGNORED_COLUMNS}
    other_cols = [c for c in df.columns
                  if c not in set(key_cols + valid_y)
                  and not any(ig in c.lower() for ig in ignored)]
    varying = []
    for col in other_cols:
        try:
            nunique = df.groupby(key_cols, sort=False)[col].nunique()
            if nunique.max() > 1:
                varying.append(f"`{col}`")
        except (ValueError, TypeError):
            continue

    mean_size = group_sizes.mean()
    parts = [f"**Aggregation ({agg_method}):** ~{mean_size:.1f} rows per group"]
    if varying:
        parts.append(f"columns varying within groups: {', '.join(varying[:8])}")
        if len(varying) > 8:
            parts.append(f"and {len(varying) - 8} more")
    return " — ".join(parts)


class AppBuilder:
    def __init__(self, db_paths: List[str] = None):
        self.db_manager = DBManager(db_paths)
        self.analyzer = TableAnalyzer()
        self.plot_engine = PlotEngine()

    def create_ui(self):
        dbs = self.db_manager.list_dbs()
        init_db = dbs[0] if dbs else None

        init_df = pd.DataFrame()
        init_tables: list = []
        init_table = None

        if init_db:
            init_tables = self.db_manager.list_tables(init_db)
            if init_tables:
                init_table = init_tables[0]
                init_df = self.db_manager.load_table(init_db, init_table)

        with gr.Blocks(title="DB Visualizer") as app:
            gr.Markdown("## DB Visualizer")

            # ====== State ======
            df_state = gr.State(init_df)
            fig_state = gr.State()
            filter_state = gr.State({})
            all_values_state = gr.State({})

            # ====== Top Bar: Dataset operations ======
            with gr.Row(variant="panel"):
                db_dropdown = gr.Dropdown(choices=dbs, value=init_db, label="Database", scale=3)
                table_dropdown = gr.Dropdown(choices=init_tables, value=init_table, label="Table", scale=3)
                with gr.Accordion("Add Database", open=False):
                    db_upload = gr.File(
                        file_types=[".db", ".sqlite", ".sqlite3"],
                        label="Upload .db / .sqlite file",
                    )

            with gr.Row():
                # ====== Left: Chart operations ======
                with gr.Column(scale=1):
                    btn_generate = gr.Button("DRAW CHART", variant="primary")

                    # --- Chart Config (open) ---
                    with gr.Accordion("Chart Config", open=True):
                        chart_type = gr.Dropdown(
                            choices=["LinePlot", "BarPlot", "HeatmapPlot", "ScatterPlot"],
                            value="LinePlot", label="Chart Type", interactive=True,
                        )
                        x_axis = gr.Dropdown(choices=[], label="X Axis", interactive=True)
                        y_axis = gr.Dropdown(choices=[], label="Y Axis", multiselect=True, interactive=True)
                        group_by = gr.Dropdown(choices=[], label="Group By", multiselect=True, interactive=True)
                        split_by = gr.Dropdown(choices=[], label="Split By", multiselect=True, interactive=True)
                        agg_method = gr.Dropdown(
                            ["mean", "max", "min", "sum", "median", "first", "last"],
                            value="mean", label="Aggregation", interactive=True,
                        )

                    # --- Filters (open) ---
                    with gr.Accordion("Filters", open=True):
                        gr.Markdown(
                            "*Deselect values to filter. Changes take effect on **DRAW CHART**.*",
                            elem_classes=["filter-hint"],
                        )

                        @gr.render(inputs=[df_state], triggers=[df_state.change])
                        def render_filters(df):
                            if not isinstance(df, pd.DataFrame) or df.empty:
                                gr.Markdown("*Load a table to see filters*")
                                return

                            infos = self.analyzer.analyze(df)
                            filterable = [c for c in infos if c.unique_values is not None]

                            if not filterable:
                                gr.Markdown("*No filterable columns found*")
                                return

                            for col_info in filterable:
                                str_choices = [str(v) for v in col_info.unique_values]

                                cb = gr.CheckboxGroup(
                                    choices=str_choices,
                                    value=str_choices,
                                    label=f"{col_info.name} ({len(str_choices)} values)",
                                    interactive=True,
                                )

                                def make_handler(col_name):
                                    def handler(selected, current_filters):
                                        if current_filters is None:
                                            current_filters = {}
                                        current_filters[col_name] = selected if selected else []
                                        logger.debug(f"Filter updated: {col_name} -> "
                                                     f"{len(selected) if selected else 0} values selected")
                                        return current_filters
                                    return handler

                                cb.change(
                                    make_handler(col_info.name),
                                    inputs=[cb, filter_state],
                                    outputs=[filter_state],
                                )

                # ====== Right: Output ======
                with gr.Column(scale=3):
                    plot_output = gr.Plot(label="Chart Preview")
                    status_text = gr.Markdown("", visible=True)

                    # --- Export (collapsed) ---
                    with gr.Accordion("Export", open=True):
                        with gr.Row():
                            export_png = gr.Button("Download PNG", size="sm")
                            export_svg = gr.Button("Download SVG", size="sm")
                        dl_file = gr.File(visible=False, label="Exported File")

                    gr.Markdown("### Data Table (first 50 rows after filtering)")
                    data_table = gr.Dataframe(value=init_df.head(50), interactive=False)

            # ==========================
            # Logic (Event Handlers)
            # ==========================

            # --- Add DB (file upload) ---
            def handle_upload_db(file):
                if file is None:
                    return gr.Dropdown()
                path = file if isinstance(file, str) else file.name
                new_list = self.db_manager.add_db(path)
                return gr.Dropdown(choices=new_list, value=path, interactive=True)

            db_upload.change(handle_upload_db, inputs=[db_upload], outputs=[db_dropdown])

            # --- DB Change ---
            def handle_db_change(path):
                tables = self.db_manager.list_tables(path)
                first = tables[0] if tables else None
                return gr.Dropdown(choices=tables, value=first, interactive=True)

            db_dropdown.change(handle_db_change, inputs=[db_dropdown], outputs=[table_dropdown])

            # --- Table Change ---
            def handle_table_change(db_path, table_name):
                df = self.db_manager.load_table(db_path, table_name)

                if df.empty:
                    return (
                        pd.DataFrame(),
                        {},
                        {},
                        gr.Dropdown(choices=[], value=None),
                        gr.Dropdown(choices=[], value=[]),
                        gr.Dropdown(choices=[], value=[]),
                        gr.Dropdown(choices=[], value=[]),
                        pd.DataFrame(),
                        None,
                        None,
                        "*No data*",
                    )

                infos = self.analyzer.analyze(df)
                all_cols = [c.name for c in infos]
                numeric_cols = [c.name for c in infos if "numeric" in c.dtype]

                dx = "Period" if "Period" in all_cols else (all_cols[0] if all_cols else None)

                dy: list = []
                if numeric_cols:
                    score_cols = [n for n in numeric_cols if "score" in n.lower()]
                    dy = [score_cols[0]] if score_cols else [numeric_cols[0]]

                init_all_values: dict = {}
                init_filters: dict = {}
                for c in infos:
                    if c.unique_values is not None:
                        str_vals = [str(v) for v in c.unique_values]
                        init_all_values[c.name] = str_vals
                        init_filters[c.name] = str_vals

                status = (f"**Loaded:** {len(df)} rows, {len(df.columns)} columns. "
                          f"**Filterable fields:** {len(init_all_values)}")

                return (
                    df,
                    init_filters,
                    init_all_values,
                    gr.Dropdown(choices=all_cols, value=dx, interactive=True),
                    gr.Dropdown(choices=numeric_cols, value=dy, interactive=True),
                    gr.Dropdown(choices=all_cols, value=[], interactive=True),
                    gr.Dropdown(choices=all_cols, value=[], interactive=True),
                    df.head(50),
                    None,
                    None,
                    status,
                )

            table_dropdown.change(
                handle_table_change,
                inputs=[db_dropdown, table_dropdown],
                outputs=[df_state, filter_state, all_values_state, x_axis, y_axis, group_by,
                         split_by, data_table, plot_output, fig_state, status_text],
            )

            # --- DRAW CHART ---
            def on_generate_click(df, x, y, g, s, agg, ctype, filters, all_values):
                logger.info(f"DRAW CHART: X={x}, Y={y}, GroupBy={g}, SplitBy={s}, Agg={agg}, Chart={ctype}")

                if not isinstance(df, pd.DataFrame) or df.empty:
                    return _empty_fig("No data loaded"), None, pd.DataFrame(), "*No data loaded*"

                filtered_df = DataFilter.apply(df, filters, all_values)

                y_list = y if isinstance(y, list) else ([y] if y else [])
                g_list = g if isinstance(g, list) else ([g] if g else [])
                s_list = s if isinstance(s, list) else ([s] if s else [])

                config = PlotConfig(
                    chart_type=ctype,
                    x_col=x,
                    y_cols=y_list,
                    group_by=g_list,
                    split_by=s_list,
                    agg_method=agg,
                )

                fig, warning = self.plot_engine.render(filtered_df, config)

                n_active = 0
                filter_details = []
                for col, selected in filters.items():
                    if selected is not None and all_values and col in all_values:
                        if set(str(v) for v in selected) != set(str(v) for v in all_values[col]):
                            n_active += 1
                            filter_details.append(f"`{col}`: {len(selected)}/{len(all_values[col])}")

                status = f"**Showing:** {len(filtered_df)} / {len(df)} rows"
                if n_active > 0:
                    status += f" | **Active filters ({n_active}):** " + ", ".join(filter_details)
                else:
                    status += " | No active filters (all values selected)"

                # Aggregation insight
                agg_info = _aggregation_insight(filtered_df, x, y_list, g_list, agg)
                if agg_info:
                    status += f"\n\n{agg_info}"

                if warning:
                    status += f"\n\n**{warning}**"

                return fig, fig, filtered_df.head(50), status

            btn_generate.click(
                on_generate_click,
                inputs=[df_state, x_axis, y_axis, group_by, split_by, agg_method, chart_type,
                        filter_state, all_values_state],
                outputs=[plot_output, fig_state, data_table, status_text],
            )

            # --- Export PNG ---
            def handle_export_png(fig):
                return PlotEngine.export_figure(fig, fmt="png")

            export_png.click(handle_export_png, inputs=fig_state, outputs=dl_file)

            # --- Export SVG ---
            def handle_export_svg(fig):
                return PlotEngine.export_figure(fig, fmt="svg")

            export_svg.click(handle_export_svg, inputs=fig_state, outputs=dl_file)

            dl_file.change(lambda: gr.update(visible=True), outputs=dl_file)

            # --- Auto Load ---
            if init_db and init_table:
                app.load(
                    fn=handle_table_change,
                    inputs=[db_dropdown, table_dropdown],
                    outputs=[df_state, filter_state, all_values_state, x_axis, y_axis, group_by,
                             data_table, plot_output, fig_state, status_text],
                )

        return app
