# 这些都是虚构的练习数据。
# text 是评论内容，sentiment 是手动设置的评价标签。
comments = [
    {"text": "画面很好看", "sentiment": "负面"},
    {"text": "战斗很有意思", "sentiment": "正面"},
    {"text": "剧情让我很投入", "sentiment": "正面"},
    {"text": "音乐非常好听", "sentiment": "正面"},
    {"text": "角色设计很棒", "sentiment": "正面"},
    {"text": "操作手感很好", "sentiment": "正面"},
    {"text": "和朋友一起玩很开心", "sentiment": "正面"},
    {"text": "关卡设计很巧妙", "sentiment": "正面"},
    {"text": "内容很丰富", "sentiment": "正面"},
    {"text": "这个价格很值得", "sentiment": "正面"},
    {"text": "更新之后体验更好了", "sentiment": "正面"},
    {"text": "愿意推荐给朋友", "sentiment": "正面"},
    {"text": "整体一般，谈不上喜欢或讨厌", "sentiment": "中立"},
    {"text": "体验中规中矩", "sentiment": "中立"},
    {"text": "优点和缺点差不多", "sentiment": "中立"},
    {"text": "没有特别满意，也没有特别不满", "sentiment": "中立"},
    {"text": "经常卡顿，体验很差", "sentiment": "负面"},
    {"text": "内容太重复了", "sentiment": "负面"},
    {"text": "经常闪退，很失望", "sentiment": "负面"},
    {"text": "不值得这个价格", "sentiment": "负面"},
]

# 三个计数器，开始时都是 0。
counts = {"正面": 0, "中立": 0, "负面": 0}

# 逐条读取评论，让对应的计数器加 1。
for comment in comments:
    label = comment["sentiment"]
    counts[label] += 1

total = len(comments)

if total == 0:
    print("还没有评论，暂时无法评分。")
else:
    print(f"评论总数：{total} 条")

    for label, count in counts.items():
        percentage = count / total * 100
        print(f"{label}：{count} 条，占比 {percentage:.1f}%")

    # 练习规则：正面算 1 分，中立算 0.5 分，负面算 0 分。
    score = (counts["正面"] + 0.5 * counts["中立"]) / total * 100
    print(f"口碑分：{score:.1f} / 100")