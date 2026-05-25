"""
任务状态数据结构与序列化支持。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
import time


VALID_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


@dataclass
class TaskInfo:
    id: str
    url: str
    status: str = "pending"
    retries: int = 0
    result: Optional[dict] = None
    created_at: float = None
    updated_at: float = None

    def __post_init__(self):
        now = time.time()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def update_status(self, new_status: str, result: Optional[dict] = None) -> None:
        if new_status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {new_status}")
        self.status = new_status
        self.updated_at = time.time()
        if result is not None:
            self.result = result
