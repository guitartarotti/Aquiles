"""
图谱构建服务
接口2：通过可切换的图谱后端构建图谱
"""

import threading
from typing import Any, Dict, List, Optional

from ..models.task import TaskManager, TaskStatus
from ..utils.locale import get_locale, set_locale, t
from .graph_backends import GraphInfo, create_graph_backend
from .text_processor import TextProcessor


class GraphBuilderService:
    """
    图谱构建服务
    负责调度具体图谱后端完成构建工作
    """

    def __init__(self, api_key: Optional[str] = None, backend_name: Optional[str] = None):
        self.backend = create_graph_backend(backend_name=backend_name, api_key=api_key)
        self.task_manager = TaskManager()

    @property
    def backend_name(self) -> str:
        return self.backend.backend_name

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
    ) -> str:
        """
        异步构建图谱

        Args:
            text: 输入文本
            ontology: 本体定义（来自接口1的输出）
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量

        Returns:
            任务ID
        """
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
                "backend": self.backend_name,
            },
        )

        current_locale = get_locale()
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale),
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = "zh",
    ):
        """图谱构建工作线程"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t("progress.startBuildingGraph"),
            )

            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t("progress.graphCreated", graphId=graph_id),
            )

            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t("progress.ontologySet"),
            )

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t("progress.textSplit", count=total_chunks),
            )

            episode_ids = self.add_text_batches(
                graph_id,
                chunks,
                batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),
                    message=msg,
                ),
            )

            self.task_manager.update_task(
                task_id,
                progress=60,
                message=t("progress.waitingZepProcess"),
            )

            self._wait_for_episodes(
                graph_id,
                episode_ids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),
                    message=msg,
                ),
            )

            self.task_manager.update_task(
                task_id,
                progress=90,
                message=t("progress.fetchingGraphInfo"),
            )

            graph_info = self._get_graph_info(graph_id)

            self.task_manager.complete_task(
                task_id,
                {
                    "graph_id": graph_id,
                    "graph_info": graph_info.to_dict(),
                    "chunks_processed": total_chunks,
                    "backend": self.backend_name,
                },
            )
        except Exception as exc:
            import traceback

            error_msg = f"{str(exc)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """创建图谱（公开方法）"""
        return self.backend.create_graph(name=name)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """设置图谱本体（公开方法）"""
        self.backend.set_ontology(graph_id, ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback=None,
    ) -> List[str]:
        """分批添加文本到图谱"""
        return self.backend.add_text_batches(
            graph_id=graph_id,
            chunks=chunks,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )

    def _wait_for_episodes(
        self,
        graph_id: str,
        episode_ids: List[str],
        progress_callback=None,
        timeout: int = 600,
    ):
        """等待所有数据完成后端处理"""
        self.backend.wait_for_ingestion(
            graph_id=graph_id,
            episode_ids=episode_ids,
            progress_callback=progress_callback,
            timeout=timeout,
        )

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        return self.backend.get_graph_info(graph_id)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """获取完整图谱数据"""
        return self.backend.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str):
        """删除图谱"""
        self.backend.delete_graph(graph_id)
