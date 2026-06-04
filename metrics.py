import os
import json
import asyncio
from typing import Dict, Any, Optional
from loguru import logger

class MetricsTracker:
    """Async-safe tracker for bot performance and audit metrics."""

    def __init__(self, filepath: str = "metrics.json"):
        self.filepath = filepath
        self.lock = asyncio.Lock()
        # Nested structure: guild_id -> metric_name -> value
        self.data: Dict[str, Dict[str, Any]] = {}
        self._load_from_json()
        self._flush_task: Optional[asyncio.Task[Any]] = None

    def start_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Starts the auto-flush loop in the event loop."""
        self._flush_task = loop.create_task(self._auto_flush_loop())

    def cancel_loop(self) -> None:
        """Stops the auto-flush background loop."""
        if self._flush_task:
            self._flush_task.cancel()

    def _load_from_json(self) -> None:
        """Loads cached metrics from filepath if exists."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load metrics from file: {e}")

    async def increment(self, metric_name: str, guild_id: str, value: int = 1) -> None:
        """Increments a guild metric counter."""
        async with self.lock:
            g_data = self.data.setdefault(str(guild_id), {})
            current = g_data.get(metric_name, 0)
            if not isinstance(current, (int, float)):
                current = 0
            g_data[metric_name] = current + value

    async def set(self, metric_name: str, guild_id: str, value: Any) -> None:
        """Sets a metric to an absolute value."""
        async with self.lock:
            g_data = self.data.setdefault(str(guild_id), {})
            g_data[metric_name] = value

    async def get(self, metric_name: str, guild_id: str) -> Any:
        """Retrieves a metric key value for a guild."""
        async with self.lock:
            return self.data.get(str(guild_id), {}).get(metric_name, 0)

    async def get_all(self, guild_id: str) -> Dict[str, Any]:
        """Returns all registered metrics for a guild."""
        async with self.lock:
            return dict(self.data.get(str(guild_id), {}))

    async def export_to_json(self) -> None:
        """Writes current metrics state to disk."""
        async with self.lock:
            try:
                # Write to temp file first to ensure atomic updates
                temp_file = f"{self.filepath}.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
                os.replace(temp_file, self.filepath)
            except Exception as e:
                logger.error(f"Failed to export metrics to JSON: {e}")

    async def _auto_flush_loop(self) -> None:
        """Background loop flushing metrics to disk every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                await self.export_to_json()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics auto-flush loop: {e}")
