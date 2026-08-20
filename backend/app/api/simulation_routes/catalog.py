import os

from flask import jsonify, request, send_file

from ...config import Config
from ...http import error_response
from ...models.project import ProjectManager
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationRunner
from ...utils.locale import t
from .. import simulation_bp
from .shared import (
    _get_report_id_for_simulation,
    logger,
)


@simulation_bp.route("/<simulation_id>", methods=["GET"])
def get_simulation(simulation_id: str):
    """获取模拟状态"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify(
                {"success": False, "error": t("api.simulationNotFound", id=simulation_id)}
            ), 404

        result = state.to_dict()

        # 如果模拟已准备好，附加运行说明
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        return jsonify({"success": True, "data": result})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/list", methods=["GET"])
def list_simulations():
    """
    列出所有模拟

    Query参数：
        project_id: 按项目ID过滤（可选）
    """
    try:
        project_id = request.args.get("project_id")

        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)

        return jsonify(
            {"success": True, "data": [s.to_dict() for s in simulations], "count": len(simulations)}
        )

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/history", methods=["GET"])
def get_simulation_history():
    """
    获取历史模拟列表（带项目详情）

    用于首页历史项目展示，返回包含项目名称、描述等丰富信息的模拟列表

    Query参数：
        limit: 返回数量限制（默认20）

    返回：
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "武大舆情分析",
                    "simulation_requirement": "如果武汉大学发布...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get("limit", 20, type=int)

        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]

        # 增强模拟数据，只从 Simulation 文件读取
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()

            # 获取模拟配置信息（从 simulation_config.json 读取 simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # 推荐轮数（后备值）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0)
                    * 60
                    / max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0

            # 获取运行状态（从 run_state.json 读取用户设置的实际轮数）
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # 使用用户设置的 total_rounds，若无则使用推荐轮数
                sim_dict["total_rounds"] = (
                    run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
                )
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            # 获取关联项目的文件列表（最多3个）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, "files") and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "未知文件")} for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []

            # 获取关联的 report_id（查找该 simulation 最新的 report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)

            # 添加版本号
            sim_dict["version"] = "v1.0.2"

            # 格式化日期
            sim_dict["created_date"] = str(sim_dict.get("created_at") or "")[:10]

            enriched_simulations.append(sim_dict)

        return jsonify(
            {"success": True, "data": enriched_simulations, "count": len(enriched_simulations)}
        )

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/<simulation_id>/profiles", methods=["GET"])
def get_simulation_profiles(simulation_id: str):
    """
    获取模拟的Agent Profile

    Query参数：
        platform: 平台类型（reddit/twitter，默认reddit）
    """
    try:
        platform = request.args.get("platform", "reddit")

        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)

        return jsonify(
            {
                "success": True,
                "data": {"platform": platform, "count": len(profiles), "profiles": profiles},
            }
        )

    except ValueError:
        return error_response(logger, status_code=404, message="Simulation profiles not found")

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/<simulation_id>/profiles/realtime", methods=["GET"])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    实时获取模拟的Agent Profile（用于在生成过程中实时查看进度）

    与 /profiles 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）

    Query参数：
        platform: 平台类型（reddit/twitter，默认reddit）

    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // 预期总数（如果有）
                "is_generating": true,  // 是否正在生成
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import csv
    import json
    from datetime import datetime

    try:
        platform = request.args.get("platform", "reddit")

        # 获取模拟目录
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify(
                {"success": False, "error": t("api.simulationNotFound", id=simulation_id)}
            ), 404

        # 确定文件路径
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")

        # 检查文件是否存在
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                if platform == "reddit":
                    with open(profiles_file, "r", encoding="utf-8") as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"读取 profiles 文件失败（可能正在写入中）: {e}")
                profiles = []

        # 检查是否正在生成（通过 state.json 判断）
        is_generating = False
        total_expected = None

        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "platform": platform,
                    "count": len(profiles),
                    "total_expected": total_expected,
                    "is_generating": is_generating,
                    "file_exists": file_exists,
                    "file_modified_at": file_modified_at,
                    "profiles": profiles,
                },
            }
        )

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/<simulation_id>/config/realtime", methods=["GET"])
def get_simulation_config_realtime(simulation_id: str):
    """
    实时获取模拟配置（用于在生成过程中实时查看进度）

    与 /config 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）
    - 即使配置还没生成完也能返回部分信息

    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // 是否正在生成
                "generation_stage": "generating_config",  // 当前生成阶段
                "config": {...}  // 配置内容（如果存在）
            }
        }
    """
    import json
    from datetime import datetime

    try:
        # 获取模拟目录
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify(
                {"success": False, "error": t("api.simulationNotFound", id=simulation_id)}
            ), 404

        # 配置文件路径
        config_file = os.path.join(sim_dir, "simulation_config.json")

        # 检查文件是否存在
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"读取 config 文件失败（可能正在写入中）: {e}")
                config = None

        # 检查是否正在生成（通过 state.json 判断）
        is_generating = False
        generation_stage = None
        config_generated = False

        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)

                    # 判断当前阶段
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass

        # 构建返回数据
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config,
        }

        # 如果配置存在，提取一些关键统计信息
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model"),
            }

        return jsonify({"success": True, "data": response_data})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/<simulation_id>/config", methods=["GET"])
def get_simulation_config(simulation_id: str):
    """
    获取模拟配置（LLM智能生成的完整配置）

    返回包含：
        - time_config: 时间配置（模拟时长、轮次、高峰/低谷时段）
        - agent_configs: 每个Agent的活动配置（活跃度、发言频率、立场等）
        - event_config: 事件配置（初始帖子、热点话题）
        - platform_configs: 平台配置
        - generation_reasoning: LLM的配置推理说明
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)

        if not config:
            return jsonify({"success": False, "error": t("api.configNotFound")}), 404

        return jsonify({"success": True, "data": config})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/<simulation_id>/config/download", methods=["GET"])
def download_simulation_config(simulation_id: str):
    """下载模拟配置文件"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            return jsonify({"success": False, "error": t("api.configFileNotFound")}), 404

        return send_file(config_path, as_attachment=True, download_name="simulation_config.json")

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@simulation_bp.route("/script/<script_name>/download", methods=["GET"])
def download_simulation_script(script_name: str):
    """
    下载模拟运行脚本文件（通用脚本，位于 backend/scripts/）

    script_name可选值：
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # 脚本位于 backend/scripts/ 目录
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))

        # 验证脚本名称
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py",
            "run_parallel_simulation.py",
            "action_logger.py",
        ]

        if script_name not in allowed_scripts:
            return jsonify(
                {
                    "success": False,
                    "error": t("api.unknownScript", name=script_name, allowed=allowed_scripts),
                }
            ), 400

        script_path = os.path.join(scripts_dir, script_name)

        if not os.path.exists(script_path):
            return jsonify(
                {"success": False, "error": t("api.scriptFileNotFound", name=script_name)}
            ), 404

        return send_file(script_path, as_attachment=True, download_name=script_name)

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)
