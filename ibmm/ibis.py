# ibmm/ibis.py
from __future__ import annotations
from .core import Topic, make_kind, define_relation, auto_edge, ___  # noqa: F401

# 1) 定义 IBIS 节点类型（继承自 Topic 的概念，无需理解内部细节）
Issue    = make_kind("issue")
Position = make_kind("position")
Pro      = make_kind("pro")
Con      = make_kind("con")
Idea     = Position  # 同义

# 2) 启用 IBIS 语义（只需这一组声明）
#    - 跨层级关系（+supports/+opposes/+answers），并限制合法的源/目标类型
supports = define_relation("supports", allow=("pro", "position"))
opposes  = define_relation("opposes",  allow=("con", "position"))
answers  = define_relation("answers",  allow=("position", "issue"))

#    - 基于层级自动补边：Position⊂Issue => answers；Pro⊂Position => supports；Con⊂Position => opposes
auto_edge(child_kind="position", parent_kind="issue",    rel_name="answers")
auto_edge(child_kind="pro",      parent_kind="position", rel_name="supports")
auto_edge(child_kind="con",      parent_kind="position", rel_name="opposes")