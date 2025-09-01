# example_mixed.py
from ibmm import Topic, Title, Note, NodeKind, ___
from ibmm import Issue, Position, Pro, Con, supports, opposes, answers
from ibmm import to_mermaid_mindmap, to_mermaid_flowchart, summarize

@Topic("Open Data Portal Project")
class ODP:
    """总体规划（mind map 部分）"""

    @Title #等价于@Title("Vision")
    class Vision:
        """开放数据促进创新与透明。"""
        +___("optional label").Gov_Sponsors.Strategy  # 纯关联

    @Title
    class Workstreams:
        @Title
        class Ingestion: """数据接入与标准化"""
        @Title
        class Catalog:   """元数据目录与搜索"""
        @Note
        class API:       """开放 API 与限流"""
        @NodeKind
        class Apps:      """示范应用与生态"""

@Topic("Government Stakeholders")
class Gov_Sponsors:
    @Title
    class Strategy:
        """开放政府、数字化转型、法规配套。"""

# ===== IBIS 问题与立场（同时允许像 mind map 一样展开）=====
@Issue("Should we open-source the portal stack?")
class OS_Question:
    """是否将门户技术栈开源？
    [Github](http://github.com)
    ![](https://github.githubassets.com/assets/mona-loading-default-c3c7aad1282f.gif)
    """

    @Position
    class Yes:
        """赞成：生态协作、透明与信任。"""

        # mind map 式展开
        @Title
        class Rationale:
            @Title
            class Ecosystem: """吸引开发者与高校合作"""
            @Note
            class Trust:     """公众与企业更信任"""

        @Pro
        class Lower_Costs:
            """共享改进、降低长期维护成本。"""
            # Pro → Position 的后代（Title/Node）：✅ 放宽校验允许
            +supports.OS_Question.Yes.Rationale.Ecosystem

        @Con
        class Monetization_Risk:
            """直接授权收入下降；需服务化。"""
            # Con → Position（或其后代），都合法
            +opposes.OS_Question.Yes

    @Position
    class No:
        """反对：控制与合规优先。"""

        @Title
        class Concerns:
            @Title
            class Security: """供应链与攻击面风险"""
            @Title
            class Compliance: """合规审计压力"""

        @Pro
        class Risk_Control:
            """更易做端到端安全管控。"""

        @Con
        class Slower_Adoption:
            """生态增长较慢，市场心智弱。"""
            +opposes.OS_Question.Yes.Rationale.Trust

# 独立 Position：明确 answer Issue（允许直接指向 Issue 或其 Title/Node）
@Position("Hybrid: core open, add-ons closed")
class Hybrid:
    """核心开源 + 商业增强组件"""
    +answers.OS_Question   # ✅ Position → Issue

# ===== 输出 =====
if __name__ == "__main__":
    print("=== Mermaid Mindmap (root: ODP) ===")
    print(to_mermaid_mindmap(ODP, show_text=True))
    print("=== Mermaid Flowchart (root: ODP) ===")
    print(to_mermaid_flowchart(ODP, show_text=True))
    print("\n=== Mermaid Flowchart (root: OS_Question) ===")
    print(to_mermaid_flowchart("OS_Question",
                               include=("contains","answers","supports","opposes","relates"),
                               show_text=True))
    print()
    summarize()
