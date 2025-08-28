# ibmm/__init__.py
from .core import (
    Topic, Note, Question, ___,
    REGISTRY, Node, Edge,
    to_mermaid_flowchart, to_mermaid_mindmap, summarize,
)
from .ibis import (
    Issue, Position, Pro, Con, Idea,
    supports, opposes, answers,
)