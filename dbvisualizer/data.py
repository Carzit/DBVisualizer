import os
import sqlite3
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

import pandas as pd

logger = logging.getLogger(__name__)


class DBManager:
    def __init__(self, db_paths: List[str] = None):
        self.db_paths: List[str] = sorted(list(set(db_paths or [])))

    def add_db(self, path: str) -> List[str]:
        if path and os.path.exists(path) and path not in self.db_paths:
            self.db_paths.append(path)
            self.db_paths.sort()
        return self.db_paths

    def list_dbs(self) -> List[str]:
        return self.db_paths

    def list_tables(self, db_path: str) -> List[str]:
        if not db_path or not os.path.exists(db_path):
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
            return sorted(tables)
        except sqlite3.Error as e:
            logger.error(f"Error listing tables: {e}")
            return []

    def load_table(self, db_path: str, table_name: str) -> pd.DataFrame:
        if not db_path or not table_name:
            return pd.DataFrame()
        try:
            with sqlite3.connect(db_path) as conn:
                df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
            logger.info(f"Loaded table '{table_name}' with {len(df)} rows, {len(df.columns)} columns.")
            return df
        except (sqlite3.Error, pd.errors.DatabaseError) as e:
            logger.error(f"Error loading table: {e}")
            return pd.DataFrame()


@dataclass
class ColumnInfo:
    name: str
    dtype: str  # "numeric", "categorical", "categorical_numeric", "text"
    unique_values: Optional[List[Any]] = None


class TableAnalyzer:
    CATEGORICAL_THRESHOLD = 50
    UNIQUENESS_RATIO_LIMIT = 0.8
    AVG_VALUE_LENGTH_LIMIT = 50
    IGNORED_COLUMNS = ["Timestamp", "Config_File", "id", "ID", "Unnamed"]

    def analyze(self, df: pd.DataFrame) -> List[ColumnInfo]:
        infos = []
        if df.empty:
            return infos

        n_rows = len(df)

        for col in df.columns:
            if any(ignored.lower() in col.lower() for ignored in self.IGNORED_COLUMNS):
                continue

            sample_series = df[col].copy()
            try:
                sample_series = pd.to_numeric(sample_series, errors='coerce')
            except (ValueError, TypeError):
                pass

            unique_vals = df[col].dropna().unique()
            n_unique = len(unique_vals)

            col_type = "text"
            is_numeric = pd.api.types.is_numeric_dtype(sample_series) or \
                         (sample_series.notna().sum() > 0 and sample_series.dtype != object)

            # Check if column looks like an identifier (almost all values unique)
            is_id_like = (n_rows > 5
                          and n_unique > 0
                          and n_unique / n_rows > self.UNIQUENESS_RATIO_LIMIT)

            # Check if values are too long for checkbox buttons
            avg_len = df[col].dropna().astype(str).str.len().mean()
            is_long_text = avg_len > self.AVG_VALUE_LENGTH_LIMIT

            if is_numeric:
                if (n_unique <= self.CATEGORICAL_THRESHOLD
                        and n_unique > 0
                        and not is_id_like):
                    col_type = "categorical_numeric"
                else:
                    col_type = "numeric"
            elif (n_unique <= self.CATEGORICAL_THRESHOLD
                  and not is_id_like
                  and not is_long_text):
                col_type = "categorical"
            else:
                col_type = "text"

            info = ColumnInfo(name=col, dtype=col_type)
            if col_type in ("categorical", "categorical_numeric"):
                try:
                    info.unique_values = sorted(unique_vals.tolist())
                except TypeError:
                    info.unique_values = unique_vals.tolist()

            infos.append(info)
        return infos


class DataFilter:
    """
    filters format: {col_name: [selected_val1, selected_val2, ...], ...}
    - If a column's selected list is None or equals the full set, that column is not filtered.
    - If a column's selected list is empty [], all rows are excluded (result is empty).
    """

    @staticmethod
    def apply(df: pd.DataFrame, filters: Dict[str, List[Any]],
              all_values: Dict[str, List[Any]] = None) -> pd.DataFrame:
        if df.empty or not filters:
            return df

        mask = pd.Series([True] * len(df), index=df.index)
        active_count = 0

        for col, selected in filters.items():
            if col not in df.columns:
                continue
            if selected is None:
                continue

            # If all_values provided, check if all are selected (skip if so)
            if all_values and col in all_values:
                if set(str(v) for v in selected) == set(str(v) for v in all_values[col]):
                    continue

            if len(selected) == 0:
                logger.debug(f"Filter '{col}': empty selection -> no rows")
                return df.iloc[0:0]

            # Type conversion
            col_dtype = df[col].dtype
            target_vals = list(selected)
            try:
                if pd.api.types.is_integer_dtype(col_dtype):
                    target_vals = [int(float(x)) for x in target_vals]
                elif pd.api.types.is_float_dtype(col_dtype):
                    target_vals = [float(x) for x in target_vals]
                else:
                    target_vals = [str(x) for x in target_vals]
                    df_col_str = df[col].astype(str)
                    current_mask = df_col_str.isin(target_vals)
                    mask &= current_mask
                    active_count += 1
                    logger.debug(f"Filter '{col}' in {target_vals[:5]}{'...' if len(target_vals) > 5 else ''}: "
                                 f"matched {current_mask.sum()} rows")
                    continue
            except (ValueError, TypeError):
                pass

            current_mask = df[col].isin(target_vals)
            mask &= current_mask
            active_count += 1
            logger.debug(f"Filter '{col}' in {target_vals[:5]}{'...' if len(target_vals) > 5 else ''}: "
                         f"matched {current_mask.sum()} rows")

        final_df = df[mask]
        logger.info(f"Filter Result: {active_count} active filters, {len(final_df)} / {len(df)} rows remaining.")
        return final_df
