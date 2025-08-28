# ibmm/__init__.py

from .core import (
    # 基础 mind map
    Topic, Title, NodeKind, Note, Question, ___,
    # 导出/工具
    to_mermaid_mindmap, to_mermaid_flowchart, summarize,
    # 可选：内部数据结构（需要时再用）
    REGISTRY, Node, Edge,
)

# IBIS 扩展
from .ibis import (
    Issue, Position, Pro, Con, Idea,
    supports, opposes, answers,
)

__all__ = [
    # core
    "Topic", "Title", "NodeKind", "Note", "Question", "___",
    "to_mermaid_mindmap", "to_mermaid_flowchart", "summarize",
    "REGISTRY", "Node", "Edge",
    # ibis
    "Issue", "Position", "Pro", "Con", "Idea",
    "supports", "opposes", "answers",
]