# ibmm/core.py
from __future__ import annotations
import inspect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Tuple
import inspect, os

# ---------- 内部扩展钩子（ibis.py 不需要了解这些） ----------
PROXY_BINDERS: List[Callable[[Any, str], None]] = []
VALIDATORS:     List[Callable[[str, str, str, "Registry", Optional[tuple[str,int]]], None]] = []
FINALIZERS:     List[Callable[["Registry"], None]] = []

def _register_proxy_binder(fn: Callable[[Any, str], None]) -> None:
    PROXY_BINDERS.append(fn)

def _register_validator(fn: Callable[[str, str, str, "Registry", Optional[tuple[str,int]]], None]) -> None:
    VALIDATORS.append(fn)

def _register_finalizer(fn: Callable[["Registry"], None]) -> None:
    FINALIZERS.append(fn)

# ---------- 数据结构 ----------
@dataclass
class Node:
    id: str                 # __qualname__
    kind: str               # topic / issue / position / pro / con / note / question / ...
    title: str
    text: str
    parent: Optional[str]
    meta: dict = field(default_factory=dict)

@dataclass
class Edge:
    src: str
    dst: str
    rel: str                # contains / relates / supports / opposes / answers / ...

# ---------- Pending 结构：携带来源 ----------
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

    # ---- 节点 & 边 ----
    def add_node(self, n: Node):
        self.nodes[n.id] = n
        if n.parent:
            self.edges.append(Edge(n.parent, n.id, "contains"))

    def defer(self, src_ref: Any, dst_ref: Any, rel: str, origin: Optional[tuple[str,int]] = None):
        self._pending.append(_Pending(src_ref, dst_ref, rel, origin))

    def add_edge(self, src: str, dst: str, rel: str):
        self.edges.append(Edge(src, dst, rel))

    # ---- 解析 ----
    def _resolve_ref(self, ref: Any) -> Optional[str]:
        # 字符串：限定名或尾段唯一匹配
        if isinstance(ref, str):
            if ref in self.nodes:
                return ref
            tail = ref.split(".")[-1]
            hits = [k for k in self.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        # 类/对象：用 __qualname__，并允许尾段唯一匹配
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
        # 自动边（由友好 API auto_edge 注册）
        for fn in FINALIZERS:
            fn(self)

        # 解析延迟边 + 规则校验（由友好 API define_relation 注册）
        for p in self._pending:
            src = self._resolve_ref(p.src_ref) or (
                p.src_ref if isinstance(p.src_ref, str) else getattr(p.src_ref, "__qualname__", None)
            )
            dst = self._resolve_ref(p.dst_ref) or (
                p.dst_ref if isinstance(p.dst_ref, str) else getattr(p.dst_ref, "__qualname__", None)
            )
            if src and dst:
                for v in VALIDATORS:
                    v(p.rel, src, dst, self, p.origin)  # ← 传入 origin
                self.add_edge(src, dst, p.rel)

REGISTRY = Registry()

# ---------- 装饰器：定义节点种类 ----------
def _parent_of(qn: str) -> Optional[str]:
    return qn.rsplit(".", 1)[0] if "." in qn else None

def _title(obj, explicit: Optional[str]) -> str:
    return explicit if explicit is not None else obj.__name__.replace("_", " ")

def make_kind(kind: str):
    """创建一个节点装饰器（例如 Topic/Issue/Position 等）。"""
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
        for binder in PROXY_BINDERS:
            binder(c, qn)  # 给类挂载跨层关系的“快捷语法”（如 .___ / .supports）
        return c

    def deco(*dargs, **dkwargs):
        # @Kind 或 @Kind("标题", ...)
        if dargs and callable(dargs[0]):
            c = dargs[0]
            title = dkwargs.pop("title", None)
            return apply(c, title=title, **dkwargs)
        title_pos = dargs[0] if dargs else None
        title_kw  = dkwargs.pop("title", None)
        title = title_kw if title_kw is not None else title_pos
        def wrapper(c):
            return apply(c, title=title, **dkwargs)
        return wrapper
    return deco

# 常用基础类型
Topic    = make_kind("topic")
Note     = make_kind("note")
Question = make_kind("question")

# ---------- 一元加号关系代理（对开发者暴露“___/supports 等变量”，无需理解其原理） ----------
class _RelProxy:
    """
    使用：
      在类体内（src=当前类）        : +___.A.B.C
      在类对象上（src=该类）        : +SomeNode.___.A.B
      也可使用下标                  : +___.["X.Y.Z"]
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
        # 捕获来源（用户代码处）
        frame = inspect.currentframe().f_back
        fi = inspect.getframeinfo(frame)
        origin = (fi.filename, fi.lineno)
        REGISTRY.defer(s, self.path, self.rel, origin=origin)
        return self

# 全局“关联”关系
___ = _RelProxy("relates")

# 默认把 ___ 挂到所有节点类（让类对象也能：+SomeNode.___.X.Y）
def _bind_relates(cls: Any, node_id: str):
    setattr(cls, "___", _RelProxy("relates", src=node_id))
_register_proxy_binder(_bind_relates)

# ---------- 友好扩展 API（给 ibis.py 使用；无需面对 proxy/validator/finalizer） ----------
def define_relation(name: str,
                    *,
                    allow: Optional[Tuple[str, str]] = None) -> _RelProxy:
    """
    定义一个可用的一元加号关系（如 'supports'）。
    - 返回值：全局可用的关系变量（如 supports），可直接在类体内写 +supports.X.Y
    - allow=("src_kind","dst_kind")：可选的类型约束；不传则不做限制。
    """
    proxy = _RelProxy(name)

    # 让所有节点类都挂上同名快捷语法（如 .supports）
    def _bind(cls: Any, node_id: str):
        setattr(cls, name, _RelProxy(name, src=node_id))
    _register_proxy_binder(_bind)

    # 可选：类型约束
    if allow:
        s_kind, d_kind = allow
        def _validator(rel: str, src_id: str, dst_id: str, reg: Registry, origin: Optional[tuple[str,int]]):
            if rel != name:
                return
            sk = reg.nodes[src_id].kind
            dk = reg.nodes[dst_id].kind
            if not (sk == s_kind and dk == d_kind):
                where = ""
                if origin:
                    where = f" at {os.path.basename(origin[0])}:{origin[1]}"
                raise ValueError(
                    f"{name}: 仅允许 {s_kind} → {d_kind}（实际 {sk} → {dk}）: {src_id} -> {dst_id}{where}"
                )
        _register_validator(_validator)

    return proxy

def auto_edge(child_kind: str, parent_kind: str, rel_name: str) -> None:
    """
    根据层级关系自动添加语义边（例如 Position 嵌套在 Issue 下时自动 answers）。
    """
    def _finalizer(reg: Registry):
        for n in list(reg.nodes.values()):
            if not n.parent:
                continue
            p = reg.nodes.get(n.parent)
            if p and (n.kind == child_kind) and (p.kind == parent_kind):
                reg.add_edge(n.id, p.id, rel_name)
    _register_finalizer(_finalizer)

# ---------- 导出 ----------
def summarize():
    REGISTRY.resolve_all()
    byk = {}
    for n in REGISTRY.nodes.values():
        byk[n.kind] = byk.get(n.kind, 0) + 1
    print("Nodes:", len(REGISTRY.nodes), byk)
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
        for cid in children.get(nid, []):
            emit(cid, d+1)
    for r in roots:
        emit(r, 1)
    return "\n".join(lines)

def to_mermaid_flowchart(root=None,
                         include=("contains","answers","supports","opposes","relates"),
                         show_text=True, wrap=28) -> str:
    import re
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

    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent:
            children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    if rid:
        selected = set()
        stack = [rid]
        while stack:
            cur = stack.pop()
            if cur in selected: continue
            selected.add(cur)
            stack.extend(children.get(cur, []))
    else:
        selected = set(REGISTRY.nodes.keys())

    def safe_id(qn: str) -> str:
        return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", qn)
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    def wrap_html(s: str, width: int) -> str:
        if width <= 0: return s
        words = s.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + (1 if cur else 0) > width:
                lines.append(cur); cur = w
            else:
                cur = w if not cur else (cur + " " + w)
        if cur: lines.append(cur)
        return "<br/>".join(lines)

    lines = ["flowchart TD"]
    ordered_nodes = sorted(selected, key=lambda i: REGISTRY.nodes[i].title.lower())
    for nid in ordered_nodes:
        n = REGISTRY.nodes[nid]
        label = n.title
        if show_text and n.text.strip():
            head = n.text.strip().splitlines()[0].strip()
            if head:
                label = label + "<br/>" + wrap_html(head, wrap)
        shape = "round" if n.kind in ("topic", "note") else "rect"
        br_l, br_r = ("(", ")") if shape == "round" else ("[", "]")
        lines.append(f'{safe_id(nid)}{br_l}"{esc(label)}"{br_r}')
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

    def edge_line(e: Edge) -> str:
        a, b = safe_id(e.src), safe_id(e.dst)
        if e.rel == "contains": return f"{a} --> {b}"
        if e.rel == "relates":  return f"{a} -. relates .-> {b}"
        return f'{a} -- "{e.rel}" --> {b}'

    selected_edges = [
        e for e in REGISTRY.edges
        if e.rel in include and e.src in selected and e.dst in selected
    ]
    selected_edges.sort(key=lambda e: (0 if e.rel=="contains" else 1, e.rel, e.src, e.dst))
    for e in selected_edges:
        lines.append(edge_line(e))
    return "\n".join(lines)