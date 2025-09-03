from ibmm import Topic, Note, Issue, Position, Pro, Con, ___, supports, opposes, answers

@Issue("内容")
class Contents:
    @Position
    class arXiv:
        """"""
        +___.Target.Tactics
        +___.Target.Implementation
    @Position("头部品牌的AI动态")
    class TopBrands:
        """"""
        +___.Target.Tactics
        +___.Target.Strategy
        +___.Target.Procurement
    @Position("eval 数据集")
    class EvalDataset:
        """"""
        +___.Target.Tactics
        +___.Target.Strategy
        +___("扩展到其他行业").Target.Investment
        @Note("之于各类软件工程的加权值")
        class ProjectTypeWeight:
            """"""
            @Note("编程语言，没包含的根据相近程度")
            class PL:
                """"""
            @Note("技术新旧")
            class Timely:
                """"""
            @Note("领域")
            class Domain:
                """"""
            @Note("牵涉")
            class Condition:
                """from scratch还是升级"""
        @Note("测试")
        class Test:
            """模型、agent"""
@Topic("对象")
class Target:
    @Topic("战略")
    class Strategy:
       pass
    @Topic("战术")
    class Tactics:
       pass
    @Topic("实现")
    class Implementation:
        pass
    @Topic("采购")
    class Procurement:
       pass
    @Topic("投资")
    class Investment:
        pass
