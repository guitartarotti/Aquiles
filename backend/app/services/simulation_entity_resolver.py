from __future__ import annotations

from typing import List, Optional

from ..models.project import Project, ProjectManager
from ..utils.logger import get_logger
from .macro_persona_service import MacroPersonaService
from .zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader

logger = get_logger("aquiles.simulation_entity_resolver")


class SimulationEntityResolver:
    """Choose between raw graph entities and macro personas based on project strategy."""

    def __init__(self):
        self.reader = ZepEntityReader()
        self.macro_personas = MacroPersonaService()

    def resolve_filtered_entities(
        self,
        graph_id: str,
        project_id: Optional[str] = None,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        if self._should_use_macro_personas(graph_id=graph_id, project_id=project_id):
            logger.info("Using macro persona strategy for simulation entities")
            return self.macro_personas.build_filtered_entities(
                graph_id=graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=enrich_with_edges,
            )

        return self.reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=defined_entity_types,
            enrich_with_edges=enrich_with_edges,
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str,
        project_id: Optional[str] = None,
    ) -> Optional[EntityNode]:
        if self._should_use_macro_personas(graph_id=graph_id, project_id=project_id):
            return self.macro_personas.get_entity_with_context(graph_id=graph_id, entity_uuid=entity_uuid)
        return self.reader.get_entity_with_context(graph_id, entity_uuid)

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        project_id: Optional[str] = None,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        if self._should_use_macro_personas(graph_id=graph_id, project_id=project_id):
            return self.macro_personas.get_entities_by_type(
                graph_id=graph_id,
                entity_type=entity_type,
                enrich_with_edges=enrich_with_edges,
            )
        return self.reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich_with_edges,
        )

    def _should_use_macro_personas(self, graph_id: str, project_id: Optional[str]) -> bool:
        project = self._resolve_project(graph_id=graph_id, project_id=project_id)
        if not project:
            return False

        return (
            (project.agent_strategy or "").strip().lower() == "macro_personas"
            or (project.project_mode or "").strip().lower() == "macro"
        )

    def _resolve_project(self, graph_id: str, project_id: Optional[str]) -> Optional[Project]:
        if project_id:
            return ProjectManager.get_project(project_id)
        return ProjectManager.find_project_by_graph_id(graph_id)
