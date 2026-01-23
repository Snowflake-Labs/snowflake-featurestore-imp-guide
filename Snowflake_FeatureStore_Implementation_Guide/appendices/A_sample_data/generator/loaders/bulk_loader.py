"""
Scalable bulk data loader using Parquet files and COPY INTO.

This module provides efficient loading for large datasets by:
1. Writing data to Parquet files in chunks (memory-efficient)
2. Uploading to Snowflake internal stage
3. Using COPY INTO for fast parallel loading
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass
class BulkLoaderConfig:
    """Configuration for bulk loading."""
    chunk_size: int = 100_000  # Rows per Parquet file
    compression: str = "snappy"  # Parquet compression
    stage_name: str = "DATA_LOAD_STAGE"
    temp_dir: Optional[Path] = None  # Local temp directory for Parquet files
    cleanup_local: bool = True  # Delete local files after upload
    cleanup_stage: bool = True  # Clear stage after COPY INTO


class BulkLoader:
    """
    Scalable bulk data loader for Snowflake.
    
    Usage:
        loader = BulkLoader(session, config)
        loader.load_table(
            table_name="EVENTS",
            data_generator=generate_events_iter(config),
            schema=EVENT_SCHEMA,
        )
    """
    
    def __init__(self, session, config: BulkLoaderConfig = None):
        """
        Initialize bulk loader.
        
        Args:
            session: Snowpark Session
            config: BulkLoaderConfig (optional)
        """
        self.session = session
        self.config = config or BulkLoaderConfig()
        self._setup_stage()
    
    def _setup_stage(self):
        """Create internal stage if not exists."""
        self.session.sql(f"""
            CREATE STAGE IF NOT EXISTS {self.config.stage_name}
            FILE_FORMAT = (TYPE = PARQUET)
        """).collect()
    
    def load_table(
        self,
        table_name: str,
        data_generator: Iterator[Dict[str, Any]],
        total_rows: int = None,
        mode: str = "overwrite",  # "overwrite" or "append"
    ) -> int:
        """
        Load data to Snowflake table using chunked Parquet + COPY INTO.
        
        Args:
            table_name: Target table name
            data_generator: Iterator yielding row dicts
            total_rows: Expected total rows (for progress display)
            mode: "overwrite" to replace table, "append" to add rows
            
        Returns:
            Number of rows loaded
        """
        # Create temp directory for Parquet files
        temp_dir = self.config.temp_dir or Path(tempfile.mkdtemp(prefix="sf_bulk_"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Write Parquet files in chunks
            parquet_files = self._write_parquet_chunks(
                data_generator, 
                temp_dir, 
                table_name,
                total_rows
            )
            
            if not parquet_files:
                print(f"  No data to load for {table_name}")
                return 0
            
            # Upload to stage
            self._upload_to_stage(parquet_files, table_name)
            
            # Create/replace table and COPY INTO
            rows_loaded = self._copy_into_table(table_name, mode)
            
            return rows_loaded
            
        finally:
            # Cleanup
            if self.config.cleanup_local:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            if self.config.cleanup_stage:
                self._cleanup_stage(table_name)
    
    def _write_parquet_chunks(
        self,
        data_generator: Iterator[Dict[str, Any]],
        output_dir: Path,
        table_name: str,
        total_rows: int = None,
    ) -> List[Path]:
        """Write data to Parquet files in chunks."""
        parquet_files = []
        chunk = []
        chunk_num = 0
        rows_written = 0
        
        for row in data_generator:
            chunk.append(row)
            
            if len(chunk) >= self.config.chunk_size:
                # Write chunk to Parquet
                file_path = output_dir / f"{table_name.lower()}_{chunk_num:05d}.parquet"
                self._write_parquet_file(chunk, file_path)
                parquet_files.append(file_path)
                
                rows_written += len(chunk)
                if total_rows:
                    pct = rows_written / total_rows * 100
                    print(f"  Generated {rows_written:,}/{total_rows:,} rows ({pct:.1f}%)")
                else:
                    print(f"  Generated {rows_written:,} rows")
                
                chunk = []
                chunk_num += 1
        
        # Write final chunk
        if chunk:
            file_path = output_dir / f"{table_name.lower()}_{chunk_num:05d}.parquet"
            self._write_parquet_file(chunk, file_path)
            parquet_files.append(file_path)
            rows_written += len(chunk)
            print(f"  Generated {rows_written:,} rows (complete)")
        
        return parquet_files
    
    def _write_parquet_file(self, rows: List[Dict], file_path: Path):
        """Write a list of dicts to a Parquet file."""
        # Convert to PyArrow table
        table = pa.Table.from_pylist(rows)
        
        # Write with compression
        pq.write_table(
            table,
            file_path,
            compression=self.config.compression,
        )
    
    def _upload_to_stage(self, parquet_files: List[Path], table_name: str):
        """Upload Parquet files to Snowflake stage."""
        stage_path = f"@{self.config.stage_name}/{table_name.lower()}/"
        
        print(f"  Uploading {len(parquet_files)} files to stage...")
        
        for file_path in parquet_files:
            # Use PUT command for upload
            self.session.file.put(
                str(file_path),
                stage_path,
                auto_compress=False,
                overwrite=True,
            )
    
    def _copy_into_table(self, table_name: str, mode: str) -> int:
        """Execute COPY INTO to load data from stage."""
        stage_path = f"@{self.config.stage_name}/{table_name.lower()}/"
        
        # For overwrite mode, we need to create/replace the table first
        if mode == "overwrite":
            # Infer schema from Parquet and create table
            print(f"  Creating table {table_name}...")
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {table_name}
                USING TEMPLATE (
                    SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
                    FROM TABLE(INFER_SCHEMA(
                        LOCATION => '{stage_path}',
                        FILE_FORMAT => 'PARQUET'
                    ))
                )
            """).collect()
        
        # Execute COPY INTO
        print(f"  Loading data via COPY INTO...")
        result = self.session.sql(f"""
            COPY INTO {table_name}
            FROM {stage_path}
            FILE_FORMAT = (TYPE = PARQUET)
            MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            PURGE = FALSE
        """).collect()
        
        # Get rows loaded from result
        rows_loaded = sum(r["rows_loaded"] for r in result if "rows_loaded" in r.as_dict())
        
        return rows_loaded
    
    def _cleanup_stage(self, table_name: str):
        """Remove files from stage after loading."""
        stage_path = f"@{self.config.stage_name}/{table_name.lower()}/"
        self.session.sql(f"REMOVE {stage_path}").collect()


def iter_chunks(data: List[Dict], chunk_size: int) -> Generator[List[Dict], None, None]:
    """Iterate over data in chunks."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]
