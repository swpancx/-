import json
from pathlib import Path

# 找到与 main.py 放在同一个文件夹里的数据文件。
file_path = Path(__file__).with_name("comments.json")

if not file_path.exists():
    raise SystemExit("没有找到评论文件，请先运行 fetch_comments.py。")

# 从 JSON 文件中读取评论。
with file_path.open("r", encoding="utf-8") as file:
    comments = json.load(file)

# 统计玩家的推荐选项。
counts = {"推荐": 0, "不推荐": 0}

for comment in comments:
    if comment["recommended"]:
        counts["推荐"] += 1
    else:
        counts["不推荐"] += 1

total = len(comments)

if total == 0:
    print("文件中没有评论，暂时无法统计。")
else:
    print(f"本次样本数量：{total} 条")

    for label, count in counts.items():
        percentage = count / total * 100
        print(f"{label}：{count} 条，占比 {percentage:.1f}%")

    score = counts["推荐"] / total * 100
    print(f"本次样本口碑分：{score:.1f} / 100（按推荐率计算）")