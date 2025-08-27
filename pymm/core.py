# mibi/core.py
from __future__ import annotations
import inspect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple

# ============ 核心模型 ============
@dataclass
class Node:
    id: str                 # __qualname__，体现层级
    kind: str               # topic / issue / position / pro / con / note / question
    title: str              # 标题（默认由类名转空格）
    text: str               # 说明文本（来自类 docstring）
    parent: Optional[str]   # 父节点 id
    meta: dict = field(default_factory=dict)

@dataclass
class Edge:
    src: str
    dst: str
    rel: str                # contains / answers / supports / opposes / relates

class Registry:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._pending: List[Tuple[Any, Any, str]] = []  # (src_ref, dst_ref, rel)

    def add_node(self, n: Node):
        self.nodes[n.id] = n
        if n.parent:
            self.edges.append(Edge(n.parent, n.id, "contains"))

    def add_edge(self, src: str, dst: str, rel: str):
        self.edges.append(Edge(src, dst, rel))

    def defer(self, src_ref: Any, dst_ref: Any, rel: str):
        self._pending.append((src_ref, dst_ref, rel))

    # ---- 解析（对象或字符串路径） ----
    def _resolve_ref(self, ref: Any) -> Optional[str]:
        if isinstance(ref, str):
            if ref in self.nodes:
                return ref
            tail = ref.split(".")[-1]
            hits = [k for k in self.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        qn = getattr(ref, "__qualname__", None)
        if qn and (qn in self.nodes or any(k.endswith(f".{qn}") or k == qn for k in self.nodes)):
            return qn
        return qn  # 允许先返回名，等节点补注册后再匹配

    def _infer_src_from_class_body(self) -> Optional[str]:
        # 在 class 体内调用时，从调用栈里找 __qualname__
        f = inspect.currentframe()
        if not f: return None
        f = f.f_back
        while f:
            qn = f.f_locals.get("__qualname__")
            if isinstance(qn, str):
                return qn
            f = f.f_back
        return None

    def resolve_all(self):
        # 自动 IBIS 语义（保留能力，mind map 用不到也不碍事）
        for n in list(self.nodes.values()):
            p = self.nodes.get(n.parent) if n.parent else None
            if n.kind == "position" and p and p.kind == "issue":
                self.add_edge(n.id, p.id, "answers")
            if n.kind in ("pro", "con") and p and p.kind == "position":
                self.add_edge(n.id, p.id, "supports" if n.kind == "pro" else "opposes")
        # 解析延迟交叉链接
        for src_ref, dst_ref, rel in self._pending:
            src = self._resolve_ref(src_ref)
            dst = self._resolve_ref(dst_ref)
            if src and dst:
                self.add_edge(src, dst, rel)

REGISTRY = Registry()

# ============ 装饰器 ============
def _parent_of(qn: str) -> Optional[str]:
    return qn.rsplit(".", 1)[0] if "." in qn else None

def _title(obj, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    return obj.__name__.replace("_", " ")

def _decorate(kind: str):
    def apply(c, title: Optional[str] = None, **meta):
        qn = c.__qualname__
        REGISTRY.add_node(Node(
            id=qn,
            kind=kind,
            title=_title(c, title),
            text=(inspect.getdoc(c) or ""),
            parent=_parent_of(qn),
            meta=meta or {},
        ))
        _attach_link_methods(c, qn)
        return c

    def deco(*dargs, **dkwargs):
        """
        兼容两种用法：
        1) @Topic                    -> dargs[0] 是类对象
        2) @Topic("标题", tags=...)  -> dargs[0] 是标题字符串（或省略，用 title= 传）
        """
        # 情况 A：@Topic 直接装饰类（无参）
        if dargs and callable(dargs[0]):
            c = dargs[0]
            title = dkwargs.pop("title", None)
            return apply(c, title=title, **dkwargs)

        # 情况 B：@Topic("标题", ...) 返回真正的装饰器
        title_pos = dargs[0] if dargs else None
        title_kw  = dkwargs.pop("title", None)
        title = title_kw if title_kw is not None else title_pos

        def wrapper(c):
            return apply(c, title=title, **dkwargs)

        return wrapper

    return deco
    
Topic    = _decorate("topic")
Note     = _decorate("note")
Issue    = _decorate("issue")
Question = _decorate("question")
Position = _decorate("position")
Pro      = _decorate("pro")
Con      = _decorate("con")
Idea     = Position  # 同义

# ============ 交叉关系（把 relates 改成三个下划线 ___） ============
Ref = Union[str, Any]

def _link(rel: str, target: Ref, src: Optional[Ref] = None):
    if src is None:
        src = REGISTRY._infer_src_from_class_body()
    REGISTRY.defer(src, target, rel)

def supports(target: Ref, src: Optional[Ref] = None): _link("supports", target, src)
def opposes(target: Ref, src: Optional[Ref] = None):  _link("opposes",  target, src)
def answers(target: Ref, src: Optional[Ref] = None):  _link("answers",  target, src)

# 通用“关联边”改为三个下划线函数 ___：
def ___(target: Ref, src: Optional[Ref] = None):       _link("relates",  target, src)

def _attach_link_methods(cls: Any, myid: str):
    def _mk(rel: str):
        def inner(target: Ref):
            REGISTRY.defer(myid, target, rel)
            return cls   # 支持链式但通常不用
        return inner
    cls.supports = _mk("supports")
    cls.opposes  = _mk("opposes")
    cls.answers  = _mk("answers")
    cls.___      = _mk("relates")   # 类方法形式：SomeNode.___(OtherNode)

# ============ 可选输出 ============
def summarize():
    REGISTRY.resolve_all()
    kinds = {}
    for n in REGISTRY.nodes.values():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    print("Nodes:", len(REGISTRY.nodes), kinds)
    print("Edges:", len(REGISTRY.edges))

# ---- Mermaid 导出（Mindmap + Flowchart）----

def to_mermaid_mindmap(root=None, show_text=False, text_max_len=80) -> str:
    """
    导出为 Mermaid mindmap 语法。
    - 仅展示层级 contains（更像纯思维导图）。
    - root: 可为类对象或限定名字符串；None 表示导出所有顶层根。
    - show_text: 是否在标题后附加一小段 docstring 摘要。
    """
    import re

    REGISTRY.resolve_all()

    # 解析 root id
    def _resolve_id(ref):
        if ref is None:
            return None
        if isinstance(ref, str):
            if ref in REGISTRY.nodes:
                return ref
            tail = ref.split(".")[-1]
            hits = [k for k in REGISTRY.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        return getattr(ref, "__qualname__", None)

    # 构造子节点表
    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent:
            children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    # 选根
    if root_id := _resolve_id(root):
        roots = [root_id]
    else:
        roots = [n.id for n in REGISTRY.nodes.values() if not n.parent]
        roots.sort(key=lambda i: REGISTRY.nodes[i].title.lower())

    def _snippet(txt: str) -> str:
        if not txt or not show_text:
            return ""
        one = txt.strip().splitlines()[0].strip()
        if len(one) > text_max_len:
            one = one[: text_max_len - 1] + "…"
        return f": {one}" if one else ""

    lines = ["mindmap"]
    IND = "  "

    def emit(node_id: str, depth: int):
        n = REGISTRY.nodes[node_id]
        label = f"{n.title}{_snippet(n.text)}"
        lines.append(f"{IND*depth}{label}")
        for cid in children.get(node_id, []):
            emit(cid, depth + 1)

    for r in roots:
        emit(r, 1)

    return "\n".join(lines)


def to_mermaid_flowchart(
    root=None,
    include=("contains", "answers", "supports", "opposes", "relates"),
    show_text=True,
    wrap=28,
) -> str:
    """
    导出为 Mermaid flowchart 语法。
    - include: 选择导出的边类型。
    - show_text: 节点标签中附加简短说明（自动换行）。
    - wrap: 每行最大字符数（用 <br/> 换行）。
    """
    import re

    REGISTRY.resolve_all()

    # 解析 root id + 选取子树所有节点
    def _resolve_id(ref):
        if ref is None:
            return None
        if isinstance(ref, str):
            if ref in REGISTRY.nodes:
                return ref
            tail = ref.split(".")[-1]
            hits = [k for k in REGISTRY.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        return getattr(ref, "__qualname__", None)

    if (rid := _resolve_id(root)) is None and root is not None:
        raise ValueError(f"root 未解析：{root}")

    # 构造子节点表（只靠 parent）
    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent:
            children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    # 选出节点集合
    if rid:
        selected = set()
        stack = [rid]
        while stack:
            cur = stack.pop()
            if cur in selected:
                continue
            selected.add(cur)
            stack.extend(children.get(cur, []))
    else:
        selected = set(REGISTRY.nodes.keys())

    # 工具：id/标签
    def safe_id(qn: str) -> str:
        return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", qn)

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def wrap_html(s: str, width: int) -> str:
        if width <= 0:
            return s
        words = s.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 > width:
                lines.append(cur)
                cur = w
            else:
                cur = w if not cur else (cur + " " + w)
        if cur:
            lines.append(cur)
        return "<br/>".join(lines)

    # 输出
    lines = ["flowchart TD"]

    # 先输出节点
    ordered_nodes = sorted(selected, key=lambda i: REGISTRY.nodes[i].title.lower())
    for nid in ordered_nodes:
        n = REGISTRY.nodes[nid]
        label = n.title
        if show_text and n.text.strip():
            firstline = n.text.strip().splitlines()[0].strip()
            if firstline:
                label = label + "<br/>" + wrap_html(firstline, wrap)
        shape = "round" if n.kind in ("topic", "note") else "rect"
        open_br, close_br = ("(", ")") if shape == "round" else ("[", "]")
        lines.append(f'{safe_id(nid)}{open_br}"{esc(label)}"{close_br}')
    # 节点样式（按 kind）
    lines += [
        "classDef topic fill:#eef6ff,stroke:#5b8,stroke-width:1px;",
        "classDef issue fill:#fff6e5,stroke:#d48,stroke-width:1px;",
        "classDef position fill:#f3ffef,stroke:#5a5,stroke-width:1px;",
        "classDef pro fill:#eafff3,stroke:#5a5,stroke-width:1px;",
        "classDef con fill:#ffefef,stroke:#d55,stroke-width:1px;",
        "classDef note fill:#f7f7f7,stroke:#999,stroke-width:1px;",
        "classDef question fill:#fff,stroke:#888,stroke-dasharray: 4 2;",
    ]
    for nid in ordered_nodes:
        lines.append(f"class {safe_id(nid)} {REGISTRY.nodes[nid].kind};")

    # 再输出边
    def edge_line(e):
        a, b = safe_id(e.src), safe_id(e.dst)
        if e.rel == "contains":
            return f"{a} --> {b}"
        if e.rel == "relates":
            return f"{a} -. relates .-> {b}"
        # answers / supports / opposes
        return f'{a} -- "{e.rel}" --> {b}'

    selected_edges = [
        e for e in REGISTRY.edges
        if e.rel in include and e.src in selected and e.dst in selected
    ]
    # 优先 contains，再其他关系，避免视觉拥挤
    selected_edges.sort(key=lambda e: (0 if e.rel == "contains" else 1, e.rel, e.src, e.dst))
    for e in selected_edges:
        lines.append(edge_line(e))

    return "\n".join(lines)    