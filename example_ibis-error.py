# ibis_example.py
from ibmm import Issue, Position, Pro, Con, ___, supports, opposes, answers
from ibmm import to_mermaid_flowchart, summarize

@Issue("Should we adopt a remote-first policy?")
class Remote_First:
    """是否采用“远程优先”的公司政策？"""

    @Position("Yes")
    class Yes:
        """赞成：更灵活、拓展人才池。"""

        @Pro
        class Wider_Talent_Pool:
            """全球招聘，扩大人才面。"""
            # 合法：Pro → Position 的“支持”
            +supports.Remote_First.No.Culture_Cohesion

        @Con
        class Collaboration_Gaps:
            """异步沟通与时区差影响协作效率。"""
            # 合法：Con → Position 的“反对”
            +opposes.Remote_First.No.Security_Risks

    @Position("No")
    class No:
        """反对：文化/安全/管理成本考虑。"""

        @Pro
        class Culture_Cohesion:
            """线下共处增强团队归属感与协作速度。"""

        @Pro
        class Security_Risks:
            """远程办公扩大攻击面、端点管理更复杂。"""

        @Con
        class Hiring_Challenges:
            """本地化招聘覆盖有限。"""

# 独立 Position：显式回答 Issue（Position → Issue 合法）
@Position("Hybrid (3–2 office)")
class Hybrid_3_2:
    """混合：每周 3 天到岗、2 天远程。"""
    +answers.Remote_First

if __name__ == "__main__":
    print(to_mermaid_flowchart(
        "Remote_First",
        include=("contains","answers","supports","opposes","relates"),
        show_text=True,
        wrap=30
    ))
    print()
    summarize()