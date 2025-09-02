# ibis_example.py  — 兼容你当前“严格 IBIS 规则”的版本
from ibmm import Issue, Position, Pro, Con, ___, supports, opposes, answers
from ibmm import to_mermaid_flowchart, summarize

@Issue("Should we adopt a remote-first policy?")
class Remote_First:
    """是否采用“远程优先”的公司政策？"""

    @Position("👍赞成")
    class Yes:
        """更灵活、拓展人才池。"""

        @Pro
        class Wider_Talent_Pool:
            """全球招聘，扩大人才面。"""
            # ✅ 合法：Pro → Position
            +supports.Remote_First.Yes
            # 如需表达“与 No.Culture_Cohesion 有所关联/对照”，可用中性关联：
            +___("随意关联，不建议").Remote_First.No.Culture_Cohesion   # 不作语义强约束

        @Con
        class Collaboration_Gaps:
            """异步沟通与时区差影响协作效率。"""
            # ✅ 合法：Con → Position（此处反对 'Yes' 立场本身）
            +opposes.Remote_First.Yes
            # 如果你理解为“这个缺点使 No 更有说服力”，仍然用 Con→Position：
            # +opposes.Remote_First.No   （按你的语义选择其一）

    @Position("🙅反对")
    class No:
        """文化/安全/管理成本考虑。"""

        @Pro
        class Culture_Cohesion:
            """线下共处增强团队归属感与协作速度。"""
            # （位于 No.Position 下会自动生成 Pro→Position 的 supports 边，无需手写）

        @Pro
        class Security_Risks:
            """远程办公扩大攻击面、端点管理更复杂。"""

        @Con
        class Hiring_Challenges:
            """本地化招聘覆盖有限。"""
            # ✅ 合法：Con → Position（反对 'Yes' 立场）
            +opposes.Remote_First.Yes

# 独立 Position：显式回答 Issue（Position → Issue 合法）
@Position("Hybrid (3–2 office)")
class Hybrid_3_2:
    """混合：每周 3 天到岗、2 天远程。"""
    +answers.Remote_First

if __name__ == "__main__":
    print(to_mermaid_flowchart(
        "Remote_First",
        include=("contains","answers","supports","opposes","relates"),
        show_text=True, wrap=30
    ))
    print()
    summarize()
