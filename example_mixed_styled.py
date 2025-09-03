from ibmm import to_mermaid_flowchart, to_mermaid_mindmap
import graphs.example_mixed  # 只要 import 就会注册节点/边
from graphs.example_mixed import OS_Question

node_styles = {
    "issue":    "fill:#fff2cc,stroke:#cc7a00,stroke-width:1.5px;",
    "position": "fill:#eafff5,stroke:#148f55,stroke-width:1.5px;",
    "pro":      "fill:#f0fff4,stroke:#22c55e,stroke-width:1px;",
    "con":      "fill:#fff1f2,stroke:#ef4444,stroke-width:1px;",
}

edge_styles = {
    "supports": "color:green,stroke:green,stroke-width:2px;",
    "opposes":  "color:red,stroke:red,stroke-width:2px;",
    "answers":  "color:blue,stroke:blue,stroke-width:2px;",
    "relates":  "color:gray,stroke:gray,stroke-width:2px,stroke-dasharray: 2 2;",
    # "contains": "stroke:#999,stroke-width:1px;"  # 如需也可加
}

print("="*20)
s1 = to_mermaid_flowchart(
    None,#"OS_Question",
    include=("contains","answers","supports","opposes","relates"),
    show_text=True,
    node_styles=node_styles,
    edge_styles=edge_styles,
    subgraphs=[OS_Question.Yes, OS_Question.No] #must import OS_Question
)
print(s1)
s2 = to_mermaid_flowchart(
    None,#"OS_Question",
    include=("contains","answers","supports","opposes","relates"),
    show_text=True,
    node_styles=node_styles,
    edge_styles=edge_styles,
    subgraphs=["OS_Question.Yes", "OS_Question.No"]
)
assert s1 == s2, "重复导出内容应完全一致"
print("="*20)
print(to_mermaid_mindmap(
    None
))
