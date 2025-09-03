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
    label: Optional[str] = None   # ← 新增：仅对 relates 有意义

@dataclass
class _Pending:
    src_ref: Any
    dst_ref: Any
    rel: str
    origin: Optional[tuple[str, int]]  # (filename, lineno)
    label: Optional[str] = None

class Registry:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._edge_set: set[tuple[str, str, str, Optional[str]]] = set()   # ← 新增：去重用
        self._pending: List[_Pending] = []

    # 节点/边
    def add_node(self, n: Node):
        self.nodes[n.id] = n
        if n.parent:
            self.add_edge(n.parent, n.id, "contains", None)  # ← 用 add_edge，而不是直接 append

    def defer(self, src_ref: Any, dst_ref: Any, rel: str, origin: Optional[tuple[str,int]] = None, label: Optional[str] = None):
        self._pending.append(_Pending(src_ref, dst_ref, rel, origin, label))

    def add_edge(self, src: str, dst: str, rel: str, label: Optional[str] = None):
        key = (src, dst, rel, label)
        if key in self._edge_set:
            return
        self._edge_set.add(key)
        self.edges.append(Edge(src, dst, rel, label))

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

        # 把当前待处理边拿出来处理，然后清空队列，避免重复追加
        pendings, self._pending = self._pending, []
        # 解析延迟边 + 规则校验
        for p in pendings:
            src = self._resolve_ref(p.src_ref) or (
                p.src_ref if isinstance(p.src_ref, str) else getattr(p.src_ref, "__qualname__", None)
            )
            dst = self._resolve_ref(p.dst_ref) or (
                p.dst_ref if isinstance(p.dst_ref, str) else getattr(p.dst_ref, "__qualname__", None)
            )
            if src and dst:
                for v in VALIDATORS:
                    v(p.rel, src, dst, self, p.origin)
                self.add_edge(src, dst, p.rel, p.label)

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

        # === 抓取 class 定义的文件与行号 ===
        src_file = inspect.getsourcefile(c) or inspect.getfile(c)
        try:
            _, src_line = inspect.getsourcelines(c)   # class 头行号
        except (OSError, TypeError):
            src_line = None

        meta_out = dict(meta or {})
        if src_file:
            meta_out["src_file"] = src_file
        if src_line:
            meta_out["src_line"] = src_line
        # ========================================

        REGISTRY.add_node(Node(
            id=qn, kind=kind, title=_title(c, title),
            text=(inspect.getdoc(c) or ""), parent=_parent_of(qn), meta=meta_out
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
    __slots__ = ("rel", "path", "src", "label")
    def __init__(self, rel: str, path: str = "", src: Optional[str] = None, label: Optional[str] = None):
        object.__setattr__(self, "rel", rel)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "src", src)
        object.__setattr__(self, "label", label)   # ← 保存标签

    def __getattr__(self, name: str) -> "_RelProxy":
        sep = "" if not self.path else "."
        return self.__class__(self.rel, f"{self.path}{sep}{name}", self.src, self.label)
    def __getitem__(self, dotted: str) -> "_RelProxy":
        return self.__class__(self.rel, dotted, self.src)

    # 把 ___(...) 当作“就地设定标签/路径”的便捷入口
    def __call__(self, *args, **kwargs) -> "_RelProxy":
        """
        用法约定（为了支持 +___("标签").A.B）：
            - ___("标签")                 -> 仅设置标签（推荐）
            - ___("路径","标签")          -> 同时设置路径与标签
            - ___(path="A.B", label="依赖") -> 关键字形式
            - ___("路径")                 -> （不推荐）若只传一串且你真想当路径，请用 ___["路径"] 更明确
        """
        path  = kwargs.get("path")
        label = kwargs.get("label")

        if len(args) == 1 and isinstance(args[0], str):
            # 约定：单个位置参数默认为“标签”（满足 ___("标签").A.B 的写法）
            if path is None and label is None:
                label = args[0]
            elif path is None:
                path = args[0]
        elif len(args) >= 2:
            path  = args[0]
            label = args[1]

        return self.__class__(
            self.rel,
            path if path is not None else self.path,
            self.src,
            label if label is not None else self.label,
        )
    def __pos__(self):
        if not self.path:
            raise ValueError(f"Empty target path for relation '{self.rel}'.")
        s = self.src or REGISTRY._infer_src_from_class_body()
        # 捕获调用处文件/行号
        frame = inspect.currentframe().f_back
        fi = inspect.getframeinfo(frame)
        origin = (fi.filename, fi.lineno)
        REGISTRY.defer(s, self.path, self.rel, origin=origin, label=self.label)
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

ALL_NODE_CLASSES_SET = set()
def _collect_node_class(cls: Any, node_id: str):
    ALL_NODE_CLASSES_SET.add(cls)
_register_proxy_binder(_collect_node_class)

def to_node_classes() -> List[Any]:
    """返回所有被装饰器（如 @Topic）标记的节点类对象列表，列表已排序确保幂等性。"""
    return sorted(list(ALL_NODE_CLASSES_SET), key=lambda c: c.__qualname__)

def summarize():
    REGISTRY.resolve_all()
    kinds = {}
    for n in REGISTRY.nodes.values():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    print("Nodes:", len(REGISTRY.nodes), kinds)
    print("Edges:", len(REGISTRY.edges))

# ---- Markdown -> HTML (极简) ----
import re as _re
def _escape_basic(s: str) -> str:
    # 仅做基础 HTML 转义，后续会插入我们生成的 <a>/<img> 等标签
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )

def _md_to_html_line(raw: str) -> str:
    """
    把单行 Markdown 转成适合 Mermaid label 的 HTML 片段：
    - 链接   [text](url)  -> <a href='url' target='_blank' rel='noopener noreferrer'>text</a>
    - 图片   ![alt](url)  -> <img src='url' alt='alt'/>
    - 粗体   **text**     -> <b>text</b>
    - 斜体   *text*       -> <i>text</i>
    - 代码   `code`       -> <code>code</code>
    - 自动链接 http(s)://... -> <a href='url' ...>url</a>
    注意：先整体转义，再做替换，保证安全；标签属性用单引号，避免 Mermaid 语法冲突。
    """
    s = _escape_basic(raw or "")

    # 图片：先替换，避免被链接规则吞掉
    def _img_sub(m):
        alt = m.group(1)
        url = m.group(2)
        return f"<img src='{url}' alt='{alt}'/>"
    s = _re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _img_sub, s)

    # 链接
    def _link_sub(m):
        text = m.group(1)
        url  = m.group(2)
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{text}</a>"
    s = _re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link_sub, s)

    # 行内代码
    s = _re.sub(r'`([^`]+)`', r'<code>\1</code>', s)

    # 粗体（先于斜体）
    s = _re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)

    # 斜体（简单处理，尽量避免与粗体冲突）
    s = _re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', s)

    # 自动链接（避免命中已经生成的标签内的 url）
    def _auto_link(m):
        url = m.group(0)
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{url}</a>"
    s = _re.sub(r'(?<!["\'=])(https?://[^\s<]+)', _auto_link, s)

    return s

def _md_to_text_line(raw: str) -> str:
    """
    把单行 Markdown 转为 mindmap 友好的纯文本：
    - ![alt](url)   ->  🖼 alt (url)
    - [text](url)   ->  text (url)
    - **bold**      ->  bold
    - *italic*      ->  italic
    - `code`        ->  ‹code›
    - 自动链接      ->  url
    """
    s = raw or ""

    # 图片：先处理，避免被链接规则吞掉
    def _img(m):
        alt, url = m.group(1), m.group(2)
        return f"🖼 {alt} ({url})" if alt else f"🖼 ({url})"
    s = _re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _img, s)

    # 链接
    def _lnk(m):
        text, url = m.group(1), m.group(2)
        text = text.strip() or url
        return f"{text} ({url})"
    s = _re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _lnk, s)

    # 行内代码 -> ‹code›
    s = _re.sub(r'`([^`]+)`', r'‹\1›', s)

    # 粗体/斜体：去掉标记
    s = _re.sub(r'\*\*([^*]+)\*\*', r'\1', s)                       # **bold**
    s = _re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', s)              # *italic*

    # 自动链接（保持原样）
    # （这里不包 <a>，mindmap 不吃 HTML）
    return s.strip()

def to_mermaid_mindmap(
    root=None,
    show_text=False,            # 当 text_mode='firstline' 时才生效
    text_max_len=8000,
    *,
    text_mode: str = "inline",   # 'firstline' | 'inline' | 'children'
    text_lines: int | None = None,  # 限制使用的 docstring 行数；None=全部
    inline_sep: str = "<br>",        # text_mode='inline' 时的分隔符
    md: str = "html",             # 'text'或 'html'（默认）
) -> str:
    """
    导出 Mermaid mindmap，支持多行 docstring。

    若 root 为 None：自动选择“后代节点最多”的顶层根（只输出这一个根）。
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

    # 选根：root 指定则用之；否则选“后代最多”的顶层根
    rid = _resolve_id(root) if root else None
    if rid is None:
        top_roots = [nid for nid, n in REGISTRY.nodes.items() if not n.parent]
        if not top_roots:
            return "mindmap"
        def subtree_size(nid: str) -> int:
            cnt = 0
            stack = list(children.get(nid, []))
            while stack:
                x = stack.pop()
                cnt += 1
                stack.extend(children.get(x, []))
            return cnt
        rid = max(
            top_roots,
            key=lambda nid: (subtree_size(nid), REGISTRY.nodes[nid].title.lower())
        )

    # 文本处理
    def _doc_lines(txt: str) -> list[str]:
        arr = [ln.strip() for ln in (txt or "").splitlines()]
        arr = [ln for ln in arr if ln]
        if text_lines is not None:
            arr = arr[:text_lines]
        return arr

    def _render_line(ln: str) -> str:
        if md == "html":
            # 注意：mindmap 对 HTML 支持有限；不同渲染器表现可能不同
            return _md_to_html_line(ln)
        return _md_to_text_line(ln)

    def _firstline_snippet(txt: str) -> str:
        if not show_text: return ""
        arr = _doc_lines(txt)
        if not arr: return ""
        first = _render_line(arr[0])
        if len(first) > text_max_len:
            first = first[:text_max_len - 1] + "…"
        return f": {first}"

    # 输出
    lines_out = ["mindmap"]
    IND = "  "

    def emit(nid: str, depth: int):
        n = REGISTRY.nodes[nid]
        if text_mode == "firstline":
            label = f"{n.title}{_firstline_snippet(n.text)}"
            lines_out.append(f"{IND*depth}{label}")
        elif text_mode == "inline":
            doc = inline_sep.join(_render_line(ln) for ln in _doc_lines(n.text))
            label = n.title if not doc else f"{n.title}: {doc}"
            lines_out.append(f"{IND*depth}{label}")
        elif text_mode == "children":
            lines_out.append(f"{IND*depth}{n.title}")
            for l in _doc_lines(n.text):
                lines_out.append(f"{IND*(depth+1)}{_render_line(l)}")
        else:
            label = f"{n.title}{_firstline_snippet(n.text)}"
            lines_out.append(f"{IND*depth}{label}")

        for cid in children.get(nid, []):
            emit(cid, depth + 1)

    emit(rid, 1)
    return "\n".join(lines_out)

def to_mermaid_flowchart(
    root=None,
    include=("contains", "answers", "supports", "opposes", "relates"),
    show_text=True,
    node_styles: dict | None = None,
    edge_styles: dict | None = None,
    *,
    text_lines: int | None = None,    # 取 docstring 的前 N 行；None=全部
    subgraphs: list[Any] | None = None,
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
    subgraphs : 要渲染为 subgraph 的根节点列表，可以是类对象或 qualname 字符串。
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
    def esc_label_quotes(s: str) -> str: return s.replace("\\", "\\\\").replace('"', '\\"')

    def _doc_lines(txt: str) -> list[str]:
        arr = [ln.strip() for ln in (txt or "").splitlines()]
        arr = [ln for ln in arr if ln]  # 去空行
        if text_lines == 0: return []
        if text_lines is not None and text_lines > 0:
            arr = arr[:text_lines]
        return arr

    def doc_md_html(txt: str) -> str:
        if not show_text:
            return ""
        lines = _doc_lines(txt)
        if not lines:
            return ""
        # 对每一行做 Markdown -> HTML 转换；不再做人工 wrap，避免破坏标签
        return "<br/>".join(_md_to_html_line(ln) for ln in lines)

    # --- 输出 ---
    lines = ["flowchart TD"]
    ordered_nodes = sorted(list(selected), key=lambda i: REGISTRY.nodes[i].title.lower())

    def render_node_definition(nid: str) -> str:
        n = REGISTRY.nodes[nid]
        label = n.title

        # === 追加"编辑链接" ===
        sf = n.meta.get("src_file")
        sl = n.meta.get("src_line")
        if sf and sl:
            #base = os.path.basename(sf)
            # 单引号属性，避免 Mermaid 语法冲突；可带 target/_blank
            if sf.startswith("/home/pyodide/"):
                sf = sf[len("/home/pyodide/"):]
            label = f"<a href='edit/{sf}:{sl}' target='_blank' rel='noopener noreferrer'>{label}</a>"
        # ==========================

        more = doc_md_html(n.text)
        if more:
            label = label + "<br/>" + more

        rounded = n.kind in ("topic", "title", "node", "note")
        br_l, br_r = ("(", ")") if rounded else ("[", "]")
        return f'{safe_id(nid)}{br_l}"{esc_label_quotes(label)}"{br_r}'

    if subgraphs:
        subgraph_root_ids = [_resolve_id(r) for r in subgraphs]
        subgraph_root_ids = [r for r in subgraph_root_ids if r and r in REGISTRY.nodes]

        # 建立subgraph根节点之间的祖先-后代关系
        def is_descendant(node_id: str, ancestor_id: str) -> bool:
            """检查node_id是否是ancestor_id的后代"""
            curr = node_id
            while curr:
                if curr == ancestor_id:
                    return True
                curr = REGISTRY.nodes[curr].parent
            return False

        # 构建subgraph的嵌套层次结构
        class SubgraphTree:
            def __init__(self, root_id: str):
                self.root_id = root_id
                self.children = []  # 存储子subgraph
                self.nodes = []     # 存储属于这个subgraph但不属于任何子subgraph的节点

        # 创建所有subgraph树节点
        subgraph_trees = {root_id: SubgraphTree(root_id) for root_id in subgraph_root_ids}

        # 建立subgraph之间的父子关系
        for root_id in subgraph_root_ids:
            for other_id in subgraph_root_ids:
                if root_id != other_id and is_descendant(other_id, root_id):
                    # other_id是root_id的后代，所以other对应的subgraph应该是root对应subgraph的子级
                    # 但我们只建立直接父子关系，不建立祖孙关系
                    is_direct_child = True
                    for third_id in subgraph_root_ids:
                        if (third_id != root_id and third_id != other_id and
                            is_descendant(other_id, third_id) and is_descendant(third_id, root_id)):
                            # 存在中间层级，other_id不是root_id的直接子级
                            is_direct_child = False
                            break
                    if is_direct_child:
                        subgraph_trees[root_id].children.append(subgraph_trees[other_id])

        # 找到顶层subgraph（没有父级subgraph的）
        top_level_subgraphs = []
        for tree in subgraph_trees.values():
            is_top_level = True
            for other_tree in subgraph_trees.values():
                if tree in other_tree.children:
                    is_top_level = False
                    break
            if is_top_level:
                top_level_subgraphs.append(tree)

        # 为每个节点分配到对应的subgraph
        standalone_nodes = []

        for nid in ordered_nodes:
            found_subgraph = None
            # 找到这个节点应该属于的最深层subgraph
            for root_id in subgraph_root_ids:
                if is_descendant(nid, root_id):
                    if found_subgraph is None or is_descendant(root_id, found_subgraph):
                        found_subgraph = root_id

            if found_subgraph:
                subgraph_trees[found_subgraph].nodes.append(nid)
            else:
                standalone_nodes.append(nid)

        # 渲染函数
        def render_subgraph_tree(tree: SubgraphTree, indent: str = ""):
            subgraph_title = REGISTRY.nodes[tree.root_id].title
            lines.append(f'{indent}subgraph "{esc_label_quotes(subgraph_title)}"')

            # 先渲染直接属于这个subgraph的节点
            for nid in tree.nodes:
                lines.append(f"{indent}  {render_node_definition(nid)}")

            # 然后渲染子subgraph
            sorted_children = sorted(tree.children, key=lambda t: REGISTRY.nodes[t.root_id].title.lower())
            for child_tree in sorted_children:
                render_subgraph_tree(child_tree, indent + "  ")

            lines.append(f"{indent}end")

        # 渲染独立节点
        for nid in standalone_nodes:
            lines.append(render_node_definition(nid))

        # 渲染顶层subgraph
        sorted_top_level = sorted(top_level_subgraphs, key=lambda t: REGISTRY.nodes[t.root_id].title.lower())
        for tree in sorted_top_level:
            render_subgraph_tree(tree)
    else:
        for nid in ordered_nodes:
            lines.append(render_node_definition(nid))

    # classDef（只输出实际出现的 kind）
    present_kinds = {REGISTRY.nodes[nid].kind for nid in ordered_nodes}
    for kind in present_kinds:
        style = default_node_styles.get(kind)
        if style:
            lines.append(f"classDef {kind} {style}")
    for nid in ordered_nodes:
        lines.append(f"class {safe_id(nid)} {REGISTRY.nodes[nid].kind};")

    # 找出所有有 semantic 关系的节点
    semantic_nodes = set()  # 存储所有有 semantic 关系（作为源节点）的节点
    for e in REGISTRY.edges:
        if e.rel in ("answers", "supports", "opposes") and e.src in selected and e.dst in selected:
            semantic_nodes.add(e.src)

    # 找出有 semantic 关系的节点的所有子孙节点
    def get_all_descendants(node_id: str) -> set:
        """获取节点的所有子孙节点"""
        descendants = set()
        queue = [node_id]
        while queue:
            curr = queue.pop(0)
            for child_id in children.get(curr, []):
                if child_id not in descendants:
                    descendants.add(child_id)
                    queue.append(child_id)
        return descendants

    semantic_descendants = set()
    for semantic_node in semantic_nodes:
        semantic_descendants.update(get_all_descendants(semantic_node))

    # 边
    def edge_line(e):
        a, b = safe_id(e.src), safe_id(e.dst)
        if e.rel == "contains":
            # 如果源节点是有semantic关系的节点或其子孙，反转方向
            if e.src in semantic_nodes or e.src in semantic_descendants:
                return f"{b} --- {a}"  # 反转方向
            else:
                return f"{a} --- {b}"  # 正常方向
        if e.rel == "relates":
            # 若有自定义标签则用标签，否则不显示标签（仅显示点划线）
            if hasattr(e, "label") and e.label and e.label.strip():
                # 带标签的点划线: -. label .->
                return f"{a} -. {esc_label_quotes(e.label.strip())} .-> {b}"
            else:
                # 无标签的点划线: -..->
                return f"{a} -..-> {b}"
        return f'{a} -- "{e.rel}" --> {b}'

    # 预处理：找出所有节点之间的关系，检查是否存在semantic关系
    semantic_relations = set()  # 存储所有已有semantic关系的节点对(src, dst)或(dst, src)
    for e in REGISTRY.edges:
        if e.rel in ("answers", "supports", "opposes") and e.src in selected and e.dst in selected:
            semantic_relations.add((e.src, e.dst))
            semantic_relations.add((e.dst, e.src))  # 反向也加入，确保contains关系被筛选

    # 过滤边：如果节点间已有semantic关系，则不显示contains关系
    filtered_edges = []
    for e in REGISTRY.edges:
        if e.rel == "contains" and (e.src, e.dst) in semantic_relations:
            continue  # 跳过已有semantic关系的contains边
        if e.rel in include and e.src in selected and e.dst in selected:
            filtered_edges.append(e)

    selected_edges = filtered_edges
    selected_edges.sort(key=lambda e: (0 if e.rel == "contains" else 1, e.rel, e.src, e.dst))

    linkstyle_lines = []
    edge_idx = 0
    if edge_styles:
        for e in selected_edges:
            lines.append(edge_line(e))
            style = edge_styles.get(e.rel)
            if style:
                linkstyle_lines.append(f"linkStyle {edge_idx} {style}")
            edge_idx += 1
    else:
        for e in selected_edges:
            lines.append(edge_line(e))

    lines.extend(linkstyle_lines)
    return "\n".join(lines)
