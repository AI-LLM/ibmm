# example_mindmap.py
from pymm import Topic, Note, ___, summarize, to_mermaid_mindmap, to_mermaid_flowchart

@Topic("AI 学习平台（路线图）")
class AI_Learn:
    """目标：以“每周有效学习时长”为北极星，打造自适应学习生态。"""

    @Topic("战略")
    class Strategy:
        """顶层战略与边界。"""

        @Topic("受众细分")
        class Segments:
            """核心用户是谁？K12 / 高校 / 终身学习。"""

            @Topic("K12")
            class K12:
                """家长付费 + 学校合作；学科：数学/英语/科学。"""

            @Topic("HigherEd")
            class HigherEd:
                """高校课程辅助，论文/实验/编程辅导。"""

            @Topic("Lifelong")
            class Lifelong:
                """成人技能提升：语言/编程/管理/写作。"""

        @Topic("护城河")
        class Moats:
            """数据、分发、教学法与品牌。"""

            @Topic("Data Moat")
            class Data_Moat:
                """专有学习过程数据与标注体系。"""
                # 与 AI 能力中的 RAG 强关联
                ___("AI_Learn.Product.AI_Capabilities.RAG") #向下引用，通过字符串

            @Topic("Distribution")
            class Distribution:
                """渠道与生态位：学校合作、社区、创作者。"""

            @Topic("Pedagogy")
            class Pedagogy:
                """以学习科学为支撑的教学设计（检索练习、间隔复习等）。"""
                ___(lambda: AI_Learn.Product.Core.Assessment) #向下引用

    @Topic("产品")
    class Product:
        """面向学习闭环：目标设定 → 学 → 练 → 测 → 复盘。"""

        @Topic("核心功能")
        class Core:
            """可组合的核心模块。"""

            @Topic("Tutor")
            class Tutor:
                """对话式辅导：讲解、启发、示例与类比。"""

            @Topic("Assessment")
            class Assessment:
                """形成性/终结性评测；自适应难度与错因诊断。"""

            @Topic("Planner")
            class Planner:
                """学习计划自动生成与动态调整。"""

        @Topic("AI 能力")
        class AI_Capabilities:
            """模型 + 工具 + 安全。"""

            @Topic("Model")
            class Model:
                """自研或托管大模型，压测 TPS 与延迟。"""

            @Topic("RAG")
            class RAG:
                """课程/题库/作业的检索增强生成。"""

            @Topic("Safety")
            class Safety:
                """内容安全、偏见治理与家长控制。"""

            # 章节间关联：评测依赖 RAG 检索命中率
            ___("AI_Learn.Product.Core.Assessment")

    @Topic("GTM（获客与变现）")
    class GTM:
        """增长与货币化路径。"""

        @Topic("销售")
        class Sales:
            """ToB 校园合作；ToC 家庭直接订阅。"""

        @Topic("伙伴&渠道")
        class Partnerships:
            """出版社/学校/内容创作者。"""

        @Topic("定价")
        class Pricing:
            """分层订阅 + 家庭套餐 + 校园授权。"""

        # 分发与护城河强关联（类方法写法）
        Partnerships.___("AI_Learn.Strategy.Moats.Distribution")

    @Topic("运营")
    class Ops:
        """日常运营与服务质量。"""

        @Topic("支持与客服")
        class Support:
            """7x12 在线支持；知识库；自助工单。"""

        @Topic("内容审核")
        class Moderation:
            """题目/答案/对话审核，未成年保护。"""
            ___("AI_Learn.Product.AI_Capabilities.Safety")

    @Topic("风险")
    class Risks:
        """识别并应对主要风险。"""

        @Topic("隐私")
        class Privacy:
            """数据合规（GDPR/COPPA）；脱敏与最小化。"""
            ___("AI_Learn.Product.AI_Capabilities.Safety")

        @Topic("偏见")
        class Bias:
            """语言与学科偏见治理；可解释性。"""

        @Topic("合规")
        class Compliance:
            """考试与认证合规；版权与引用。"""
            ___("AI_Learn.Product.AI_Capabilities.RAG")

    @Topic("指标")
    class Metrics:
        """量化目标与健康度。"""

        @Topic("北极星")
        class North_Star:
            """每周有效学习时长（分钟/用户）"""

        @Topic("留存")
        class Retention:
            """D7/D30 留存；家庭续费率。"""

        # 指标与产品模块的互相关联
        North_Star.___("AI_Learn.Product.Core.Planner")
        Retention.___("AI_Learn.GTM.Pricing")
    ___(AI_Learn.GTM.Pricing)

# 可选小结（无需输出也行）
if __name__ == "__main__":
    #summarize()
    mm = to_mermaid_mindmap(AI_Learn, show_text=True)
    print(mm)
    fc = to_mermaid_flowchart("AI_Learn", include=("contains","relates"))
    print(fc)