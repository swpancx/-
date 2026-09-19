import requests
import json
from pathlib import Path
# 示例游戏：星露谷物语，它在 Steam 上的游戏编号是 413150。
app_id = "413150"

# 获取这个游戏的评测数据。
url = f"https://store.steampowered.com/appreviews/{app_id}"

# 告诉 Steam，我们想获取什么样的数据。
params = {
    "json": 1,                 # 返回 JSON 格式的数据
    "language": "schinese",    # 简体中文评测
    "filter": "recent",        # 按发布时间从新到旧排序
    "review_type": "all",      # 推荐和不推荐都要
    "purchase_type": "all",    # 包含不同购买来源的评测
    "num_per_page": 200,        # 本次最多获取 200 条
    "cursor": "*",            # 从第一批开始获取
}

# 发送请求，并设置等待超时。
response = requests.get(url, params=params, timeout=20)

# 如果服务器返回 HTTP 错误，就停止并显示错误。
response.raise_for_status()

# 把返回的 JSON 数据转换为 Python 可以操作的数据。
data = response.json()

if data.get("success") != 1:
    raise RuntimeError("Steam 没有成功返回评测数据。")

# 从返回的数据中取出评测列表。
reviews = data["reviews"]

print(f"本次获取到 {len(reviews)} 条评测。")

for review in reviews:
    print()
    print("评论内容：", review["review"])

    if review["voted_up"]:
        print("玩家选择：推荐")
    else:
        print("玩家选择：不推荐")

# 整理出这次练习需要的数据。
comments = []

for review in reviews:
    comments.append({
        "text": review["review"],
        "recommended": review["voted_up"]
    })

# 文件保存在当前 Python 脚本所在的文件夹。
file_path = Path(__file__).with_name("comments.json")

# 将数据写入 JSON 文件。
with file_path.open("w", encoding="utf-8") as file:
    json.dump(comments, file, ensure_ascii=False, indent=2)

print(f"已保存 {len(comments)} 条评论到：{file_path}")