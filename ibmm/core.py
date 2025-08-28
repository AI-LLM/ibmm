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
    # 没给标题就用类名，且将下划线转为空格
    return explicit if explicit is not None else obj.__name__.replace("_", " ")

def make_kind(kind: str):
    """创建一个节点装饰器，既支持 @Kind 也支持 @Kind('标题', ...)。"""
    def apply(c, title: Optional[str] = None, **meta):
        qn = c.__qualname__
        REGISTRY.add_node(Node(
            id=qn, kind=kind, title=_title(c, title),
            text=(inspect.getdoc(c) or ""), parent=_parent_of(qn), meta=meta or {}
        ))
        for binder in PROXY_BINDERS: binder(c, qn)
        return c
    def deco(*dargs, **dkwargs):
        # 情况 A：@Kind 直接装饰类（无参）
        if dargs and callable(dargs[0]):  # @Kind
            c = dargs[0]; title = dkwargs.pop("title", None)
            return apply(c, title=title, **dkwargs)
        # 情况 B：@Kind("标题", ...) 返回真正装饰器    
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

def to_mermaid_mindmap(
    root=None,
    show_text=False,            # 当 text_mode='firstline' 时才生效
    text_max_len=8000,
    *,
    text_mode: str = "inline",   # 'firstline' | 'inline' | 'children'
    text_lines: int | None = None,  # 限制使用的 docstring 行数；None=全部
    inline_sep: str = "<br>",        # text_mode='inline' 时的分隔符
) -> str:
    """
    导出 Mermaid mindmap，支持多行 docstring。

    text_mode:
      - 'firstline'：只显示第一行（旧行为；受 show_text/text_max_len 控制）
      - 'inline'   ：把多行合并为一行，用 inline_sep 连接（不支持 <br/>）
      - 'children' ：把每一行作为“子节点”渲染（推荐在思维导图中表达多行）

    text_lines: 限制 docstring 取前 N 行；None 表示全部非空行。
    """
    REGISTRY.resolve_all()

    def _resolve_id(ref):
        if ref is None: return None
        if isinstance(ref, str):
            if ref in REGISTRY.nodes: return ref
            tail = ref.split(".")[-1]
            hits = [k for k in REGISTRY.nodes if k.endswith(f".{tail}") or k == tail]
            return hits[0] if len(hits) == 1 else None
        return getattr(ref, "__qualname__", None)

    # children 索引
    children = {}
    for n in REGISTRY.nodes.values():
        if n.parent:
            children.setdefault(n.parent, []).append(n.id)
    for k in children:
        children[k].sort(key=lambda i: (REGISTRY.nodes[i].kind, REGISTRY.nodes[i].title.lower()))

    roots = [_resolve_id(root)] if _resolve_id(root) else \
            sorted([nid for nid, n in REGISTRY.nodes.items() if not n.parent],
                   key=lambda i: REGISTRY.nodes[i].title.lower())

    def _doc_lines(txt: str) -> list[str]:
        lines = [ln.strip() for ln in (txt or "").splitlines()]
        lines = [ln for ln in lines if ln]  # 去掉空行
        if text_lines is not None:
            lines = lines[:text_lines]
        return lines

    def _snippet_firstline(txt: str) -> str:
        if not show_text: return ""
        lines = _doc_lines(txt)
        if not lines: return ""
        head = lines[0]
        if len(head) > text_max_len:
            head = head[:text_max_len - 1] + "…"
        return f": {head}"

    lines_out = ["mindmap"]
    IND = "  "

    def emit(nid: str, depth: int):
        n = REGISTRY.nodes[nid]
        if text_mode == "firstline":
            label = f"{n.title}{_snippet_firstline(n.text)}"
            lines_out.append(f"{IND*depth}{label}")
        elif text_mode == "inline":
            doc = inline_sep.join(_doc_lines(n.text))
            label = n.title if not doc else f"{n.title}: {doc}"
            lines_out.append(f"{IND*depth}{label}")
        elif text_mode == "children":
            lines_out.append(f"{IND*depth}{n.title}")
            for l in _doc_lines(n.text):
                lines_out.append(f"{IND*(depth+1)}{l}")
        else:
            # 回退到旧行为
            label = f"{n.title}{_snippet_firstline(n.text)}"
            lines_out.append(f"{IND*depth}{label}")

        for cid in children.get(nid, []):
            emit(cid, depth + 1)

    for r in roots:
        emit(r, 1)
    return "\n".join(lines_out)

def to_mermaid_flowchart(
    root=None,
    include=("contains", "answers", "supports", "opposes", "relates"),
    show_text=True,
    wrap=28,
    node_styles: dict | None = None,
    edge_styles: dict | None = None,
    *,
    text_lines: int | None = None,    # 取 docstring 的前 N 行；None=全部
) -> str:
    """
    导出 Mermaid flowchart（可选自定义节点/边样式）。

    参数
    ----
    node_styles : 映射 {kind: "Mermaid classDef 样式串"}
        例如: {"issue": "fill:#fff2cc,stroke:#cc7a00,stroke-width:1.5px;"}
    edge_styles : 映射 {rel: "Mermaid linkStyle 样式串"}
        例如: {
          "supports": "stroke:#16a34a,stroke-width:2px;",
          "opposes":  "stroke:#dc2626,stroke-width:2px;",
          "answers":  "stroke:#2563eb,stroke-width:1.5px,stroke-dasharray: 4 2;",
          "relates":  "stroke:#6b7280,stroke-dasharray: 2 2;"
        }
        注意：我们已自动按输出顺序为每条边计算 linkStyle 编号，你无需关心 index。
    text_lines : 取 docstring 的前 N 行；None=全部（默认），0=不显示（等价 show_text=False）。
    """
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

    # --- 子树选择 ---
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

    # --- 样式（可被覆盖） ---
    default_node_styles = {
        "topic":    "fill:#eef6ff,stroke:#5b8,stroke-width:1px;",
        "title":    "fill:#f0f7ff,stroke:#69c,stroke-width:1px;",
        "node":     "fill:#ffffff,stroke:#bbb,stroke-width:1px;",
        "note":     "fill:#f7f7f7,stroke:#999,stroke-width:1px;",
        "issue":    "fill:#fff6e5,stroke:#d48,stroke-width:1px;",
        "position": "fill:#f3ffef,stroke:#5a5,stroke-width:1px;",
        "pro":      "fill:#eafff3,stroke:#5a5,stroke-width:1px;",
        "con":      "fill:#ffefef,stroke:#d55,stroke-width:1px;",
        "question": "fill:#fff,stroke:#888,stroke-dasharray: 4 2;",
    }
    if node_styles:
        default_node_styles.update(node_styles)

    # --- 工具 ---
    def safe_id(qn: str) -> str: return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", qn)
    def esc(s: str) -> str: return s.replace("\\", "\\\\").replace('"', '\\"')

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

    def doc_as_html(txt: str) -> str:
        if not show_text:
            return ""
        raw = [ln.strip() for ln in (txt or "").splitlines()]
        raw = [ln for ln in raw if ln]  # 去空行
        if text_lines == 0:
            raw = []
        elif text_lines is not None and text_lines > 0:
            raw = raw[:text_lines]
        if not raw:
            return ""
        # 每一行单独 wrap，然后用 <br/> 连接，保持段落结构
        return "<br/>".join(wrap_html(ln, wrap) for ln in raw)

    # --- 输出 ---
    lines = ["flowchart TD"]
    ordered_nodes = sorted(selected, key=lambda i: REGISTRY.nodes[i].title.lower())

    for nid in ordered_nodes:
        n = REGISTRY.nodes[nid]
        label = n.title
        more = doc_as_html(n.text)
        if more:
            label = label + "<br/>" + more
        rounded = n.kind in ("topic", "title", "node", "note")
        br_l, br_r = ("(", ")") if rounded else ("[", "]")
        lines.append(f'{safe_id(nid)}{br_l}"{esc(label)}"{br_r}')

    # classDef
    present_kinds = {REGISTRY.nodes[nid].kind for nid in ordered_nodes}
    for kind in present_kinds:
        style = default_node_styles.get(kind)
        if style:
            lines.append(f"classDef {kind} {style}")
    for nid in ordered_nodes:
        lines.append(f"class {safe_id(nid)} {REGISTRY.nodes[nid].kind};")

    # 边
    def edge_line(e):
        a, b = safe_id(e.src), safe_id(e.dst)
        if e.rel == "contains": return f"{a} --> {b}"
        if e.rel == "relates":  return f"{a} -. relates .-> {b}"
        return f'{a} -- "{e.rel}" --> {b}'

    selected_edges = [
        e for e in REGISTRY.edges
        if e.rel in include and e.src in selected and e.dst in selected
    ]
    selected_edges.sort(key=lambda e: (0 if e.rel == "contains" else 1, e.rel, e.src, e.dst))

    # linkStyle
    linkstyle_lines = []
    edge_idx = 0
    for e in selected_edges:
        lines.append(edge_line(e))
        if edge_styles and (style := edge_styles.get(e.rel)):
            linkstyle_lines.append(f"linkStyle {edge_idx} {style}")
        edge_idx += 1

    lines.extend(linkstyle_lines)
    return "\n".join(lines)