from ibmm import to_mermaid_flowchart, to_mermaid_mindmap
import graphs.example_mixed  # 只要 import 就会注册节点/边

node_styles = {
    "issue":    "fill:#fff2cc,stroke:#cc7a00,stroke-width:1.5px;",
    "position": "fill:#eafff5,stroke:#148f55,stroke-width:1.5px;",
    "pro":      "fill:#f0fff4,stroke:#22c55e,stroke-width:1px;",
    "con":      "fill:#fff1f2,stroke:#ef4444,stroke-width:1px;",
}

edge_styles = {
    "supports": "stroke:green,stroke-width:2px;",
    "opposes":  "stroke:red,stroke-width:2px;",
    "answers":  "stroke:blue,stroke-width:1.5px,stroke-dasharray: 4 2;",
    "relates":  "stroke:#6b7280,stroke-dasharray: 2 2;",
    # "contains": "stroke:#999,stroke-width:1px;"  # 如需也可加
}

print(to_mermaid_flowchart(
    None,#"OS_Question",
    include=("contains","answers","supports","opposes","relates"),
    show_text=True,
    wrap=28,
    node_styles=node_styles,
    edge_styles=edge_styles,
))

print(to_mermaid_mindmap(
    None
))