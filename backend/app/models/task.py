"""
任务状态管理
用于跟踪长时间运行的任务（如图谱构建）
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from ..utils.locale import t


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待中
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败


_MAX_SUMMARY_DEPTH = 3
_MAX_SUMMARY_ITEMS = 24
_MAX_LIST_ITEMS = 8
_MAX_STRING_LENGTH = 500
_HEAVY_PAYLOAD_KEYS = {
    "all_actions",
    "candles",
    "chain",
    "children",
    "data",
    "edges",
    "feature_preparation",
    "grid",
    "history",
    "latest_by_security",
    "nodes",
    "option_exposures",
    "prepared_options",
    "profiles",
    "raw",
    "records",
    "rows",
    "series",
    "snapshots",
    "surface",
    "ticks",
    "values",
}
_REF_KEYS = (
    "result_ref",
    "artifact_path",
    "file_path",
    "output_path",
    "path",
    "manifest_path",
    "url",
    "href",
)
_ID_KEYS = (
    "run_id",
    "batch_id",
    "graph_id",
    "report_id",
    "simulation_id",
    "model_run_id",
    "fair_value_run_id",
    "global_run_id",
)


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_STRING_LENGTH:
        return value
    return f"{value[:_MAX_STRING_LENGTH]}...<truncated {len(value) - _MAX_STRING_LENGTH} chars>"


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_string(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "item"):
        try:
            return _compact_value(value.item(), depth=depth)
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return _truncate_string(str(value))
    if depth >= _MAX_SUMMARY_DEPTH:
        if isinstance(value, dict):
            return {"type": "dict", "count": len(value)}
        if isinstance(value, (list, tuple, set)):
            return {"type": "list", "count": len(value)}
        return _truncate_string(str(value))
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for key, item in list(value.items())[:_MAX_SUMMARY_ITEMS]:
            key_text = str(key)
            if key_text in _HEAVY_PAYLOAD_KEYS:
                compact[f"{key_text}_count"] = len(item) if hasattr(item, "__len__") else None
                continue
            compact[key_text] = _compact_value(item, depth=depth + 1)
        if len(value) > _MAX_SUMMARY_ITEMS:
            compact["_truncated_keys"] = len(value) - _MAX_SUMMARY_ITEMS
        return compact
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return {
            "count": len(items),
            "sample": [_compact_value(item, depth=depth + 1) for item in items[:_MAX_LIST_ITEMS]],
        }
    return _truncate_string(str(value))


def _first_present(payload: Dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_result_ref(payload: Dict[str, Any]) -> Optional[str]:
    ref = _first_present(payload, _REF_KEYS)
    if isinstance(ref, dict):
        ref = _first_present(ref, _REF_KEYS)
    if ref not in (None, ""):
        return str(ref)

    persisted = payload.get("persisted")
    if isinstance(persisted, dict):
        ref = _first_present(persisted, _REF_KEYS)
        if ref not in (None, ""):
            return str(ref)
    return None


def _compact_task_result(result: Optional[Dict]) -> tuple[Optional[Dict], Optional[str], Optional[str], Optional[Dict]]:
    if not isinstance(result, dict):
        if result is None:
            return None, None, None, None
        summary = {"value": _compact_value(result)}
        return {"summary": summary}, None, None, summary

    run_id = _first_present(result, _ID_KEYS)
    result_ref = _extract_result_ref(result)
    source_summary = result.get("summary") if isinstance(result.get("summary"), dict) else result
    summary = _compact_value(source_summary)
    if not isinstance(summary, dict):
        summary = {"value": summary}

    compact_result: Dict[str, Any] = {
        "run_id": str(run_id) if run_id not in (None, "") else None,
        "result_ref": result_ref,
        "summary": summary,
    }
    for key in _ID_KEYS:
        value = result.get(key)
        if value not in (None, ""):
            compact_result[key] = str(value)
    return compact_result, compact_result.get("result_ref"), compact_result.get("run_id"), summary


@dataclass
class Task:
    """任务数据类"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0              # 总进度百分比 0-100
    message: str = ""              # 状态消息
    result: Optional[Dict] = None  # 任务结果
    error: Optional[str] = None    # 错误信息
    metadata: Dict = field(default_factory=dict)  # 额外元数据
    progress_detail: Dict = field(default_factory=dict)  # 详细进度信息
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "result_ref": getattr(self, "result_ref", None),
            "run_id": getattr(self, "run_id", None),
            "summary": getattr(self, "summary", None),
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """
    任务管理器
    线程安全的任务状态管理
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Task] = {}
                    cls._instance._task_lock = threading.Lock()
        return cls._instance
    
    def create_task(self, task_type: str, metadata: Optional[Dict] = None) -> str:
        """
        创建新任务
        
        Args:
            task_type: 任务类型
            metadata: 额外元数据
            
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now()
        
        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        with self._task_lock:
            self._tasks[task_id] = task
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with self._task_lock:
            return self._tasks.get(task_id)
    
    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
        progress_detail: Optional[Dict] = None
    ):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            progress: 进度
            message: 消息
            result: 结果
            error: 错误信息
            progress_detail: 详细进度信息
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    compact_result, result_ref, run_id, summary = _compact_task_result(result)
                    task.result = compact_result
                    task.result_ref = result_ref
                    task.run_id = run_id
                    task.summary = summary
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail
    
    def complete_task(self, task_id: str, result: Dict):
        """标记任务完成"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=t('progress.taskComplete'),
            result=result
        )
    
    def fail_task(self, task_id: str, error: str):
        """标记任务失败"""
        self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=t('progress.taskFailed'),
            error=error
        )
    
    def list_tasks(self, task_type: Optional[str] = None) -> list:
        """列出任务"""
        with self._task_lock:
            tasks = list(self._tasks.values())
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)]
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        with self._task_lock:
            old_ids = [
                tid for tid, task in self._tasks.items()
                if task.created_at < cutoff and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
            ]
            for tid in old_ids:
                del self._tasks[tid]
