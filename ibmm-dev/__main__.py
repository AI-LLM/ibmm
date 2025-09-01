# ibmm-dev/__main__.pys
from __future__ import annotations
import sys, os, time, webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from urllib.parse import urlparse, quote_plus
import urllib.parse
import subprocess
from pathlib import Path
import importlib
from string import Template

HOST = os.environ.get("IBMM_DEV_HOST", "127.0.0.1")
PORT = int(os.environ.get("IBMM_DEV_PORT", "8765"))
PROJECT_ROOT = os.getcwd()

# ----------------- 工具 -----------------
def common_docroot(paths):
    """返回多个路径的公共上层目录 Path。"""
    paths = [str(Path(p).resolve()) for p in paths]
    return Path(os.path.commonpath(paths))

def list_py_files(root: Path) -> list[Path]:
    """递归列出 root 下的所有 .py（排除 __pycache__、隐藏目录）。"""
    items = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        items.append(p)
    return sorted(items)

def compute_sig_for_dirs(dirs: list[Path], extra_files: list[Path] | None = None) -> int:
    """聚合多个目录/文件的 mtime_ns 作为变化签名。"""
    sig = 0
    for d in dirs:
        if d.is_file():
            try: sig ^= d.stat().st_mtime_ns
            except FileNotFoundError: pass
            continue
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try: sig ^= p.stat().st_mtime_ns
            except FileNotFoundError: pass
    if extra_files:
        for f in extra_files:
            try: sig ^= f.stat().st_mtime_ns
            except FileNotFoundError: pass
    return sig

def to_module(docroot: Path, file_path: Path) -> str | None:
    """
    将文件路径转为可用于 import 的模块名（基于 docroot）。
    若 file 不在 docroot 下，则返回 None。
    """
    try:
        rel = file_path.resolve().relative_to(docroot.resolve())
    except ValueError:
        return None
    mod = str(rel).replace(os.sep, ".")
    if mod.endswith(".py"): mod = mod[:-3]
    return mod

# ----------------- Handler -----------------
LIST_HTML = Template("""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ibmm-dev · graphs</title>
<style>
  body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;}
  header{padding:10px 14px;background:#0f172a;color:#e2e8f0;display:flex;gap:12px;align-items:center;}
  header b{color:#fff;}
  main{padding:16px;}
  ul{list-style:none;margin:0;padding:0;}
  li{padding:8px 10px;border-bottom:1px solid #e5e7eb;display:flex;gap:10px;align-items:center;}
  code{background:#f3f4f6;padding:2px 6px;border-radius:6px;}
  a{color:#2563eb;text-decoration:none;}
  a:hover{text-decoration:underline;}
  .small{color:#64748b;font-size:12px;}
</style>
</head>
<body>
<header>
  <b>ibmm-dev</b>
  <span>&nbsp;· listing <code>$list_root</code></span>
  <span style="flex:1"></span>
  <a href="/" style="color:#e2e8f0">open index.html</a>
</header>
<main>
  <p class="small">点击任意条目将打开 <code>/index.html?graph=&lt;module&gt;</code> 进行渲染。</p>
  <ul>
    $items
  </ul>
</main>
<script>
  // 热刷新（可选）：若服务器支持 /events，自动刷新
  try {
    const es = new EventSource("/events");
    es.onmessage = () => location.reload();
  } catch (e) {}
</script>
</body>
</html>
""")

class DevHandler(SimpleHTTPRequestHandler):
    """静态文件 + /events(SSE) + /list(动态生成)"""
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ---- 1) SSE ----
        if path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last = compute_sig_for_dirs(
                [self.server.watch_root, self.server.ibmm_pkg_dir],
                [self.server.index_html] if self.server.index_html else None
            )
            idle = 0
            try:
                while True:
                    time.sleep(0.5)
                    cur = compute_sig_for_dirs(
                        [self.server.watch_root, self.server.ibmm_pkg_dir],
                        [self.server.index_html] if self.server.index_html else None
                    )
                    if cur != last:
                        self.wfile.write(b"data: reload\n\n")
                        self.wfile.flush()
                        last = cur
                        idle = 0
                        continue
                    idle += 1
                    if idle >= 30:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        idle = 0
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        # ---- 2) /list ----
        if path == "/list":
            root = self.server.watch_root
            docroot = Path(self.directory)
            items_html = []
            for py in list_py_files(root):
                if py.name == "__init__.py":
                    continue
                mod = to_module(docroot, py)
                if not mod:
                    # 不在 docroot 下，跳过（正常不会发生）
                    continue
                href = f"/?graph={quote_plus(mod)}"
                rel_show = str(py.relative_to(root))
                items_html.append(
                    f'<li><a href="{href}">{mod}</a>'
                    f'<span class="small">&nbsp;&nbsp;(<code>{rel_show}</code>)</span></li>'
                )
            html = LIST_HTML.substitute(
                list_root=str(root),
                items="\n    ".join(items_html) or "<li><i>no .py files found</i></li>",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        # 截获 /edit/... ，其他路径走原逻辑
        if self.path.startswith("/edit/"):
            self._handle_edit()
            return
        # ---- 3) 其他：静态 ----
        return super().do_GET()

    def _handle_edit(self):
        # /edit/{src_path}:{line_num}
        parsed = urllib.parse.urlsplit(self.path)
        raw = urllib.parse.unquote(parsed.path[len("/edit/"):])

        # 只按“最后一个冒号”分割，避免路径中出现冒号（例如未来扩展）
        if ":" not in raw:
            self._send_text(400, f"Bad edit target: {raw}")
            return
        src_str, line_str = raw.rsplit(":", 1)

        try:
            line_no = int(line_str)
        except ValueError:
            self._send_text(400, f"Invalid line number: {line_str}")
            return

        # 允许绝对路径；相对路径相对于项目根
        if os.path.isabs(src_str):
            fs_path = src_str
        else:
            fs_path = os.path.abspath(os.path.join(PROJECT_ROOT, src_str))

        # 简单防护：必须在项目目录内
        try:
            common = os.path.commonpath([PROJECT_ROOT, os.path.abspath(fs_path)])
        except ValueError:
            common = ""  # 不同盘符等情况
        if common != PROJECT_ROOT:
            self._send_text(403, f"Forbidden path: {fs_path}")
            return

        if not os.path.exists(fs_path):
            self._send_text(404, f"File not found: {fs_path}")
            return

        # 执行 'subl path:line'
        cmd = ["subl", f"{fs_path}:{line_no}"]
        try:
            subprocess.Popen(cmd)  # 非阻塞
        except FileNotFoundError:
            # subl 不存在时给出清晰提示
            self._send_text(500, "subl not found. Install Sublime CLI or add to PATH.")
            return
        except Exception as e:
            self._send_text(500, f"Failed to launch subl: {e}")
            return

        # 成功：可以 204，无内容
        self.send_response(204)
        self.end_headers()

    def _send_text(self, code: int, msg: str):
        data = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

class DevHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, server_address, RequestHandlerClass,
                 docroot: Path, watch_root: Path, ibmm_pkg_dir: Path, index_html: Path | None):
        super().__init__(server_address, RequestHandlerClass)
        self.docroot = docroot
        self.watch_root = watch_root
        self.ibmm_pkg_dir = ibmm_pkg_dir
        self.index_html = index_html

# ----------------- 启动逻辑 -----------------
def run(entry: str | None):
    """
    entry:
      - None           : 遍历 ./graphs
      - 指向目录的路径 : 遍历该目录
      - 指向文件的路径 : 支持，但 /list 仍列出所在目录
    """
    # 1) 能 import ibmm，拿到包目录（用于监听变更）
    try:
        ibmm = importlib.import_module("ibmm")
    except Exception:
        print("[ibmm-dev] Cannot import 'ibmm'. Ensure it is importable (PYTHONPATH).")
        raise
    ibmm_pkg_dir = Path(ibmm.__file__).resolve().parent

    # 2) 解析参数
    watch_root: Path
    graph_file: Path | None = None
    if not entry:
        # 无参：默认遍历 ./graphs
        watch_root = Path("graphs").resolve()
    else:
        p = Path(entry).resolve()
        if p.is_dir():
            watch_root = p
        elif p.is_file():
            graph_file = p
            watch_root = p.parent
        else:
            print(f"[ibmm-dev] path not found: {p}")
            sys.exit(1)

    # 3) 选静态根目录（docroot）：需要覆盖 index.html、ibmm 包目录、watch_root
    #    若 index.html 位于 watch_root，则优先用它所在目录作为 docroot；
    #    否则取三者的公共上层目录
    idx_candidate = watch_root / "index.html"
    if idx_candidate.exists():
        docroot = watch_root
        index_html = idx_candidate
    else:
        docroot = common_docroot([watch_root, ibmm_pkg_dir.parent])
        idx = docroot / "index.html"
        index_html = idx if idx.exists() else None

    # 4) 启动服务器（纯静态 + /events + /list）
    handler_cls = partial(DevHandler, directory=str(docroot))
    httpd = DevHTTPServer((HOST, PORT), handler_cls,
                          docroot=docroot,
                          watch_root=watch_root,
                          ibmm_pkg_dir=ibmm_pkg_dir,
                          index_html=index_html)

    url_root = f"http://{HOST}:{PORT}"
    url_list = f"{url_root}/list"

    print(f"[ibmm-dev] docroot : {docroot}")
    print(f"[ibmm-dev] watching: {watch_root}  (and {ibmm_pkg_dir})")
    if index_html:
        print(f"[ibmm-dev] index  : {index_html}")
    else:
        print("[ibmm-dev] WARN: index.html not found under docroot; "
              "links to '/?graph=...' may 404. Put your index.html under docroot.")

    # 如果是文件参数，也打印直接渲染该文件的 URL（方便调试）
    if graph_file:
        mod = to_module(docroot, graph_file)
        if mod:
            print(f"[ibmm-dev] direct : {url_root}/?graph={mod}")

    print(f"[ibmm-dev] list   : {url_list}")
    print("[ibmm-dev] SSE    : /events  (auto-reload)")

    # 打开浏览器到 /list
    try:
        webbrowser.open_new_tab(url_list)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ibmm-dev] bye.")

if __name__ == "__main__":
    entry = sys.argv[1] if len(sys.argv) >= 2 else None
    run(entry)
