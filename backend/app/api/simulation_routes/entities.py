from flask import jsonify, request

from ...http import error_response
from ...services.simulation_entity_resolver import SimulationEntityResolver
from ...utils.locale import t
from .. import simulation_bp
from .shared import ensure_graph_backend_ready, logger


@simulation_bp.route("/entities/<graph_id>", methods=["GET"])
def get_graph_entities(graph_id: str):
    """
    获取图谱中的所有实体（已过滤）

    只返回符合预定义实体类型的节点（Labels不只是Entity的节点）

    Query参数：
        entity_types: 逗号分隔的实体类型列表（可选，用于进一步过滤）
        enrich: 是否获取相关边信息（默认true）
    """
    try:
        backend_error = ensure_graph_backend_ready()
        if backend_error:
            return error_response(logger, status_code=500)

        entity_types_str = request.args.get("entity_types", "")
        entity_types = (
            [t.strip() for t in entity_types_str.split(",") if t.strip()]
            if entity_types_str
            else None
        )
        enrich = request.args.get("enrich", "true").lower() == "true"

        logger.info(
            f"获取图谱实体: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}"
        )

        resolver = SimulationEntityResolver()
        result = resolver.resolve_filtered_entities(
            graph_id=graph_id,
            project_id=request.args.get("project_id"),
            defined_entity_types=entity_types,
            enrich_with_edges=enrich,
        )

        return jsonify({"success": True, "data": result.to_dict()})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/entities/<graph_id>/<entity_uuid>", methods=["GET"])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """获取单个实体的详细信息"""
    try:
        backend_error = ensure_graph_backend_ready()
        if backend_error:
            return error_response(logger, status_code=500)

        resolver = SimulationEntityResolver()
        entity = resolver.get_entity_with_context(
            graph_id=graph_id,
            entity_uuid=entity_uuid,
            project_id=request.args.get("project_id"),
        )

        if not entity:
            return jsonify(
                {"success": False, "error": t("api.entityNotFound", id=entity_uuid)}
            ), 404

        return jsonify({"success": True, "data": entity.to_dict()})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/entities/<graph_id>/by-type/<entity_type>", methods=["GET"])
def get_entities_by_type(graph_id: str, entity_type: str):
    """获取指定类型的所有实体"""
    try:
        backend_error = ensure_graph_backend_ready()
        if backend_error:
            return error_response(logger, status_code=500)

        enrich = request.args.get("enrich", "true").lower() == "true"

        resolver = SimulationEntityResolver()
        entities = resolver.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            project_id=request.args.get("project_id"),
            enrich_with_edges=enrich,
        )

        return jsonify(
            {
                "success": True,
                "data": {
                    "entity_type": entity_type,
                    "count": len(entities),
                    "entities": [e.to_dict() for e in entities],
                },
            }
        )

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)
