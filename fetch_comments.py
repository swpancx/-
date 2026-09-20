import requests
import json
from pathlib import Path

# 让用户输入游戏名称。
game_name = input("请输入游戏名称：").strip()

if not game_name:
    raise SystemExit("游戏名称不能为空，请重新运行。")

# 向 Steam 商店搜索游戏。
search_response = requests.get(
    "https://store.steampowered.com/api/storesearch/",
    params={
        "term": game_name,
        "l": "schinese",
        "cc": "CN"
    },
    timeout=20
)

search_response.raise_for_status()
search_data = search_response.json()

# 保留带有应用编号的搜索结果。
games = []

for item in search_data.get("items", []):
    if item.get("type") == "app":
        games.append(item)

if not games:
    raise SystemExit("没有找到结果，请尝试游戏的商店正式名称或英文名。")

# 为每个候选结果显示一个序号。
print("搜索结果：")

for index, game in enumerate(games, start=1):
    print(f"{index}. {game['name']}（编号：{game['id']}）")

# 用户选择要查询的游戏。
try:
    choice = int(input("请输入要查询的序号："))
except ValueError:
    raise SystemExit("序号需要填写整数，请重新运行。")

if choice < 1 or choice > len(games):
    raise SystemExit("序号超出了搜索结果范围，请重新运行。")

# 列表从 0 开始计数，因此要减 1。
selected_game = games[choice - 1]

app_id = str(selected_game["id"])
game_name = selected_game["name"]

print(f"正在获取《{game_name}》的评测……")

# 获取这个游戏的评测数据。
url = f"https://store.steampowered.com/appreviews/{app_id}"

# 告诉 Steam，我们想获取什么样的数据。
params = {
    "json": 1,
    "language": "schinese",    # 简体中文评测
    "filter": "recent",        # 按发布时间，从新到旧
    "review_type": "all",      # 推荐、不推荐都包含
    "purchase_type": "all",    # 不限制购买来源
    "num_per_page": 100,       # 最多获取 100 条
    "cursor": "*",             # 从第一批开始
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

comments.append({
    "text": review["review"],
    "recommended": review["voted_up"],
    "created_at": review["timestamp_created"]
})
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