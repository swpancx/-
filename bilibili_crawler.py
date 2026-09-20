"""B 站最新评论采集练习：正常打开网页，保存网页加载的主评论。"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


DEFAULT_VIDEO = "https://www.bilibili.com/video/BV1dhtL65Eo2/"


def default_profile_dir():
    """独立浏览器配置保存在本机应用数据目录，避免混入 GitHub 项目。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BiliCommentCollector" / "browser"


def is_latest_reply_url(url, aid=None):
    parsed = urlparse(url)
    if parsed.hostname != "api.bilibili.com":
        return False
    query = parse_qs(parsed.query)
    oid = query.get("oid", [])
    if len(oid) != 1 or not re.fullmatch(r"[1-9][0-9]*", oid[0]):
        return False
    if query.get("type") != ["1"] or (aid is not None and oid != [str(aid)]):
        return False
    path = parsed.path.rstrip("/")
    if path in ("/x/v2/reply/main", "/x/v2/reply/wbi/main"):
        return query.get("mode") == ["2"]
    return path == "/x/v2/reply" and query.get("sort") == ["0"]


def video_id_from(value):
    """接受 BV 号或完整视频链接，去掉分享跟踪参数。"""
    value = value.strip()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "www.bilibili.com", "bilibili.com"
    ):
        raise ValueError("请填写 bilibili.com 的视频链接，或完整 BV 号。")
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10})/?", parsed.path)
    if not match:
        raise ValueError("链接中没有有效的 BV 号。")
    return match.group(1)


def reply_id(reply):
    value = reply.get("rpid_str") or reply.get("rpid")
    return str(value) if value is not None else ""


class CommentCollector:
    """只接收指定视频、时间排序、首批开始的主评论。"""

    def __init__(self, aid, limit, bvid=""):
        self.aid = str(aid) if aid is not None else None
        self.bvid = bvid
        self.title = bvid
        self.limit = limit
        self.comments = {}
        self.started = False
        self.exhausted = False
        self.blocked = False
        self.last_progress = time.monotonic()
        self.successful_batches = 0
        self.warning = ""
        self.warnings = []
        self.matched_responses = 0

    def bind_video(self, data):
        """只采用网页中与输入 BV 号一致的公开视频信息。"""
        if not self.bvid or not isinstance(data, dict):
            return False
        if data.get("bvid") != self.bvid:
            return False
        aid = str(data.get("aid", ""))
        if not re.fullmatch(r"[1-9][0-9]*", aid):
            return False
        if self.aid is not None and self.aid != aid:
            self.warn("网页返回的视频编号发生变化，未切换采集对象。")
            return False
        self.aid = aid
        title = data.get("title")
        if isinstance(title, str) and title.strip():
            self.title = title
        return True

    def matches(self, url):
        return self.aid is not None and is_latest_reply_url(url, self.aid)

    def warn(self, message):
        self.warning = message
        if message not in self.warnings:
            self.warnings.append(message)

    def is_first_batch(self, url, data):
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        cursor = data.get("cursor") or {}
        if cursor.get("is_begin") is True:
            return True
        if query.get("next") == ["0"] or query.get("pn") == ["1"]:
            return True
        page = data.get("page") or {}
        if page.get("num") == 1:
            return True
        try:
            pagination = json.loads(query.get("pagination_str", ["null"])[0])
        except (ValueError, TypeError):
            pagination = None
        return isinstance(pagination, dict) and pagination.get("offset") == ""

    def ingest(self, url, payload):
        """只处理评论数据，不读取或保存请求头、Cookie、账号资料。"""
        if not self.matches(url):
            return 0
        self.matched_responses += 1
        if not isinstance(payload, dict) or payload.get("code") != 0:
            self.blocked = True
            code = payload.get("code") if isinstance(payload, dict) else "未知"
            self.warn(f"评论请求没有成功（代码 {code}）。请查看浏览器中的提示。")
            return 0
        data = payload.get("data")
        if not isinstance(data, dict):
            self.warn("响应没有有效的 data，未将它视为没有评论。")
            return 0
        replies = data.get("replies")
        if replies is None:
            if self.started and (data.get("cursor") or {}).get("is_end") is True:
                self.exhausted = True
            else:
                self.warn("接口没有返回评论列表，未将空响应视为采集成功。")
            return 0
        if not isinstance(replies, list):
            self.warn("评论结构发生变化，需要检查页面返回的数据。")
            return 0
        if not self.started and not self.is_first_batch(url, data):
            self.warn("正在等待最新评论的第一批。请在网页切换一次排序，再选最新。")
            return 0

        self.blocked = False
        self.warning = ""
        self.started = True
        self.successful_batches += 1
        self.exhausted = (data.get("cursor") or {}).get("is_end") is True

        # 单独返回的置顶评论，不混入本次时间排序样本。
        pinned_ids = set()
        pinned = list(data.get("top_replies") or [])
        upper = data.get("upper") or {}
        if isinstance(upper.get("top"), dict):
            pinned.append(upper["top"])
        top = data.get("top") or {}
        if isinstance(top, dict):
            if reply_id(top):
                pinned.append(top)
            pinned.extend(value for value in top.values() if isinstance(value, dict))
        for item in pinned:
            if isinstance(item, dict) and reply_id(item):
                pinned_ids.add(reply_id(item))

        added = 0
        for item in replies:
            if not isinstance(item, dict):
                continue
            comment_id = reply_id(item)
            if not comment_id or comment_id in pinned_ids:
                continue
            # 不把楼中楼、重复返回的主评论算成新评论。
            if str(item.get("root", 0)) != "0" or str(item.get("parent", 0)) != "0":
                continue
            if comment_id in self.comments:
                continue
            content = item.get("content") or {}
            text = content.get("message")
            created = item.get("ctime")
            if not isinstance(text, str) or not isinstance(created, int) or created <= 0:
                continue
            self.comments[comment_id] = {
                "comment_id": comment_id,
                "text": text,
                "created_at": created,
                "created_at_utc": datetime.fromtimestamp(
                    created, timezone.utc
                ).isoformat(),
                "likes": item.get("like", 0),
            }
            added += 1
        if added:
            self.last_progress = time.monotonic()
        return added

    def result(self):
        # 只对网页实际返回的评论排序；不声称覆盖所有隐藏/删除的评论。
        return sorted(
            self.comments.values(), key=lambda item: item["created_at"], reverse=True
        )[:self.limit]


class BrowserResponses:
    """观察页面自身的响应；视频信息确认之前，暂存少量首批响应。"""

    def __init__(self, collector):
        self.collector = collector
        self.pending = []

    def accept(self, url, status, payload):
        collector = self.collector
        if not collector.matches(url):
            return
        if status != 200:
            collector.blocked = True
            collector.warn(f"评论请求返回 HTTP {status}，已暂停自动操作，请查看网页。")
            return
        added = collector.ingest(url, payload)
        if added:
            print(f"已获得 {len(collector.result())}/{collector.limit} 条主评论。")

    def flush_pending(self):
        if self.collector.aid is None:
            return
        queued, self.pending = self.pending, []
        for item in queued:
            self.accept(*item)

    def __call__(self, response):
        parsed = urlparse(response.url)
        if (self.collector.aid is None and parsed.hostname == "api.bilibili.com"
                and parsed.path in (
                    "/x/web-interface/view", "/x/web-interface/view/detail"
                )):
            try:
                if response.status == 200:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("code") == 0:
                        data = payload.get("data")
                        if isinstance(data, dict):
                            self.collector.bind_video(data.get("View", data))
                            self.flush_pending()
            except Exception:
                pass  # 页面本身也可能已包含公开视频信息。
            return
        if not is_latest_reply_url(response.url, self.collector.aid):
            return
        try:
            payload = response.json() if response.status == 200 else None
            item = (response.url, response.status, payload)
            if self.collector.aid is None:
                if len(self.pending) < 10:
                    self.pending.append(item)
                return
            self.accept(*item)
        except Exception as error:
            self.collector.warn(f"未能读取这次评论响应：{type(error).__name__}")


def first_visible(locators):
    for locator in locators.all():
        if locator.is_visible():
            return locator
    return None


def comment_scope(page):
    area = page.locator("#commentapp")
    return area.first if area.count() else page


def sort_button(page, latest=True):
    area = comment_scope(page)
    header = area.locator("bili-comments-header-renderer")
    if header.count():
        area = header.first
    pattern = re.compile(r"^(最新|按时间排序)$" if latest else r"^(最热|热门|按热度排序)$")
    return (first_visible(area.get_by_role("button", name=pattern))
            or first_visible(area.get_by_text(pattern)))


def login_required(page):
    # 只判断控件是否出现；不读取账号、密码、Cookie 或登录令牌。
    if first_visible(page.get_by_placeholder("请输入账号", exact=True)):
        return True
    if first_visible(page.get_by_text("扫描二维码登录", exact=True)):
        return True
    gate = comment_scope(page).get_by_text(re.compile(r"^登录后查看.*条评论$"))
    return first_visible(gate) is not None


class AutoNavigator:
    """少量、有间隔的网页操作；收到数据之后不再来回切换排序。"""

    def __init__(self):
        self.stage = "find_latest"
        self.clicked_at = None
        self.recovered = False
        self.seek_scrolls = 0
        self.login_opened = False

    def open_login(self, page):
        if self.login_opened:
            return
        gate = first_visible(comment_scope(page).get_by_text(
            re.compile(r"^登录后查看.*条评论$")
        ))
        # 登录框已经打开时不点击其后的遮挡内容。
        if first_visible(page.get_by_placeholder("请输入账号", exact=True)):
            return
        if first_visible(page.get_by_text("扫描二维码登录", exact=True)):
            return
        if gate is not None:
            gate.click(timeout=1500)
            self.login_opened = True

    def after_login(self, collector):
        self.stage = "find_latest"
        self.clicked_at = None
        self.recovered = False
        collector.blocked = False
        collector.exhausted = False
        collector.started = False
        collector.last_progress = time.monotonic()

    def step(self, page, collector, now):
        # 已经切到最热进行一次恢复时，必须先切回最新，才能继续滚动。
        if self.stage == "restore_latest":
            button = sort_button(page)
            if button is not None:
                button.click(timeout=1500)
                self.stage = "waiting"
                self.clicked_at = now
            return None

        if collector.started:
            if now - collector.last_progress > 30:
                return "no_more_progress"
            # 将鼠标置于评论所在的左侧内容区域，再滚动加载。
            page.mouse.move(400, 700)
            page.mouse.wheel(0, 750)
            return None

        if self.stage == "find_latest":
            button = sort_button(page)
            if button is not None:
                button.click(timeout=1500)
                self.clicked_at = now
                self.stage = "waiting"
                print("已自动点击最新，等待网站返回按时间排序的评论。")
                return None
            area = page.locator("#commentapp")
            if area.count():
                area.first.scroll_into_view_if_needed(timeout=1500)
            elif self.seek_scrolls < 5:
                page.mouse.wheel(0, 600)
                self.seek_scrolls += 1
            return None

        if now - self.clicked_at < 12:
            return None
        if not self.recovered:
            # 页面可能记住上次的“最新”；再次点击不会触发新请求。
            # 只切换一次最热→最新，重新取得首批数据。
            button = sort_button(page, latest=False)
            if button is not None:
                button.click(timeout=1500)
                self.recovered = True
                self.stage = "restore_latest"
                print("正在自动重新切换排序，以取得最新评论的第一批。")
                return None
        if now - self.clicked_at > 35:
            return "latest_response_unavailable"
        return None


def collect_on_page(page, bvid, collector, timeout):
    from playwright.sync_api import TimeoutError as BrowserTimeout

    observer = BrowserResponses(collector)
    navigator = AutoNavigator()
    page.on("response", observer)
    last_warning = ""
    video_announced = False
    waiting_login = False
    stop_reason = "timeout"
    started_at = time.monotonic()
    next_action = started_at
    try:
        try:
            navigation = page.goto(
                f"https://www.bilibili.com/video/{bvid}/",
                wait_until="domcontentloaded", timeout=30000
            )
            if navigation is not None and navigation.status >= 400:
                collector.warn(f"视频网页返回 HTTP {navigation.status}，本次已停止。")
                return "video_page_http_error"
        except BrowserTimeout:
            print("页面加载较慢，继续等待。请检查浏览器是否出现登录或验证提示。")

        while time.monotonic() - started_at < timeout:
            if page.is_closed():
                return "browser_closed"
            if collector.warning and collector.warning != last_warning:
                print(collector.warning)
                last_warning = collector.warning
            now = time.monotonic()
            if now < next_action:
                page.wait_for_timeout(250)
                continue
            next_action = now + 2

            # 在其他视频或站点上不会继续操作。
            try:
                current_bvid = video_id_from(page.url)
            except ValueError:
                current_bvid = None
            if current_bvid != bvid:
                collector.warn("页面离开了指定视频，已停止采集。")
                return "video_changed"

            if collector.aid is None:
                data = page.evaluate("""() => {
                    const video = window.__INITIAL_STATE__?.videoData;
                    if (!video) return null;
                    return {bvid: video.bvid, aid: String(video.aid), title: video.title};
                }""")
                collector.bind_video(data)
            observer.flush_pending()

            # 登录提示优先于“没有更多评论”，避免将匿名可见的几条当作全部。
            if login_required(page):
                if not waiting_login:
                    print("需要登录：请在此浏览器中扫码或自行输入账号密码，完成后程序自动继续。")
                    waiting_login = True
                try:
                    navigator.open_login(page)
                except BrowserTimeout:
                    pass
                continue
            if waiting_login:
                print("登录提示已关闭，继续自动切换最新评论。")
                navigator.after_login(collector)
                waiting_login = False
            if collector.blocked:
                return "comment_request_rejected"
            if len(collector.result()) >= collector.limit:
                return "target_reached"
            if collector.exhausted:
                return "site_reported_end"

            if collector.aid is None:
                collector.warn("正在等待网页中的视频信息；如有登录或验证提示，请在浏览器中完成。")
                continue
            if not video_announced:
                print(f"已识别视频：{collector.title}")
                video_announced = True
            try:
                reason = navigator.step(page, collector, now)
            except BrowserTimeout:
                # 不强行穿透登录框等遮挡；留待下次观察页面。
                reason = None
            if reason:
                if reason == "latest_response_unavailable":
                    collector.warn("已经尝试切换最新评论，但网页未返回可识别的首批数据。")
                return reason
        if waiting_login:
            collector.warn("等待登录超时。下次运行会继续使用此浏览器配置。")
            stop_reason = "login_required"
        elif collector.aid is None:
            collector.warn("未能从网页识别视频信息，可能需要适配页面结构。")
            stop_reason = "video_metadata_unavailable"
        return stop_reason
    except KeyboardInterrupt:
        return "user_interrupted"
    except Exception:
        if page.is_closed():
            return "browser_closed"
        raise
    finally:
        page.remove_listener("response", observer)


def collect_in_browser(bvid, collector, timeout):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "请先运行：python -m pip install playwright\n"
            "然后运行：python -m playwright install chromium"
        ) from None
    profile = default_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    print(f"使用本机独立浏览器配置：{profile}")
    print("首次需要登录时请在网页完成；浏览器会在本机保留登录状态，失效时需要重新登录。")
    print("随后会自动切换最新、滚动并保存。关闭浏览器或按 Ctrl+C 可提前结束。")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile), headless=False, viewport={"width": 1280, "height": 900}
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            return collect_on_page(page, bvid, collector, timeout)
        finally:
            context.close()


def save_result(folder, bvid, title, collector, reason):
    comments = collector.result()
    if not comments:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now(timezone.utc)
    filename = (
        f"bilibili_{bvid}_{fetched.strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex}.json"
    )
    output = folder / filename
    document = {
        "source": "bilibili",
        "video_id": bvid,
        "video_title": title,
        "source_url": f"https://www.bilibili.com/video/{bvid}/",
        "fetched_at_utc": fetched.isoformat(),
        "sort": "newest_creation_time",
        "scope": "top_level_replies_returned_by_the_site",
        "requested_count": collector.limit,
        "saved_count": len(comments),
        "reached_requested_count": len(comments) >= collector.limit,
        "stop_reason": reason,
        "successful_batches": collector.successful_batches,
        "warnings": collector.warnings,
        "oldest_comment_at_utc": comments[-1]["created_at_utc"],
        "newest_comment_at_utc": comments[0]["created_at_utc"],
        "comments": comments,
    }
    with output.open("x", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
    text_output = output.with_suffix(".txt")
    lines = [title, document["source_url"],
             f"本次保存 {len(comments)} 条主评论（目标 {collector.limit} 条）", ""]
    for number, comment in enumerate(comments, 1):
        lines.extend([
            f"{number}. {comment['created_at_utc']}  点赞：{comment['likes']}",
            comment["text"], "",
        ])
    try:
        with text_output.open("x", encoding="utf-8") as file:
            file.write("\n".join(lines))
    except OSError:
        print("JSON 已保存，但未能写入便于阅读的 TXT 副本。")
    return output


def main():
    # 让 Windows 终端和重定向输出都能正确显示中文。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="视频链接或 BV 号")
    parser.add_argument("--limit", type=int, default=100, help="目标条数，默认 100")
    parser.add_argument("--timeout", type=int, default=300, help="最多等待秒数，默认 300")
    parser.add_argument("--print-comments", action="store_true", help="同时在终端输出评论原文")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent / "bilibili_data")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 30 <= args.timeout <= 1800:
        parser.error("limit 请设置为 1～1000，timeout 请设置为 30～1800 秒。")
    value = args.url or input("请输入视频链接或 BV 号（回车使用本次示例）：").strip()
    try:
        bvid = video_id_from(value or DEFAULT_VIDEO)
        print(f"准备打开视频：{bvid}")
        collector = CommentCollector(None, args.limit, bvid=bvid)
        try:
            reason = collect_in_browser(bvid, collector, args.timeout)
        except Exception as error:
            if not collector.comments:
                raise
            reason = "browser_error"
            collector.warn(f"浏览器提前停止：{type(error).__name__}")
            print("浏览器提前停止，将保存已经取得的部分评论。")
        output = save_result(
            args.output_dir.resolve(), bvid, collector.title, collector, reason
        )
        if output is None:
            print("本次没有取得可保存的最新评论，未生成空数据文件。")
            print("请检查网页是否要求登录或验证；如果页面已正常显示最新，可能需要适配程序。")
            if collector.warning:
                print(collector.warning)
            return 2
        print(f"已保存 {len(collector.result())} 条评论：{output}")
        if output.with_suffix(".txt").is_file():
            print(f"可以直接阅读或复制的文本：{output.with_suffix('.txt')}")
        if args.print_comments:
            for number, comment in enumerate(collector.result(), 1):
                print(f"\n{number}. {comment['text']}")
        if len(collector.result()) < args.limit:
            print(f"本次不足目标条数，停止原因：{reason}。")
        print("结果只代表本次网页返回的主评论，未包含楼中楼或情感评分。")
        return 0
    except Exception as error:
        print(f"采集未完成：{error}")
        print("没有生成成功结果；已有历史文件不会被覆盖。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
