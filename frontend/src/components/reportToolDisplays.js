import { computed, h, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";

// Tool configurations with display names and colors
const toolConfig = {
  insight_forge: {
    name: "Deep Insight",
    color: "purple",
    icon: "lightbulb", // 灯泡图标 - 代表洞察
  },
  panorama_search: {
    name: "Panorama Search",
    color: "blue",
    icon: "globe", // 地球图标 - 代表全景搜索
  },
  interview_agents: {
    name: "Agent Interview",
    color: "green",
    icon: "users", // 用户图标 - 代表对话
  },
  quick_search: {
    name: "Quick Search",
    color: "orange",
    icon: "zap", // 闪电图标 - 代表快速
  },
  get_graph_statistics: {
    name: "Graph Stats",
    color: "cyan",
    icon: "chart", // 图表图标 - 代表统计
  },
  get_entities_by_type: {
    name: "Entity Query",
    color: "pink",
    icon: "database", // 数据库图标 - 代表实体
  },
};

const getToolDisplayName = (toolName) => {
  return toolConfig[toolName]?.name || toolName;
};

const getToolColor = (toolName) => {
  return toolConfig[toolName]?.color || "gray";
};

const getToolIcon = (toolName) => {
  return toolConfig[toolName]?.icon || "tool";
};

// Parse functions
const parseInsightForge = (text) => {
  const result = {
    query: "",
    simulationRequirement: "",
    stats: { facts: 0, entities: 0, relationships: 0 },
    subQueries: [],
    facts: [],
    entities: [],
    relations: [],
  };

  try {
    // 提取分析问题
    const queryMatch = text.match(/分析问题:\s*(.+?)(?:\n|$)/);
    if (queryMatch) result.query = queryMatch[1].trim();

    // 提取预测场景
    const reqMatch = text.match(/预测场景:\s*(.+?)(?:\n|$)/);
    if (reqMatch) result.simulationRequirement = reqMatch[1].trim();

    // 提取统计数据 - 匹配"相关预测事实: X条"格式
    const factMatch = text.match(/相关预测事实:\s*(\d+)/);
    const entityMatch = text.match(/涉及实体:\s*(\d+)/);
    const relMatch = text.match(/关系链:\s*(\d+)/);
    if (factMatch) result.stats.facts = parseInt(factMatch[1]);
    if (entityMatch) result.stats.entities = parseInt(entityMatch[1]);
    if (relMatch) result.stats.relationships = parseInt(relMatch[1]);

    // 提取子问题 - 完整提取，不限制数量
    const subQSection = text.match(/### 分析的子问题\n([\s\S]*?)(?=\n###|$)/);
    if (subQSection) {
      const lines = subQSection[1].split("\n").filter((l) => l.match(/^\d+\./));
      result.subQueries = lines
        .map((l) => l.replace(/^\d+\.\s*/, "").trim())
        .filter(Boolean);
    }

    // 提取关键事实 - 完整提取，不限制数量
    const factsSection = text.match(
      /### 【关键事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/,
    );
    if (factsSection) {
      const lines = factsSection[1]
        .split("\n")
        .filter((l) => l.match(/^\d+\./));
      result.facts = lines
        .map((l) => {
          const match = l.match(/^\d+\.\s*"?(.+?)"?\s*$/);
          return match
            ? match[1].replace(/^"|"$/g, "").trim()
            : l.replace(/^\d+\.\s*/, "").trim();
        })
        .filter(Boolean);
    }

    // 提取核心实体 - 完整提取，包含摘要和相关事实数
    const entitySection = text.match(/### 【核心实体】\n([\s\S]*?)(?=\n###|$)/);
    if (entitySection) {
      const entityText = entitySection[1];
      // 按 "- **" 分割实体块
      const entityBlocks = entityText
        .split(/\n(?=- \*\*)/)
        .filter((b) => b.trim().startsWith("- **"));
      result.entities = entityBlocks
        .map((block) => {
          const nameMatch = block.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/);
          const summaryMatch = block.match(/摘要:\s*"?(.+?)"?(?:\n|$)/);
          const relatedMatch = block.match(/相关事实:\s*(\d+)/);
          return {
            name: nameMatch ? nameMatch[1].trim() : "",
            type: nameMatch ? nameMatch[2].trim() : "",
            summary: summaryMatch ? summaryMatch[1].trim() : "",
            relatedFactsCount: relatedMatch ? parseInt(relatedMatch[1]) : 0,
          };
        })
        .filter((e) => e.name);
    }

    // 提取关系链 - 完整提取，不限制数量
    const relSection = text.match(/### 【关系链】\n([\s\S]*?)(?=\n###|$)/);
    if (relSection) {
      const lines = relSection[1]
        .split("\n")
        .filter((l) => l.trim().startsWith("-"));
      result.relations = lines
        .map((l) => {
          const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/);
          if (match) {
            return {
              source: match[1].trim(),
              relation: match[2].trim(),
              target: match[3].trim(),
            };
          }
          return null;
        })
        .filter(Boolean);
    }
  } catch (e) {
    console.warn("Parse insight_forge failed:", e);
  }

  return result;
};

const parsePanorama = (text) => {
  const result = {
    query: "",
    stats: { nodes: 0, edges: 0, activeFacts: 0, historicalFacts: 0 },
    activeFacts: [],
    historicalFacts: [],
    entities: [],
  };

  try {
    // 提取查询
    const queryMatch = text.match(/查询:\s*(.+?)(?:\n|$)/);
    if (queryMatch) result.query = queryMatch[1].trim();

    // 提取统计数据
    const nodesMatch = text.match(/总节点数:\s*(\d+)/);
    const edgesMatch = text.match(/总边数:\s*(\d+)/);
    const activeMatch = text.match(/当前有效事实:\s*(\d+)/);
    const histMatch = text.match(/历史\/过期事实:\s*(\d+)/);
    if (nodesMatch) result.stats.nodes = parseInt(nodesMatch[1]);
    if (edgesMatch) result.stats.edges = parseInt(edgesMatch[1]);
    if (activeMatch) result.stats.activeFacts = parseInt(activeMatch[1]);
    if (histMatch) result.stats.historicalFacts = parseInt(histMatch[1]);

    // 提取当前有效事实 - 完整提取，不限制数量
    const activeSection = text.match(
      /### 【当前有效事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/,
    );
    if (activeSection) {
      const lines = activeSection[1]
        .split("\n")
        .filter((l) => l.match(/^\d+\./));
      result.activeFacts = lines
        .map((l) => {
          // 移除编号和引号
          const factText = l
            .replace(/^\d+\.\s*/, "")
            .replace(/^"|"$/g, "")
            .trim();
          return factText;
        })
        .filter(Boolean);
    }

    // 提取历史/过期事实 - 完整提取，不限制数量
    const histSection = text.match(
      /### 【历史\/过期事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/,
    );
    if (histSection) {
      const lines = histSection[1].split("\n").filter((l) => l.match(/^\d+\./));
      result.historicalFacts = lines
        .map((l) => {
          const factText = l
            .replace(/^\d+\.\s*/, "")
            .replace(/^"|"$/g, "")
            .trim();
          return factText;
        })
        .filter(Boolean);
    }

    // 提取涉及实体 - 完整提取，不限制数量
    const entitySection = text.match(/### 【涉及实体】\n([\s\S]*?)(?=\n###|$)/);
    if (entitySection) {
      const lines = entitySection[1]
        .split("\n")
        .filter((l) => l.trim().startsWith("-"));
      result.entities = lines
        .map((l) => {
          const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/);
          if (match) return { name: match[1].trim(), type: match[2].trim() };
          return null;
        })
        .filter(Boolean);
    }
  } catch (e) {
    console.warn("Parse panorama failed:", e);
  }

  return result;
};

const parseInterview = (text) => {
  const result = {
    topic: "",
    agentCount: "",
    successCount: 0,
    totalCount: 0,
    selectionReason: "",
    interviews: [],
    summary: "",
  };

  try {
    // 提取采访主题
    const topicMatch = text.match(/\*\*采访主题:\*\*\s*(.+?)(?:\n|$)/);
    if (topicMatch) result.topic = topicMatch[1].trim();

    // 提取采访人数（如 "5 / 9 位模拟Agent"）
    const countMatch = text.match(/\*\*采访人数:\*\*\s*(\d+)\s*\/\s*(\d+)/);
    if (countMatch) {
      result.successCount = parseInt(countMatch[1]);
      result.totalCount = parseInt(countMatch[2]);
      result.agentCount = `${countMatch[1]} / ${countMatch[2]}`;
    }

    // 提取采访对象选择理由
    const reasonMatch = text.match(
      /### 采访对象选择理由\n([\s\S]*?)(?=\n---\n|\n### 采访实录)/,
    );
    if (reasonMatch) {
      result.selectionReason = reasonMatch[1].trim();
    }

    // 解析每个人的选择理由
    const parseIndividualReasons = (reasonText) => {
      const reasons = {};
      if (!reasonText) return reasons;

      const lines = reasonText.split(/\n+/);
      let currentName = null;
      let currentReason = [];

      for (const line of lines) {
        let headerMatch = null;
        let name = null;
        let reasonStart = null;

        // 格式1: 数字. **名字（index=X）**：理由
        // 例如: 1. **校友_345（index=1）**：作为武大校友...
        headerMatch = line.match(
          /^\d+\.\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/,
        );
        if (headerMatch) {
          name = headerMatch[1].trim();
          reasonStart = headerMatch[2];
        }

        // 格式2: - 选择名字（index X）：理由
        // 例如: - 选择家长_601（index 0）：作为家长群体代表...
        if (!headerMatch) {
          headerMatch = line.match(
            /^-\s*选择([^（(]+)(?:[（(]index\s*=?\s*\d+[)）])?[：:]\s*(.*)/,
          );
          if (headerMatch) {
            name = headerMatch[1].trim();
            reasonStart = headerMatch[2];
          }
        }

        // 格式3: - **名字（index X）**：理由
        // 例如: - **家长_601（index 0）**：作为家长群体代表...
        if (!headerMatch) {
          headerMatch = line.match(
            /^-\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/,
          );
          if (headerMatch) {
            name = headerMatch[1].trim();
            reasonStart = headerMatch[2];
          }
        }

        if (name) {
          // 保存上一个人的理由
          if (currentName && currentReason.length > 0) {
            reasons[currentName] = currentReason.join(" ").trim();
          }
          // 开始新的人
          currentName = name;
          currentReason = reasonStart ? [reasonStart.trim()] : [];
        } else if (
          currentName &&
          line.trim() &&
          !line.match(/^未选|^综上|^最终选择/)
        ) {
          // 理由的续行（排除结尾总结段落）
          currentReason.push(line.trim());
        }
      }

      // 保存最后一个人的理由
      if (currentName && currentReason.length > 0) {
        reasons[currentName] = currentReason.join(" ").trim();
      }

      return reasons;
    };

    const individualReasons = parseIndividualReasons(result.selectionReason);

    // 提取每个采访记录
    const interviewBlocks = text.split(/#### 采访 #\d+:/).slice(1);

    interviewBlocks.forEach((block, index) => {
      const interview = {
        num: index + 1,
        title: "",
        name: "",
        role: "",
        bio: "",
        selectionReason: "",
        questions: [],
        twitterAnswer: "",
        redditAnswer: "",
        quotes: [],
      };

      // 提取标题（如 "学生"、"教育从业者" 等）
      const titleMatch = block.match(/^(.+?)\n/);
      if (titleMatch) interview.title = titleMatch[1].trim();

      // 提取姓名和角色
      const nameRoleMatch = block.match(/\*\*(.+?)\*\*\s*\((.+?)\)/);
      if (nameRoleMatch) {
        interview.name = nameRoleMatch[1].trim();
        interview.role = nameRoleMatch[2].trim();
        // 设置该人的选择理由
        interview.selectionReason = individualReasons[interview.name] || "";
      }

      // 提取简介
      const bioMatch = block.match(/_简介:\s*([\s\S]*?)_\n/);
      if (bioMatch) {
        interview.bio = bioMatch[1].trim().replace(/\.\.\.$/, "...");
      }

      // 提取问题列表
      const qMatch = block.match(
        /\*\*Q:\*\*\s*([\s\S]*?)(?=\n\n\*\*A:\*\*|\*\*A:\*\*)/,
      );
      if (qMatch) {
        const qText = qMatch[1].trim();
        // 按数字编号分割问题
        const questions = qText.split(/\n\d+\.\s+/).filter((q) => q.trim());
        if (questions.length > 0) {
          // 如果第一个问题前面有"1."，需要特殊处理
          const firstQ = qText.match(/^1\.\s+(.+)/);
          if (firstQ) {
            interview.questions = [
              firstQ[1].trim(),
              ...questions.slice(1).map((q) => q.trim()),
            ];
          } else {
            interview.questions = questions.map((q) => q.trim());
          }
        }
      }

      // 提取回答 - 分Twitter和Reddit
      const answerMatch = block.match(
        /\*\*A:\*\*\s*([\s\S]*?)(?=\*\*关键引言|$)/,
      );
      if (answerMatch) {
        const answerText = answerMatch[1].trim();

        // 分离Twitter和Reddit回答
        const twitterMatch = answerText.match(
          /【Twitter平台回答】\n?([\s\S]*?)(?=【Reddit平台回答】|$)/,
        );
        const redditMatch = answerText.match(
          /【Reddit平台回答】\n?([\s\S]*?)$/,
        );

        if (twitterMatch) {
          interview.twitterAnswer = twitterMatch[1].trim();
        }
        if (redditMatch) {
          interview.redditAnswer = redditMatch[1].trim();
        }

        // 平台回退逻辑（兼容旧格式：只有一个平台标记的情况）
        if (!twitterMatch && redditMatch) {
          // 只有 Reddit 回答，仅在非占位文本时复制为默认显示
          if (
            interview.redditAnswer &&
            interview.redditAnswer !== "（该平台未获得回复）"
          ) {
            interview.twitterAnswer = interview.redditAnswer;
          }
        } else if (twitterMatch && !redditMatch) {
          if (
            interview.twitterAnswer &&
            interview.twitterAnswer !== "（该平台未获得回复）"
          ) {
            interview.redditAnswer = interview.twitterAnswer;
          }
        } else if (!twitterMatch && !redditMatch) {
          // 没有分平台标记（极旧格式），整体作为回答
          interview.twitterAnswer = answerText;
        }
      }

      // 提取关键引言（兼容多种引号格式）
      const quotesMatch = block.match(
        /\*\*关键引言:\*\*\n([\s\S]*?)(?=\n---|\n####|$)/,
      );
      if (quotesMatch) {
        const quotesText = quotesMatch[1];
        // 优先匹配 > "text" 格式
        let quoteMatches = quotesText.match(/> "([^"]+)"/g);
        // 回退：匹配 > "text" 或 > \u201Ctext\u201D（中文引号）
        if (!quoteMatches) {
          quoteMatches = quotesText.match(
            /> [\u201C""]([^\u201D""]+)[\u201D""]/g,
          );
        }
        if (quoteMatches) {
          interview.quotes = quoteMatches
            .map((q) => q.replace(/^> [\u201C""]|[\u201D""]$/g, "").trim())
            .filter((q) => q);
        }
      }

      if (interview.name || interview.title) {
        result.interviews.push(interview);
      }
    });

    // 提取采访摘要
    const summaryMatch = text.match(/### 采访摘要与核心观点\n([\s\S]*?)$/);
    if (summaryMatch) {
      result.summary = summaryMatch[1].trim();
    }
  } catch (e) {
    console.warn("Parse interview failed:", e);
  }

  return result;
};

const parseQuickSearch = (text) => {
  const result = {
    query: "",
    count: 0,
    facts: [],
    edges: [],
    nodes: [],
  };

  try {
    // 提取搜索查询
    const queryMatch = text.match(/搜索查询:\s*(.+?)(?:\n|$)/);
    if (queryMatch) result.query = queryMatch[1].trim();

    // 提取结果数量
    const countMatch = text.match(/找到\s*(\d+)\s*条/);
    if (countMatch) result.count = parseInt(countMatch[1]);

    // 提取相关事实 - 完整提取，不限制数量
    const factsSection = text.match(/### 相关事实:\n([\s\S]*)$/);
    if (factsSection) {
      const lines = factsSection[1]
        .split("\n")
        .filter((l) => l.match(/^\d+\./));
      result.facts = lines
        .map((l) => l.replace(/^\d+\.\s*/, "").trim())
        .filter(Boolean);
    }

    // 尝试提取边信息（如果有）
    const edgesSection = text.match(/### 相关边:\n([\s\S]*?)(?=\n###|$)/);
    if (edgesSection) {
      const lines = edgesSection[1]
        .split("\n")
        .filter((l) => l.trim().startsWith("-"));
      result.edges = lines
        .map((l) => {
          const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/);
          if (match) {
            return {
              source: match[1].trim(),
              relation: match[2].trim(),
              target: match[3].trim(),
            };
          }
          return null;
        })
        .filter(Boolean);
    }

    // 尝试提取节点信息（如果有）
    const nodesSection = text.match(/### 相关节点:\n([\s\S]*?)(?=\n###|$)/);
    if (nodesSection) {
      const lines = nodesSection[1]
        .split("\n")
        .filter((l) => l.trim().startsWith("-"));
      result.nodes = lines
        .map((l) => {
          const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/);
          if (match) return { name: match[1].trim(), type: match[2].trim() };
          const simpleMatch = l.match(/^-\s*(.+)$/);
          if (simpleMatch) return { name: simpleMatch[1].trim(), type: "" };
          return null;
        })
        .filter(Boolean);
    }
  } catch (e) {
    console.warn("Parse quick_search failed:", e);
  }

  return result;
};

// ========== Sub Components ==========

// Insight Display Component - Enhanced with full data rendering (Interview-like style)
const InsightDisplay = {
  props: ["result", "resultLength"],
  setup(props) {
    const { t } = useI18n();
    const activeTab = ref("facts"); // 'facts', 'entities', 'relations', 'subqueries'
    const expandedFacts = ref(false);
    const expandedEntities = ref(false);
    const expandedRelations = ref(false);
    const INITIAL_SHOW_COUNT = 5;

    // Format result size for display
    const formatSize = (length) => {
      if (!length) return "";
      if (length >= 1000) {
        return `${(length / 1000).toFixed(1)}k chars`;
      }
      return `${length} chars`;
    };

    return () =>
      h("div", { class: "insight-display" }, [
        // Header Section - like interview header
        h("div", { class: "insight-header" }, [
          h("div", { class: "header-main" }, [
            h("div", { class: "header-title" }, "Deep Insight"),
            h("div", { class: "header-stats" }, [
              h("span", { class: "stat-item" }, [
                h(
                  "span",
                  { class: "stat-value" },
                  props.result.stats.facts || props.result.facts.length,
                ),
                h("span", { class: "stat-label" }, "Facts"),
              ]),
              h("span", { class: "stat-divider" }, "/"),
              h("span", { class: "stat-item" }, [
                h(
                  "span",
                  { class: "stat-value" },
                  props.result.stats.entities || props.result.entities.length,
                ),
                h("span", { class: "stat-label" }, "Entities"),
              ]),
              h("span", { class: "stat-divider" }, "/"),
              h("span", { class: "stat-item" }, [
                h(
                  "span",
                  { class: "stat-value" },
                  props.result.stats.relationships ||
                    props.result.relations.length,
                ),
                h("span", { class: "stat-label" }, "Relations"),
              ]),
              props.resultLength && h("span", { class: "stat-divider" }, "·"),
              props.resultLength &&
                h(
                  "span",
                  { class: "stat-size" },
                  formatSize(props.resultLength),
                ),
            ]),
          ]),
          props.result.query &&
            h("div", { class: "header-topic" }, props.result.query),
          props.result.simulationRequirement &&
            h("div", { class: "header-scenario" }, [
              h("span", { class: "scenario-label" }, t("step4.scenarioLabel")),
              h(
                "span",
                { class: "scenario-text" },
                props.result.simulationRequirement,
              ),
            ]),
        ]),

        // Tab Navigation
        h("div", { class: "insight-tabs" }, [
          h(
            "button",
            {
              class: ["insight-tab", { active: activeTab.value === "facts" }],
              onClick: () => {
                activeTab.value = "facts";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabKeyFacts", { count: props.result.facts.length }),
              ),
            ],
          ),
          h(
            "button",
            {
              class: [
                "insight-tab",
                { active: activeTab.value === "entities" },
              ],
              onClick: () => {
                activeTab.value = "entities";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabCoreEntities", {
                  count: props.result.entities.length,
                }),
              ),
            ],
          ),
          h(
            "button",
            {
              class: [
                "insight-tab",
                { active: activeTab.value === "relations" },
              ],
              onClick: () => {
                activeTab.value = "relations";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabRelationChains", {
                  count: props.result.relations.length,
                }),
              ),
            ],
          ),
          props.result.subQueries.length > 0 &&
            h(
              "button",
              {
                class: [
                  "insight-tab",
                  { active: activeTab.value === "subqueries" },
                ],
                onClick: () => {
                  activeTab.value = "subqueries";
                },
              },
              [
                h(
                  "span",
                  { class: "tab-label" },
                  t("step4.tabSubQueries", {
                    count: props.result.subQueries.length,
                  }),
                ),
              ],
            ),
        ]),

        // Tab Content
        h("div", { class: "insight-content" }, [
          // Facts Tab
          activeTab.value === "facts" &&
            props.result.facts.length > 0 &&
            h("div", { class: "facts-panel" }, [
              h("div", { class: "panel-header" }, [
                h("span", { class: "panel-title" }, t("step4.panelKeyFacts")),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalCount", { count: props.result.facts.length }),
                ),
              ]),
              h(
                "div",
                { class: "facts-list" },
                (expandedFacts.value
                  ? props.result.facts
                  : props.result.facts.slice(0, INITIAL_SHOW_COUNT)
                ).map((fact, i) =>
                  h("div", { class: "fact-item", key: i }, [
                    h("span", { class: "fact-number" }, i + 1),
                    h("div", { class: "fact-content" }, fact),
                  ]),
                ),
              ),
              props.result.facts.length > INITIAL_SHOW_COUNT &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedFacts.value = !expandedFacts.value;
                    },
                  },
                  expandedFacts.value
                    ? t("step4.collapse")
                    : t("step4.expandAll", {
                        count: props.result.facts.length,
                      }),
                ),
            ]),

          // Entities Tab
          activeTab.value === "entities" &&
            props.result.entities.length > 0 &&
            h("div", { class: "entities-panel" }, [
              h("div", { class: "panel-header" }, [
                h(
                  "span",
                  { class: "panel-title" },
                  t("step4.panelCoreEntities"),
                ),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalEntityCount", {
                    count: props.result.entities.length,
                  }),
                ),
              ]),
              h(
                "div",
                { class: "entities-grid" },
                (expandedEntities.value
                  ? props.result.entities
                  : props.result.entities.slice(0, 12)
                ).map((entity, i) =>
                  h(
                    "div",
                    {
                      class: "entity-tag",
                      key: i,
                      title: entity.summary || "",
                    },
                    [
                      h("span", { class: "entity-name" }, entity.name),
                      h("span", { class: "entity-type" }, entity.type),
                      entity.relatedFactsCount > 0 &&
                        h(
                          "span",
                          { class: "entity-fact-count" },
                          t("step4.factCount", {
                            count: entity.relatedFactsCount,
                          }),
                        ),
                    ],
                  ),
                ),
              ),
              props.result.entities.length > 12 &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedEntities.value = !expandedEntities.value;
                    },
                  },
                  expandedEntities.value
                    ? t("step4.collapse")
                    : t("step4.expandAllEntities", {
                        count: props.result.entities.length,
                      }),
                ),
            ]),

          // Relations Tab
          activeTab.value === "relations" &&
            props.result.relations.length > 0 &&
            h("div", { class: "relations-panel" }, [
              h("div", { class: "panel-header" }, [
                h(
                  "span",
                  { class: "panel-title" },
                  t("step4.panelRelationChains"),
                ),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalCount", {
                    count: props.result.relations.length,
                  }),
                ),
              ]),
              h(
                "div",
                { class: "relations-list" },
                (expandedRelations.value
                  ? props.result.relations
                  : props.result.relations.slice(0, INITIAL_SHOW_COUNT)
                ).map((rel, i) =>
                  h("div", { class: "relation-item", key: i }, [
                    h("span", { class: "rel-source" }, rel.source),
                    h("span", { class: "rel-arrow" }, [
                      h("span", { class: "rel-line" }),
                      h("span", { class: "rel-label" }, rel.relation),
                      h("span", { class: "rel-line" }),
                    ]),
                    h("span", { class: "rel-target" }, rel.target),
                  ]),
                ),
              ),
              props.result.relations.length > INITIAL_SHOW_COUNT &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedRelations.value = !expandedRelations.value;
                    },
                  },
                  expandedRelations.value
                    ? t("step4.collapse")
                    : t("step4.expandAll", {
                        count: props.result.relations.length,
                      }),
                ),
            ]),

          // Sub-queries Tab
          activeTab.value === "subqueries" &&
            props.result.subQueries.length > 0 &&
            h("div", { class: "subqueries-panel" }, [
              h("div", { class: "panel-header" }, [
                h("span", { class: "panel-title" }, t("step4.panelSubQueries")),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalEntityCount", {
                    count: props.result.subQueries.length,
                  }),
                ),
              ]),
              h(
                "div",
                { class: "subqueries-list" },
                props.result.subQueries.map((sq, i) =>
                  h("div", { class: "subquery-item", key: i }, [
                    h("span", { class: "subquery-number" }, `Q${i + 1}`),
                    h("div", { class: "subquery-text" }, sq),
                  ]),
                ),
              ),
            ]),

          // Empty state
          activeTab.value === "facts" &&
            props.result.facts.length === 0 &&
            h("div", { class: "empty-state" }, t("step4.emptyKeyFacts")),
          activeTab.value === "entities" &&
            props.result.entities.length === 0 &&
            h("div", { class: "empty-state" }, t("step4.emptyCoreEntities")),
          activeTab.value === "relations" &&
            props.result.relations.length === 0 &&
            h("div", { class: "empty-state" }, t("step4.emptyRelationChains")),
        ]),
      ]);
  },
};

// Panorama Display Component - Enhanced with Active/Historical tabs
const PanoramaDisplay = {
  props: ["result", "resultLength"],
  setup(props) {
    const { t } = useI18n();
    const activeTab = ref("active"); // 'active', 'historical', 'entities'
    const expandedActive = ref(false);
    const expandedHistorical = ref(false);
    const expandedEntities = ref(false);
    const INITIAL_SHOW_COUNT = 5;

    // Format result size for display
    const formatSize = (length) => {
      if (!length) return "";
      if (length >= 1000) {
        return `${(length / 1000).toFixed(1)}k chars`;
      }
      return `${length} chars`;
    };

    return () =>
      h("div", { class: "panorama-display" }, [
        // Header Section
        h("div", { class: "panorama-header" }, [
          h("div", { class: "header-main" }, [
            h("div", { class: "header-title" }, "Panorama Search"),
            h("div", { class: "header-stats" }, [
              h("span", { class: "stat-item" }, [
                h("span", { class: "stat-value" }, props.result.stats.nodes),
                h("span", { class: "stat-label" }, "Nodes"),
              ]),
              h("span", { class: "stat-divider" }, "/"),
              h("span", { class: "stat-item" }, [
                h("span", { class: "stat-value" }, props.result.stats.edges),
                h("span", { class: "stat-label" }, "Edges"),
              ]),
              props.resultLength && h("span", { class: "stat-divider" }, "·"),
              props.resultLength &&
                h(
                  "span",
                  { class: "stat-size" },
                  formatSize(props.resultLength),
                ),
            ]),
          ]),
          props.result.query &&
            h("div", { class: "header-topic" }, props.result.query),
        ]),

        // Tab Navigation
        h("div", { class: "panorama-tabs" }, [
          h(
            "button",
            {
              class: ["panorama-tab", { active: activeTab.value === "active" }],
              onClick: () => {
                activeTab.value = "active";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabActiveFacts", {
                  count: props.result.activeFacts.length,
                }),
              ),
            ],
          ),
          h(
            "button",
            {
              class: [
                "panorama-tab",
                { active: activeTab.value === "historical" },
              ],
              onClick: () => {
                activeTab.value = "historical";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabHistoricalFacts", {
                  count: props.result.historicalFacts.length,
                }),
              ),
            ],
          ),
          h(
            "button",
            {
              class: [
                "panorama-tab",
                { active: activeTab.value === "entities" },
              ],
              onClick: () => {
                activeTab.value = "entities";
              },
            },
            [
              h(
                "span",
                { class: "tab-label" },
                t("step4.tabEntities", { count: props.result.entities.length }),
              ),
            ],
          ),
        ]),

        // Tab Content
        h("div", { class: "panorama-content" }, [
          // Active Facts Tab
          activeTab.value === "active" &&
            h("div", { class: "facts-panel active-facts" }, [
              h("div", { class: "panel-header" }, [
                h(
                  "span",
                  { class: "panel-title" },
                  t("step4.panelActiveFacts"),
                ),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalCount", {
                    count: props.result.activeFacts.length,
                  }),
                ),
              ]),
              props.result.activeFacts.length > 0
                ? h(
                    "div",
                    { class: "facts-list" },
                    (expandedActive.value
                      ? props.result.activeFacts
                      : props.result.activeFacts.slice(0, INITIAL_SHOW_COUNT)
                    ).map((fact, i) =>
                      h("div", { class: "fact-item active", key: i }, [
                        h("span", { class: "fact-number" }, i + 1),
                        h("div", { class: "fact-content" }, fact),
                      ]),
                    ),
                  )
                : h(
                    "div",
                    { class: "empty-state" },
                    t("step4.emptyActiveFacts"),
                  ),
              props.result.activeFacts.length > INITIAL_SHOW_COUNT &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedActive.value = !expandedActive.value;
                    },
                  },
                  expandedActive.value
                    ? t("step4.collapse")
                    : t("step4.expandAll", {
                        count: props.result.activeFacts.length,
                      }),
                ),
            ]),

          // Historical Facts Tab
          activeTab.value === "historical" &&
            h("div", { class: "facts-panel historical-facts" }, [
              h("div", { class: "panel-header" }, [
                h(
                  "span",
                  { class: "panel-title" },
                  t("step4.panelHistoricalFacts"),
                ),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalCount", {
                    count: props.result.historicalFacts.length,
                  }),
                ),
              ]),
              props.result.historicalFacts.length > 0
                ? h(
                    "div",
                    { class: "facts-list" },
                    (expandedHistorical.value
                      ? props.result.historicalFacts
                      : props.result.historicalFacts.slice(
                          0,
                          INITIAL_SHOW_COUNT,
                        )
                    ).map((fact, i) =>
                      h("div", { class: "fact-item historical", key: i }, [
                        h("span", { class: "fact-number" }, i + 1),
                        h("div", { class: "fact-content" }, [
                          // 尝试提取时间信息 [time - time]
                          (() => {
                            const timeMatch = fact.match(/^\[(.+?)\]\s*(.*)$/);
                            if (timeMatch) {
                              return [
                                h("span", { class: "fact-time" }, timeMatch[1]),
                                h("span", { class: "fact-text" }, timeMatch[2]),
                              ];
                            }
                            return h("span", { class: "fact-text" }, fact);
                          })(),
                        ]),
                      ]),
                    ),
                  )
                : h(
                    "div",
                    { class: "empty-state" },
                    t("step4.emptyHistoricalFacts"),
                  ),
              props.result.historicalFacts.length > INITIAL_SHOW_COUNT &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedHistorical.value = !expandedHistorical.value;
                    },
                  },
                  expandedHistorical.value
                    ? t("step4.collapse")
                    : t("step4.expandAll", {
                        count: props.result.historicalFacts.length,
                      }),
                ),
            ]),

          // Entities Tab
          activeTab.value === "entities" &&
            h("div", { class: "entities-panel" }, [
              h("div", { class: "panel-header" }, [
                h("span", { class: "panel-title" }, t("step4.panelEntities")),
                h(
                  "span",
                  { class: "panel-count" },
                  t("step4.totalEntityCount", {
                    count: props.result.entities.length,
                  }),
                ),
              ]),
              props.result.entities.length > 0
                ? h(
                    "div",
                    { class: "entities-grid" },
                    (expandedEntities.value
                      ? props.result.entities
                      : props.result.entities.slice(0, 8)
                    ).map((entity, i) =>
                      h("div", { class: "entity-tag", key: i }, [
                        h("span", { class: "entity-name" }, entity.name),
                        entity.type &&
                          h("span", { class: "entity-type" }, entity.type),
                      ]),
                    ),
                  )
                : h("div", { class: "empty-state" }, t("step4.emptyEntities")),
              props.result.entities.length > 8 &&
                h(
                  "button",
                  {
                    class: "expand-btn",
                    onClick: () => {
                      expandedEntities.value = !expandedEntities.value;
                    },
                  },
                  expandedEntities.value
                    ? t("step4.collapse")
                    : t("step4.expandAllEntities", {
                        count: props.result.entities.length,
                      }),
                ),
            ]),
        ]),
      ]);
  },
};

// Interview Display Component - Conversation Style (Q&A Format)
const InterviewDisplay = {
  props: ["result", "resultLength"],
  setup(props) {
    const { t } = useI18n();

    // Format result size for display
    const formatSize = (length) => {
      if (!length) return "";
      if (length >= 1000) {
        return `${(length / 1000).toFixed(1)}k chars`;
      }
      return `${length} chars`;
    };

    // Clean quote text - remove leading list numbers to avoid double numbering
    const cleanQuoteText = (text) => {
      if (!text) return "";
      // Remove common numeric list markers to avoid rendering a second number.
      return text.replace(/^\s*\d+[.)、）]\s*/u, "").trim();
    };

    const activeIndex = ref(0);
    const expandedAnswers = ref(new Set());
    // 为每个问题-回答对维护独立的平台选择状态
    const platformTabs = reactive({}); // { 'agentIdx-qIdx': 'twitter' | 'reddit' }

    // 获取某个问题的当前平台选择
    const getPlatformTab = (agentIdx, qIdx) => {
      const key = `${agentIdx}-${qIdx}`;
      return platformTabs[key] || "twitter";
    };

    // 设置某个问题的平台选择
    const setPlatformTab = (agentIdx, qIdx, platform) => {
      const key = `${agentIdx}-${qIdx}`;
      platformTabs[key] = platform;
    };

    const toggleAnswer = (key) => {
      const newSet = new Set(expandedAnswers.value);
      if (newSet.has(key)) {
        newSet.delete(key);
      } else {
        newSet.add(key);
      }
      expandedAnswers.value = newSet;
    };

    const formatAnswer = (text, expanded) => {
      if (!text) return "";
      if (expanded || text.length <= 400) return text;
      return text.substring(0, 400) + "...";
    };

    // 检查是否为平台占位文本
    const isPlaceholderText = (text) => {
      if (!text) return true;
      const t = text.trim();
      return (
        t === "（该平台未获得回复）" ||
        t === "(该平台未获得回复)" ||
        t === "[无回复]"
      );
    };

    // 尝试按问题编号分割回答
    const splitAnswerByQuestions = (answerText, questionCount) => {
      if (!answerText || questionCount <= 0) return [answerText];
      if (isPlaceholderText(answerText)) return [""];

      // 支持两种编号格式：
      // 1. "问题X：" 或 "问题X:" （中文格式，后端新格式）
      // 2. "1. " 或 "\n1. " （数字+点，旧格式兼容）
      let matches = [];
      let match;

      // 优先尝试 "问题X：" 格式
      const cnPattern = /(?:^|[\r\n]+)问题(\d+)[：:]\s*/g;
      while ((match = cnPattern.exec(answerText)) !== null) {
        matches.push({
          num: parseInt(match[1]),
          index: match.index,
          fullMatch: match[0],
        });
      }

      // 如果没匹配到，回退到 "数字." 格式
      if (matches.length === 0) {
        const numPattern = /(?:^|[\r\n]+)(\d+)\.\s+/g;
        while ((match = numPattern.exec(answerText)) !== null) {
          matches.push({
            num: parseInt(match[1]),
            index: match.index,
            fullMatch: match[0],
          });
        }
      }

      // 如果没有找到编号或只找到一个，返回整体
      if (matches.length <= 1) {
        const cleaned = answerText
          .replace(/^问题\d+[：:]\s*/, "")
          .replace(/^\d+\.\s+/, "")
          .trim();
        return [cleaned || answerText];
      }

      // 按编号提取各部分
      const parts = [];
      for (let i = 0; i < matches.length; i++) {
        const current = matches[i];
        const next = matches[i + 1];

        const startIdx = current.index + current.fullMatch.length;
        const endIdx = next ? next.index : answerText.length;

        let part = answerText.substring(startIdx, endIdx).trim();
        part = part.replace(/[\r\n]+$/, "").trim();
        parts.push(part);
      }

      if (parts.length > 0 && parts.some((p) => p)) {
        return parts;
      }

      return [answerText];
    };

    // 获取某个问题对应的回答
    const getAnswerForQuestion = (interview, qIdx, platform) => {
      const answer =
        platform === "twitter"
          ? interview.twitterAnswer
          : interview.redditAnswer || interview.twitterAnswer;
      if (!answer || isPlaceholderText(answer)) return answer || "";

      const questionCount = interview.questions?.length || 1;
      const answers = splitAnswerByQuestions(answer, questionCount);

      // 分割成功且索引有效
      if (answers.length > 1 && qIdx < answers.length) {
        return answers[qIdx] || "";
      }

      // 分割失败：第一个问题返回完整回答，其余返回空
      return qIdx === 0 ? answer : "";
    };

    // 检查某个问题是否有双平台回答（过滤占位文本）
    const hasMultiplePlatforms = (interview, qIdx) => {
      if (!interview.twitterAnswer || !interview.redditAnswer) return false;
      const twitterAnswer = getAnswerForQuestion(interview, qIdx, "twitter");
      const redditAnswer = getAnswerForQuestion(interview, qIdx, "reddit");
      // 两个平台都有真实回答（非占位文本）且内容不同
      return (
        !isPlaceholderText(twitterAnswer) &&
        !isPlaceholderText(redditAnswer) &&
        twitterAnswer !== redditAnswer
      );
    };

    return () =>
      h("div", { class: "interview-display" }, [
        // Header Section
        h("div", { class: "interview-header" }, [
          h("div", { class: "header-main" }, [
            h("div", { class: "header-title" }, "Agent Interview"),
            h("div", { class: "header-stats" }, [
              h("span", { class: "stat-item" }, [
                h(
                  "span",
                  { class: "stat-value" },
                  props.result.successCount || props.result.interviews.length,
                ),
                h("span", { class: "stat-label" }, "Interviewed"),
              ]),
              props.result.totalCount > 0 &&
                h("span", { class: "stat-divider" }, "/"),
              props.result.totalCount > 0 &&
                h("span", { class: "stat-item" }, [
                  h("span", { class: "stat-value" }, props.result.totalCount),
                  h("span", { class: "stat-label" }, "Total"),
                ]),
              props.resultLength && h("span", { class: "stat-divider" }, "·"),
              props.resultLength &&
                h(
                  "span",
                  { class: "stat-size" },
                  formatSize(props.resultLength),
                ),
            ]),
          ]),
          props.result.topic &&
            h("div", { class: "header-topic" }, props.result.topic),
        ]),

        // Agent Selector Tabs
        props.result.interviews.length > 0 &&
          h(
            "div",
            { class: "agent-tabs" },
            props.result.interviews.map((interview, i) =>
              h(
                "button",
                {
                  class: ["agent-tab", { active: activeIndex.value === i }],
                  key: i,
                  onClick: () => {
                    activeIndex.value = i;
                  },
                },
                [
                  h(
                    "span",
                    { class: "tab-avatar" },
                    interview.name ? interview.name.charAt(0) : i + 1,
                  ),
                  h(
                    "span",
                    { class: "tab-name" },
                    interview.title || interview.name || `Agent ${i + 1}`,
                  ),
                ],
              ),
            ),
          ),

        // Active Interview Detail
        props.result.interviews.length > 0 &&
          h("div", { class: "interview-detail" }, [
            // Agent Profile Card
            h("div", { class: "agent-profile" }, [
              h(
                "div",
                { class: "profile-avatar" },
                props.result.interviews[activeIndex.value]?.name?.charAt(0) ||
                  "A",
              ),
              h("div", { class: "profile-info" }, [
                h(
                  "div",
                  { class: "profile-name" },
                  props.result.interviews[activeIndex.value]?.name || "Agent",
                ),
                h(
                  "div",
                  { class: "profile-role" },
                  props.result.interviews[activeIndex.value]?.role || "",
                ),
                props.result.interviews[activeIndex.value]?.bio &&
                  h(
                    "div",
                    { class: "profile-bio" },
                    props.result.interviews[activeIndex.value].bio,
                  ),
              ]),
            ]),

            // Selection Reason - 选择理由
            props.result.interviews[activeIndex.value]?.selectionReason &&
              h("div", { class: "selection-reason" }, [
                h("div", { class: "reason-label" }, "选择理由"),
                h(
                  "div",
                  { class: "reason-content" },
                  props.result.interviews[activeIndex.value].selectionReason,
                ),
              ]),

            // Q&A Conversation Thread - 一问一答样式
            h(
              "div",
              { class: "qa-thread" },
              (props.result.interviews[activeIndex.value]?.questions?.length > 0
                ? props.result.interviews[activeIndex.value].questions
                : [
                    props.result.interviews[activeIndex.value]?.question ||
                      "No question available",
                  ]
              ).map((question, qIdx) => {
                const interview = props.result.interviews[activeIndex.value];
                const currentPlatform = getPlatformTab(activeIndex.value, qIdx);
                const answerText = getAnswerForQuestion(
                  interview,
                  qIdx,
                  currentPlatform,
                );
                const hasDualPlatform = hasMultiplePlatforms(interview, qIdx);
                const expandKey = `${activeIndex.value}-${qIdx}`;
                const isExpanded = expandedAnswers.value.has(expandKey);
                const isPlaceholder = isPlaceholderText(answerText);

                return h("div", { class: "qa-pair", key: qIdx }, [
                  // Question Block
                  h("div", { class: "qa-question" }, [
                    h("div", { class: "qa-badge q-badge" }, `Q${qIdx + 1}`),
                    h("div", { class: "qa-content" }, [
                      h("div", { class: "qa-sender" }, "Interviewer"),
                      h("div", { class: "qa-text" }, question),
                    ]),
                  ]),

                  // Answer Block
                  answerText &&
                    h(
                      "div",
                      {
                        class: [
                          "qa-answer",
                          { "answer-placeholder": isPlaceholder },
                        ],
                      },
                      [
                        h("div", { class: "qa-badge a-badge" }, `A${qIdx + 1}`),
                        h("div", { class: "qa-content" }, [
                          h("div", { class: "qa-answer-header" }, [
                            h(
                              "div",
                              { class: "qa-sender" },
                              interview?.name || "Agent",
                            ),
                            // 双平台切换按钮（仅在有真实双平台回答时显示）
                            hasDualPlatform &&
                              h("div", { class: "platform-switch" }, [
                                h(
                                  "button",
                                  {
                                    class: [
                                      "platform-btn",
                                      { active: currentPlatform === "twitter" },
                                    ],
                                    onClick: (e) => {
                                      e.stopPropagation();
                                      setPlatformTab(
                                        activeIndex.value,
                                        qIdx,
                                        "twitter",
                                      );
                                    },
                                  },
                                  [
                                    h(
                                      "svg",
                                      {
                                        class: "platform-icon",
                                        viewBox: "0 0 24 24",
                                        width: 12,
                                        height: 12,
                                        fill: "none",
                                        stroke: "currentColor",
                                        "stroke-width": 2,
                                      },
                                      [
                                        h("circle", {
                                          cx: "12",
                                          cy: "12",
                                          r: "10",
                                        }),
                                        h("line", {
                                          x1: "2",
                                          y1: "12",
                                          x2: "22",
                                          y2: "12",
                                        }),
                                        h("path", {
                                          d: "M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z",
                                        }),
                                      ],
                                    ),
                                    h("span", {}, t("step4.world1")),
                                  ],
                                ),
                                h(
                                  "button",
                                  {
                                    class: [
                                      "platform-btn",
                                      { active: currentPlatform === "reddit" },
                                    ],
                                    onClick: (e) => {
                                      e.stopPropagation();
                                      setPlatformTab(
                                        activeIndex.value,
                                        qIdx,
                                        "reddit",
                                      );
                                    },
                                  },
                                  [
                                    h(
                                      "svg",
                                      {
                                        class: "platform-icon",
                                        viewBox: "0 0 24 24",
                                        width: 12,
                                        height: 12,
                                        fill: "none",
                                        stroke: "currentColor",
                                        "stroke-width": 2,
                                      },
                                      [
                                        h("path", {
                                          d: "M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z",
                                        }),
                                      ],
                                    ),
                                    h("span", {}, t("step4.world2")),
                                  ],
                                ),
                              ]),
                          ]),
                          h("div", {
                            class: [
                              "qa-text",
                              "answer-text",
                              { "placeholder-text": isPlaceholder },
                            ],
                            innerHTML: isPlaceholder
                              ? answerText
                              : formatAnswer(answerText, isExpanded)
                                  .replace(
                                    /\*\*(.+?)\*\*/g,
                                    "<strong>$1</strong>",
                                  )
                                  .replace(/\n/g, "<br>"),
                          }),
                          // Expand/Collapse Button（占位文本不显示）
                          !isPlaceholder &&
                            answerText.length > 400 &&
                            h(
                              "button",
                              {
                                class: "expand-answer-btn",
                                onClick: () => toggleAnswer(expandKey),
                              },
                              isExpanded ? "Show Less" : "Show More",
                            ),
                        ]),
                      ],
                    ),
                ]);
              }),
            ),

            // Key Quotes Section
            props.result.interviews[activeIndex.value]?.quotes?.length > 0 &&
              h("div", { class: "quotes-section" }, [
                h("div", { class: "quotes-header" }, "Key Quotes"),
                h(
                  "div",
                  { class: "quotes-list" },
                  props.result.interviews[activeIndex.value].quotes
                    .slice(0, 3)
                    .map((quote, qi) => {
                      const cleanedQuote = cleanQuoteText(quote);
                      const displayQuote =
                        cleanedQuote.length > 200
                          ? cleanedQuote.substring(0, 200) + "..."
                          : cleanedQuote;
                      return h("blockquote", {
                        key: qi,
                        class: "quote-item",
                        innerHTML: renderMarkdown(displayQuote),
                      });
                    }),
                ),
              ]),
          ]),

        // Summary Section (Collapsible)
        props.result.summary &&
          h("div", { class: "summary-section" }, [
            h("div", { class: "summary-header" }, "Interview Summary"),
            h("div", {
              class: "summary-content",
              innerHTML: renderMarkdown(
                props.result.summary.length > 500
                  ? props.result.summary.substring(0, 500) + "..."
                  : props.result.summary,
              ),
            }),
          ]),
      ]);
  },
};

// Quick Search Display Component - Enhanced with full data rendering
const QuickSearchDisplay = {
  props: ["result", "resultLength"],
  setup(props) {
    const { t } = useI18n();
    const activeTab = ref("facts"); // 'facts', 'edges', 'nodes'
    const expandedFacts = ref(false);
    const INITIAL_SHOW_COUNT = 5;

    // Check if there are edges or nodes to show tabs
    const hasEdges = computed(
      () => props.result.edges && props.result.edges.length > 0,
    );
    const hasNodes = computed(
      () => props.result.nodes && props.result.nodes.length > 0,
    );
    const showTabs = computed(() => hasEdges.value || hasNodes.value);

    // Format result size for display
    const formatSize = (length) => {
      if (!length) return "";
      if (length >= 1000) {
        return `${(length / 1000).toFixed(1)}k chars`;
      }
      return `${length} chars`;
    };

    return () =>
      h("div", { class: "quick-search-display" }, [
        // Header Section
        h("div", { class: "quicksearch-header" }, [
          h("div", { class: "header-main" }, [
            h("div", { class: "header-title" }, "Quick Search"),
            h("div", { class: "header-stats" }, [
              h("span", { class: "stat-item" }, [
                h(
                  "span",
                  { class: "stat-value" },
                  props.result.count || props.result.facts.length,
                ),
                h("span", { class: "stat-label" }, "Results"),
              ]),
              props.resultLength && h("span", { class: "stat-divider" }, "·"),
              props.resultLength &&
                h(
                  "span",
                  { class: "stat-size" },
                  formatSize(props.resultLength),
                ),
            ]),
          ]),
          props.result.query &&
            h("div", { class: "header-query" }, [
              h("span", { class: "query-label" }, t("step4.searchLabel")),
              h("span", { class: "query-text" }, props.result.query),
            ]),
        ]),

        // Tab Navigation (only show if there are edges or nodes)
        showTabs.value &&
          h("div", { class: "quicksearch-tabs" }, [
            h(
              "button",
              {
                class: [
                  "quicksearch-tab",
                  { active: activeTab.value === "facts" },
                ],
                onClick: () => {
                  activeTab.value = "facts";
                },
              },
              [
                h(
                  "span",
                  { class: "tab-label" },
                  t("step4.tabFacts", { count: props.result.facts.length }),
                ),
              ],
            ),
            hasEdges.value &&
              h(
                "button",
                {
                  class: [
                    "quicksearch-tab",
                    { active: activeTab.value === "edges" },
                  ],
                  onClick: () => {
                    activeTab.value = "edges";
                  },
                },
                [
                  h(
                    "span",
                    { class: "tab-label" },
                    t("step4.tabEdges", { count: props.result.edges.length }),
                  ),
                ],
              ),
            hasNodes.value &&
              h(
                "button",
                {
                  class: [
                    "quicksearch-tab",
                    { active: activeTab.value === "nodes" },
                  ],
                  onClick: () => {
                    activeTab.value = "nodes";
                  },
                },
                [
                  h(
                    "span",
                    { class: "tab-label" },
                    t("step4.tabNodes", { count: props.result.nodes.length }),
                  ),
                ],
              ),
          ]),

        // Content Area
        h(
          "div",
          { class: ["quicksearch-content", { "no-tabs": !showTabs.value }] },
          [
            // Facts (always show if no tabs, or when facts tab is active)
            (!showTabs.value || activeTab.value === "facts") &&
              h("div", { class: "facts-panel" }, [
                !showTabs.value &&
                  h("div", { class: "panel-header" }, [
                    h(
                      "span",
                      { class: "panel-title" },
                      t("step4.panelSearchResults"),
                    ),
                    h(
                      "span",
                      { class: "panel-count" },
                      t("step4.totalCount", {
                        count: props.result.facts.length,
                      }),
                    ),
                  ]),
                props.result.facts.length > 0
                  ? h(
                      "div",
                      { class: "facts-list" },
                      (expandedFacts.value
                        ? props.result.facts
                        : props.result.facts.slice(0, INITIAL_SHOW_COUNT)
                      ).map((fact, i) =>
                        h("div", { class: "fact-item", key: i }, [
                          h("span", { class: "fact-number" }, i + 1),
                          h("div", { class: "fact-content" }, fact),
                        ]),
                      ),
                    )
                  : h(
                      "div",
                      { class: "empty-state" },
                      t("step4.emptySearchResults"),
                    ),
                props.result.facts.length > INITIAL_SHOW_COUNT &&
                  h(
                    "button",
                    {
                      class: "expand-btn",
                      onClick: () => {
                        expandedFacts.value = !expandedFacts.value;
                      },
                    },
                    expandedFacts.value
                      ? t("step4.collapse")
                      : t("step4.expandAll", {
                          count: props.result.facts.length,
                        }),
                  ),
              ]),

            // Edges Tab
            activeTab.value === "edges" &&
              hasEdges.value &&
              h("div", { class: "edges-panel" }, [
                h("div", { class: "panel-header" }, [
                  h(
                    "span",
                    { class: "panel-title" },
                    t("step4.panelRelatedEdges"),
                  ),
                  h(
                    "span",
                    { class: "panel-count" },
                    t("step4.totalCount", { count: props.result.edges.length }),
                  ),
                ]),
                h(
                  "div",
                  { class: "edges-list" },
                  props.result.edges.map((edge, i) =>
                    h("div", { class: "edge-item", key: i }, [
                      h("span", { class: "edge-source" }, edge.source),
                      h("span", { class: "edge-arrow" }, [
                        h("span", { class: "edge-line" }),
                        h("span", { class: "edge-label" }, edge.relation),
                        h("span", { class: "edge-line" }),
                      ]),
                      h("span", { class: "edge-target" }, edge.target),
                    ]),
                  ),
                ),
              ]),

            // Nodes Tab
            activeTab.value === "nodes" &&
              hasNodes.value &&
              h("div", { class: "nodes-panel" }, [
                h("div", { class: "panel-header" }, [
                  h(
                    "span",
                    { class: "panel-title" },
                    t("step4.panelRelatedNodes"),
                  ),
                  h(
                    "span",
                    { class: "panel-count" },
                    t("step4.totalEntityCount", {
                      count: props.result.nodes.length,
                    }),
                  ),
                ]),
                h(
                  "div",
                  { class: "nodes-grid" },
                  props.result.nodes.map((node, i) =>
                    h("div", { class: "node-tag", key: i }, [
                      h("span", { class: "node-name" }, node.name),
                      node.type && h("span", { class: "node-type" }, node.type),
                    ]),
                  ),
                ),
              ]),
          ],
        ),
      ]);
  },
};

const renderMarkdown = (content) => {
  if (!content) return "";

  // 去掉开头的二级标题（## xxx），因为章节标题已在外层显示
  let processedContent = content.replace(/^##\s+.+\n+/, "");

  // 处理代码块
  let html = processedContent.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    '<pre class="code-block"><code>$2</code></pre>',
  );

  // 处理行内代码
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // 处理标题
  html = html.replace(/^#### (.+)$/gm, '<h5 class="md-h5">$1</h5>');
  html = html.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 class="md-h2">$1</h2>');

  // 处理引用块
  html = html.replace(
    /^> (.+)$/gm,
    '<blockquote class="md-quote">$1</blockquote>',
  );

  // 处理列表 - 支持子列表
  html = html.replace(/^(\s*)- (.+)$/gm, (match, indent, text) => {
    const level = Math.floor(indent.length / 2);
    return `<li class="md-li" data-level="${level}">${text}</li>`;
  });
  html = html.replace(/^(\s*)(\d+)\. (.+)$/gm, (match, indent, num, text) => {
    const level = Math.floor(indent.length / 2);
    return `<li class="md-oli" data-level="${level}">${text}</li>`;
  });

  // 包装无序列表
  html = html.replace(
    /(<li class="md-li"[^>]*>.*?<\/li>\s*)+/g,
    '<ul class="md-ul">$&</ul>',
  );
  // 包装有序列表
  html = html.replace(
    /(<li class="md-oli"[^>]*>.*?<\/li>\s*)+/g,
    '<ol class="md-ol">$&</ol>',
  );

  // 清理列表项之间的所有空白
  html = html.replace(/<\/li>\s+<li/g, "</li><li");
  // 清理列表开始标签后的空白
  html = html.replace(/<ul class="md-ul">\s+/g, '<ul class="md-ul">');
  html = html.replace(/<ol class="md-ol">\s+/g, '<ol class="md-ol">');
  // 清理列表结束标签前的空白
  html = html.replace(/\s+<\/ul>/g, "</ul>");
  html = html.replace(/\s+<\/ol>/g, "</ol>");

  // 处理粗体和斜体
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/_(.+?)_/g, "<em>$1</em>");

  // 处理分隔线
  html = html.replace(/^---$/gm, '<hr class="md-hr">');

  // 处理换行 - 空行变成段落分隔，单换行变成 <br>
  html = html.replace(/\n\n/g, '</p><p class="md-p">');
  html = html.replace(/\n/g, "<br>");

  // 包装在段落中
  html = '<p class="md-p">' + html + "</p>";

  // 清理空段落
  html = html.replace(/<p class="md-p"><\/p>/g, "");
  html = html.replace(/<p class="md-p">(<h[2-5])/g, "$1");
  html = html.replace(/(<\/h[2-5]>)<\/p>/g, "$1");
  html = html.replace(/<p class="md-p">(<ul|<ol|<blockquote|<pre|<hr)/g, "$1");
  html = html.replace(/(<\/ul>|<\/ol>|<\/blockquote>|<\/pre>)<\/p>/g, "$1");
  // 清理块级元素前后的 <br> 标签
  html = html.replace(/<br>\s*(<ul|<ol|<blockquote)/g, "$1");
  html = html.replace(/(<\/ul>|<\/ol>|<\/blockquote>)\s*<br>/g, "$1");
  // 清理 <p><br> 紧跟块级元素的情况（多余空行导致）
  html = html.replace(
    /<p class="md-p">(<br>\s*)+(<ul|<ol|<blockquote|<pre|<hr)/g,
    "$2",
  );
  // 清理连续的 <br> 标签
  html = html.replace(/(<br>\s*){2,}/g, "<br>");
  // 清理块级元素后紧跟的段落开始标签前的 <br>
  html = html.replace(/(<\/ol>|<\/ul>|<\/blockquote>)<br>(<p|<div)/g, "$1$2");

  // 修复非连续有序列表的编号：当单项 <ol> 被段落内容隔开时，保持编号递增
  const tokens = html.split(
    /(<ol class="md-ol">(?:<li class="md-oli"[^>]*>[\s\S]*?<\/li>)+<\/ol>)/g,
  );
  let olCounter = 0;
  let inSequence = false;
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].startsWith('<ol class="md-ol">')) {
      const liCount = (tokens[i].match(/<li class="md-oli"/g) || []).length;
      if (liCount === 1) {
        olCounter++;
        if (olCounter > 1) {
          tokens[i] = tokens[i].replace(
            '<ol class="md-ol">',
            `<ol class="md-ol" start="${olCounter}">`,
          );
        }
        inSequence = true;
      } else {
        olCounter = 0;
        inSequence = false;
      }
    } else if (inSequence) {
      if (/<h[2-5]/.test(tokens[i])) {
        olCounter = 0;
        inSequence = false;
      }
    }
  }
  html = tokens.join("");

  return html;
};

export {
  InsightDisplay,
  InterviewDisplay,
  PanoramaDisplay,
  QuickSearchDisplay,
  getToolColor,
  getToolDisplayName,
  getToolIcon,
  parseInsightForge,
  parseInterview,
  parsePanorama,
  parseQuickSearch,
  renderMarkdown,
};
