# ibmm/ibis.py
from __future__ import annotations
from .core import (
    Topic, Title, NodeKind, Note, Question, ___,
    make_kind, define_relation, auto_edge, REGISTRY
)

# 节点类型：IBIS 扩展（仍可在内部混用 Title/NodeKind 作 mind map 展开）
Issue    = make_kind("issue")
Position = make_kind("position")
Pro      = make_kind("pro")
Con      = make_kind("con")
Idea     = Position  # 同义

# 关系：按祖先类型放宽（dst 可为 Position/Issue 的后代：Title/Node）
supports = define_relation("supports", allow=("pro", "position"),   allow_dst_descendant=True)
opposes  = define_relation("opposes",  allow=("con", "position"),   allow_dst_descendant=True)
answers  = define_relation("answers",  allow=("position", "issue"), allow_dst_descendant=True)

# 自动语义边（靠层级推断）
auto_edge(child_kind="position", parent_kind="issue",    rel_name="answers")
auto_edge(child_kind="pro",      parent_kind="position", rel_name="supports")
auto_edge(child_kind="con",      parent_kind="position", rel_name="opposes")