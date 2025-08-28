# ibmm/core.py
from __future__ import annotations
import inspect, os, re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple

# ---------- 内部扩展钩子（对扩展隐藏） ----------
PROXY_BINDERS: List[Callable[[Any, str], None]] = []
VALIDATORS:     List[Callable[[str, str, str, "Registry", Optional[tuple[str,int]]], None]] = []
FINALIZERS:     List[Callable[["Registry"], None]] = []

def _register_proxy_binder(fn: Callable[[Any, str], None]) -> None: PROXY_BINDERS.append(fn)
def _register_validator(fn: Callable[[str, str, str, "Registry", Optional[tuple[str,int]]], None]) -> None: VALIDATORS.append(fn)
def _register_finalizer(fn: Callable[["Registry"], None]) -> None: FINALIZERS.append(fn)

# ---------- 数据结构 ----------
@dataclass
class Node:
    id: str                 # __qualname__
    kind: str               # topic/issue/position/pro/con/title/node/note/question/...
    title: str
    text: str
    parent: Optional[str]
    meta: dict = field(default_factory=dict)

@dataclass
class Edge:
    src: str
    dst: str
    rel: str                # contains / relates / supports / opposes / answers / ...

@dataclass
class _Pending:
    src_ref: Any
    dst_ref: Any
    rel: str
    origin: Optional[tuple[str, int]]  # (filename, lineno)

class Registry:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._pending: List[_Pending] = []

    # 节点/边
    def add_node(self, n: Node):
        self.nodes[n.id] = n
        if n.parent:
            self.edges.append(Edge(n.parent, n.id, "contains"))

    def defer(self, src_ref: Any, dst_ref: Any, rel: str, origin: Optional[tuple[str,int]] = None):
        self._pending.append(_Pending(src_ref, dst_ref, rel, origin))

    def add_edge(self, src: str, dst: str, rel: str):
        self.edges.append(Edge(src, dst, rel))

    # 解析
    def _resolve_ref(self, ref: Any) -> Optional[str]:
        if isinstance(ref, str):
            if ref in self.nodes:
                return ref
            tail = ref.split(".")[-1]
            hits = [k for k in self.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        qn = getattr(ref, "__qualname__", None)
        if isinstance(qn, str):
            if qn in self.nodes:
                return qn
            hits = [k for k in self.nodes if k.endswith(f".{qn}") or k == qn]
            return hits[0] if len(hits) == 1 else None
        return None

    def _infer_src_from_class_body(self) -> Optional[str]:
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
        # 自动边（扩展可注入）
        for fn in FINALIZERS:
            fn(self)

        # 解析延迟边 + 规则校验
        for p in self._pending:
            src = self._resolve_ref(p.src_ref) or (
                p.src_ref if isinstance(p.src_ref, str) else getattr(p.src_ref, "__qualname__", None)
            )
            dst = self._resolve_ref(p.dst_ref) or (
                p.dst_ref if isinstance(p.dst_ref, str) else getattr(p.dst_ref, "__qualname__", None)
            )
            if src and dst:
                for v in VALIDATORS:
                    v(p.rel, src, dst, self, p.origin)
                self.add_edge(src, dst, p.rel)

REGISTRY = Registry()

# ---------- 装饰器 ----------
def _parent_of(qn: str) -> Optional[str]:
    return qn.rsplit(".", 1)[0] if "." in qn else None

def _title(obj, explicit: Optional[str]) -> str:
    return explicit if explicit is not None else obj.__name__.replace("_", " ")

def make_kind(kind: str):
    def apply(c, title: Optional[str] = None, **meta):
        qn = c.__qualname__
        REGISTRY.add_node(Node(
            id=qn, kind=kind, title=_title(c, title),
            text=(inspect.getdoc(c) or ""), parent=_parent_of(qn), meta=meta or {}
        ))
        for binder in PROXY_BINDERS: binder(c, qn)
        return c
    def deco(*dargs, **dkwargs):
        if dargs and callable(dargs[0]):  # @Kind
            c = dargs[0]; title = dkwargs.pop("title", None)
            return apply(c, title=title, **dkwargs)
        title_pos = dargs[0] if dargs else None
        title_kw  = dkwargs.pop("title", None)
        title = title_kw if title_kw is not None else title_pos
        def wrapper(c): return apply(c, title=title, **dkwargs)
        return wrapper
    return deco

# 基础 mind map 类型（供扩展复用）
Topic    = make_kind("topic")
Title    = make_kind("title")   # 专用于 mind map 内的小标题
NodeKind = make_kind("node")    # 叶子或任意节点
Note     = make_kind("note")
Question = make_kind("question")

# ---------- 一元加号关系代理 ----------
class _RelProxy:
    """
    写法：
      类体内（src=当前类）:  +___.A.B.C
      类对象（src=该类）  :  +Some.___.A.B
      下标路径             :  +___.["A.B.C"]
    """
    __slots__ = ("rel", "path", "src")
    def __init__(self, rel: str, path: str = "", src: Optional[str] = None):
        object.__setattr__(self, "rel", rel)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "src", src)
    def __getattr__(self, name: str) -> "_RelProxy":
        sep = "" if not self.path else "."
        return self.__class__(self.rel, f"{self.path}{sep}{name}", self.src)
    def __getitem__(self, dotted: str) -> "_RelProxy":
        return self.__class__(self.rel, dotted, self.src)
    def __pos__(self):
        if not self.path:
            raise ValueError(f"Empty target path for relation '{self.rel}'.")
        s = self.src or REGISTRY._infer_src_from_class_body()
        # 捕获调用处文件/行号
        frame = inspect.currentframe().f_back
        fi = inspect.getframeinfo(frame)
        origin = (fi.filename, fi.lineno)
        REGISTRY.defer(s, self.path, self.rel, origin=origin)
        return self

# 全局“关联”
___ = _RelProxy("relates")

def _bind_relates(cls: Any, node_id: str):
    setattr(cls, "___", _RelProxy("relates", src=node_id))
_register_proxy_binder(_bind_relates)

# ---------- 友好扩展 API ----------
def define_relation(name: str,
                    *,
                    allow: Optional[Tuple[str, str]] = None,
                    allow_dst_descendant: bool = False) -> _RelProxy:
    """
    定义一元加号关系（如 'supports'）。如果给出 allow=(src_kind, dst_kind)：
      - 若 allow_dst_descendant=True，则允许目标是该 dst_kind 的“后代”（祖先链上包含 dst_kind）。
    """
    proxy = _RelProxy(name)
    def _bind(cls: Any, node_id: str):
        setattr(cls, name, _RelProxy(name, src=node_id))
    _register_proxy_binder(_bind)

    if allow:
        s_kind, d_kind = allow
        def _validator(rel: str, src_id: str, dst_id: str, reg: Registry, origin: Optional[tuple[str,int]]):
            if rel != name: return
            sk = reg.nodes[src_id].kind
            # 目标是否是 d_kind，或 d_kind 的祖先？
            ok_dst = False
            cur = dst_id
            while True:
                dk = reg.nodes[cur].kind
                if dk == d_kind:
                    ok_dst = True; break
                if not allow_dst_descendant: break
                parent = reg.nodes[cur].parent
                if not parent: break
                cur = parent
            if not (sk == s_kind and ok_dst):
                where = f" at {os.path.basename(origin[0])}:{origin[1]}" if origin else ""
                raise ValueError(f"{name}: 仅允许 {s_kind} → {d_kind}{'(含其后代)' if allow_dst_descendant else ''}"
                                 f"（实际 {sk} → {reg.nodes[dst_id].kind}）: {src_id} -> {dst_id}{where}")
        _register_validator(_validator)

    return proxy

def auto_edge(child_kind: str, parent_kind: str, rel_name: str) -> None:
    """根据层级关系自动添加语义边。"""
    def _finalizer(reg: Registry):
        for n in list(reg.nodes.values()):
            if not n.parent: continue
            p = reg.nodes.get(n.parent)
            if p and n.kind == child_kind and p.kind == parent_kind:
                reg.add_edge(n.id, p.id, rel_name)
    _register_finalizer(_finalizer)

# ---------- 导出 ----------
def summarize():
    REGISTRY.resolve_all()
    kinds = {}
    for n in REGISTRY.nodes.values():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    print("Nodes:", len(REGISTRY.nodes), kinds)
    print("Edges:", len(REGISTRY.edges))

def to_mermaid_mindmap(root=None, show_text=False, text_max_len=80) -> str:
    REGISTRY.resolve_all()

    def _resolve_id(ref):
        if ref is None: return None
        if isinstance(ref, str):
            if ref in REGISTRY.nodes: return ref
            tail = ref.split(".")[-1]
            hits = [k for k in REGISTRY.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        return getattr(ref, "__qualname__", None)

    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent:
            children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    roots = [ _resolve_id(root) ] if _resolve_id(root) else \
            sorted([nid for nid, n in REGISTRY.nodes.items() if not n.parent],
                   key=lambda i: REGISTRY.nodes[i].title.lower())

    def snippet(txt: str) -> str:
        if not show_text or not txt.strip(): return ""
        head = txt.strip().splitlines()[0].strip()
        if len(head) > text_max_len: head = head[:text_max_len-1] + "…"
        return f": {head}" if head else ""

    lines = ["mindmap"]
    IND = "  "
    def emit(nid: str, d: int):
        n = REGISTRY.nodes[nid]
        lines.append(f"{IND*d}{n.title}{snippet(n.text)}")
        for cid in children.get(nid, []): emit(cid, d+1)
    for r in roots: emit(r, 1)
    return "\n".join(lines)

def to_mermaid_flowchart(root=None,
                         include=("contains","answers","supports","opposes","relates"),
                         show_text=True, wrap=28) -> str:
    REGISTRY.resolve_all()

    def _resolve_id(ref):
        if ref is None: return None
        if isinstance(ref, str):
            if ref in REGISTRY.nodes: return ref
            tail = ref.split(".")[-1]
            hits = [k for k in REGISTRY.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        return getattr(ref, "__qualname__", None)
    rid = _resolve_id(root) if root else None

    # gather children
    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent: children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    if rid:
        selected = set(); stack = [rid]
        while stack:
            cur = stack.pop()
            if cur in selected: continue
            selected.add(cur)
            stack.extend(children.get(cur, []))
    else:
        selected = set(REGISTRY.nodes.keys())

    def safe_id(qn: str) -> str: return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", qn)
    def esc(s: str) -> str: return s.replace("\\", "\\\\").replace('"', '\\"')
    def wrap_html(s: str, width: int) -> str:
        if width <= 0: return s
        words = s.split(); lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + (1 if cur else 0) > width: lines.append(cur); cur = w
            else: cur = w if not cur else (cur + " " + w)
        if cur: lines.append(cur); return "<br/>".join(lines)

    lines = ["flowchart TD"]
    ordered_nodes = sorted(selected, key=lambda i: REGISTRY.nodes[i].title.lower())
    for nid in ordered_nodes:
        n = REGISTRY.nodes[nid]
        label = n.title
        if show_text and n.text.strip():
            head = n.text.strip().splitlines()[0].strip()
            if head: label = label + "<br/>" + wrap_html(head, wrap)
        # 形状：mind-map类圆角，其他矩形
        rounded = n.kind in ("topic","title","node","note")
        br_l, br_r = ("(", ")") if rounded else ("[", "]")
        lines.append(f'{safe_id(nid)}{br_l}"{esc(label)}"{br_r}')
    lines += [
        "classDef topic fill:#eef6ff,stroke:#5b8,stroke-width:1px;",
        "classDef title fill:#f0f7ff,stroke:#69c,stroke-width:1px;",
        "classDef node fill:#ffffff,stroke:#bbb,stroke-width:1px;",
        "classDef note fill:#f7f7f7,stroke:#999,stroke-width:1px;",
        "classDef issue fill:#fff6e5,stroke:#d48,stroke-width:1px;",
        "classDef position fill:#f3ffef,stroke:#5a5,stroke-width:1px;",
        "classDef pro fill:#eafff3,stroke:#5a5,stroke-width:1px;",
        "classDef con fill:#ffefef,stroke:#d55,stroke-width:1px;",
        "classDef question fill:#fff,stroke:#888,stroke-dasharray: 4 2;",
    ]
    for nid in ordered_nodes:
        lines.append(f"class {safe_id(nid)} {REGISTRY.nodes[nid].kind};")

    def edge_line(e: Edge) -> str:
        a, b = safe_id(e.src), safe_id(e.dst)
        if e.rel == "contains": return f"{a} --> {b}"
        if e.rel == "relates":  return f"{a} -. relates .-> {b}"
        return f'{a} -- "{e.rel}" --> {b}'

    selected_edges = [e for e in REGISTRY.edges if e.rel in include and e.src in selected and e.dst in selected]
    selected_edges.sort(key=lambda e: (0 if e.rel=="contains" else 1, e.rel, e.src, e.dst))
    for e in selected_edges: lines.append(edge_line(e))
    return "\n".join(lines)