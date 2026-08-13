"""汇率小宝 v2 — 入口。
- 窗口：pywebview (WebView2)，无边框自定义标题栏
- 材质：DWM 系统级 Acrylic（Win11）/ 兼容 Win10
- 后端：汇率抓取、剪贴板、粘贴单元格、主题持久化
"""
import sys
import os
import json
import threading
import time
from datetime import datetime

from core import acrylic
from core import rate as rate_core
from core import config

APP_TITLE = "汇率小宝"
APP_VERSION = "2.0.0"

# 浅色系主题（窗口材质 / 标题栏按深色模式处理时用）
LIGHT_THEMES = {"Light", "github", "apple", "dsa", "chrome"}

# 各主题的页面背景色（仅作 html 画布兜底，实际背景由 CSS 绘制）
BG_COLORS = {
    "Light": "#F5F6F8",
    "Dark": "#16181D",
    "github": "#F6F8FA",
    "apple": "#F5F5F7",
    "dsa": "#EAF2FA",
    "chrome": "#E8F0FE",
}

# ---- 黑屏自动纠错（看门狗）参数 ----
WATCHDOG_INTERVAL = 3      # 看门狗检查间隔（秒）
HB_TIMEOUT = 12            # 心跳超时（秒），超过即判页面无响应
PROBE_EVERY = 6            # 每 N 次检查做一次中心像素探测（约 18s 一次）
RECOVER_GRACE = 12         # 启动宽限期（秒），期间不判死
RECOVER_MAX = 3            # 连续自动恢复次数上限，超过则提示重启
RECOVER_COOLDOWN = 8       # 恢复后短暂宽限，避免连环触发


def _system_is_dark():
    """读取系统深/浅色模式（注册表）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return v == 0
    except Exception:
        return False


def _theme_is_dark(name, mode=None):
    """主题名（或前端解析后的模式）→ 是否深色，用于窗口材质/标题栏。"""
    if mode is not None:
        return mode == "dark"
    if name in LIGHT_THEMES:
        return False
    if name == "System":
        return _system_is_dark()
    return True


def _find_hwnd_by_title(title):
    """按窗口标题查找顶层窗口句柄（Win32 枚举，打包后也可靠）。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    result = []

    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value == title:
            result.append(hwnd)
            return False
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return result[0] if result else None


class Api:
    """暴露给前端 JS 的后端桥接 API（方法名与前端 pywebview.api.* 严格对齐）。"""

    # 最常用的 10 个货币对
    # 按国际外汇市场交易量排名（BIS），排除人民币本身（本应用均为 X/CNY 交叉盘）
    DEFAULT_PAIRS = [
        {"code": "USD/CNY", "name": "美元"},
        {"code": "EUR/CNY", "name": "欧元"},
        {"code": "JPY/CNY", "name": "日元"},
        {"code": "GBP/CNY", "name": "英镑"},
        {"code": "AUD/CNY", "name": "澳大利亚元"},
        {"code": "CAD/CNY", "name": "加拿大元"},
        {"code": "CHF/CNY", "name": "瑞士法郎"},
        {"code": "HKD/CNY", "name": "港币"},
        {"code": "SGD/CNY", "name": "新加坡元"},
        {"code": "NZD/CNY", "name": "新西兰元"},
    ]

    def __init__(self):
        self._crawling = threading.Lock()
        self._latest = []          # 最近一次抓取的 pairs
        self._cfg = config.load_config()
        self._theme = self._cfg.get("theme", "Dark")
        self._pair = self._cfg.get("pair", "USD/CNY")
        self._hb = time.time()     # 前端心跳时间戳（黑屏看门狗用）

    # ---------- 心跳（黑屏自动纠错） ----------
    def heartbeat(self):
        """前端周期性上报"页面存活"，看门狗据此判断渲染是否卡死。"""
        self._hb = time.time()
        return {"ok": True}

    # ---------- 初始化 ----------
    def get_init(self):
        """前端启动时拉取初始状态（主题 + 10 个默认货币对占位）。"""
        pairs = [dict(p, rate=None, sellRate=None, cashRate=None, cashSellRate=None)
                 for p in self.DEFAULT_PAIRS]
        # 尝试用上次缓存填充
        cache = config.load_cache()
        if isinstance(cache.get("pairs"), list):
            cached = {p["code"]: p for p in cache["pairs"] if isinstance(p, dict)}
            for item in pairs:
                if item["code"] in cached:
                    item.update(cached[item["code"]])
        return {
            "ok": True,
            "theme": self._theme,
            "pair": self._pair,
            "pairs": pairs,
            "sidebar_w": self._cfg.get("sidebar_w", 232),
            "version": APP_VERSION,
        }

    # ---------- 汇率抓取 ----------
    def fetch_rate(self, pair_code=None):
        """抓取中国银行全部牌价，但只返回请求的那个货币对（避免404）。"""
        if not self._crawling.acquire(blocking=False):
            return {"ok": False, "msg": "正在抓取中，请稍候"}
        try:
            rows = rate_core.fetch_rate_rows()
            if not rows:
                return {"ok": False, "msg": "抓取失败：未获取到牌价，请检查网络"}
            all_pairs = rate_core.build_pairs(rows)
            # 只取请求的这一个
            target = None
            for p in all_pairs:
                if pair_code and p["code"] == pair_code:
                    target = p
                    break
            if not target and all_pairs:
                target = all_pairs[0]
            if not target:
                return {"ok": False, "msg": "未找到该货币对数据"}
            now = datetime.now().strftime("%H:%M:%S")
            # 更新内存缓存
            idx = next((i for i, d in enumerate(self._latest) if d.get("code") == target["code"]), None)
            if idx is not None:
                self._latest[idx].update(target)
            else:
                self._latest.append(target)
            config.save_cache({"pairs": self._latest, "saved_at": now})
            self._log(f"已同步 {target['code']} = {target['rate']}")
            return {"ok": True, "pairs": [target], "time": now}
        except Exception as e:
            self._log("抓取异常：" + str(e))
            return {"ok": False, "msg": "抓取异常：" + str(e)}
        finally:
            self._crawling.release()

    def fetch_all(self):
        """抓取全部货币对牌价，一次性更新左侧所有数据。"""
        if not self._crawling.acquire(blocking=False):
            return {"ok": False, "msg": "正在抓取中，请稍候"}
        try:
            rows = rate_core.fetch_rate_rows()
            if not rows:
                return {"ok": False, "msg": "抓取失败：未获取到牌价，请检查网络"}
            all_pairs = rate_core.build_pairs(rows)
            if not all_pairs:
                return {"ok": False, "msg": "未获取到牌价数据"}
            self._latest = all_pairs
            now = datetime.now().strftime("%H:%M:%S")
            config.save_cache({"pairs": all_pairs, "saved_at": now})
            self._log("已同步全部 %d 个货币对" % len(all_pairs))
            return {"ok": True, "pairs": all_pairs, "time": now}
        except Exception as e:
            self._log("抓取异常：" + str(e))
            return {"ok": False, "msg": "抓取异常：" + str(e)}
        finally:
            self._crawling.release()

    # ---------- 主题 / 货币对 ----------
    def set_theme(self, name, mode=None):
        """持久化主题选择，并同步系统级深色模式与窗口背景色。"""
        self._theme = name
        cfg = config.load_config()
        cfg["theme"] = name
        config.save_config(cfg)
        self._log("主题已切换：" + name)
        # 通知前端更新窗口材质（调用模块级函数，不是 Api 方法）
        try:
            import webview as _w
            w = _w.windows[0] if _w.windows else None
            if w:
                _apply_material(w, name, mode)
        except Exception:
            pass
        return {"ok": True}

    def update_window_bg(self, mode, theme_name=None):
        """设置根元素兜底背景色（仅画布层），页面背景由 CSS 主题负责。"""
        try:
            import webview as _w
            w = _w.windows[0] if _w.windows else None
            if not w:
                return {"ok": True}
            bg = BG_COLORS.get(theme_name)
            if not bg:
                bg = "#F5F6F8" if mode == "light" else "#16181D"
            w.evaluate_js(
                "document.documentElement.style.background='" + bg + "';"
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def select_pair(self, code):
        """持久化当前查看的货币对。"""
        self._pair = code
        cfg = config.load_config()
        cfg["pair"] = code
        config.save_config(cfg)
        return {"ok": True}

    def set_sidebar_width(self, width):
        """持久化侧边栏宽度（左右栏分隔条拖拽后保存）。"""
        try:
            cfg = config.load_config()
            cfg["sidebar_w"] = int(width)
            config.save_config(cfg)
        except Exception:
            pass
        return {"ok": True}

    def begin_resize(self, start_w, start_h):
        """右下角缩放：后台线程跟随鼠标直到松开左键（保持左上角固定）。"""
        try:
            import webview as _w
            w = _w.windows[0] if _w.windows else None
            if not w:
                return {"ok": False}
            hwnd1 = _get_hwnd(w)
            hwnd2 = _find_hwnd_by_title(APP_TITLE)
            hwnd = hwnd1 or hwnd2
            if not hwnd:
                return {"ok": False}
            threading.Thread(
                target=self._resize_loop,
                args=(w, hwnd, int(start_w), int(start_h)),
                daemon=True,
            ).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def _resize_loop(self, w, hwnd, start_w, start_h):
        """跟随鼠标位置缩放窗口，直到左键松开。"""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        ox, oy = pt.x, pt.y
        try:
            dpi = user32.GetDpiForWindow(hwnd)
            scale = max(1.0, dpi / 96.0)
        except Exception:
            scale = 1.0
        try:
            while user32.GetAsyncKeyState(0x01) & 0x8000:  # 左键按住
                user32.GetCursorPos(ctypes.byref(pt))
                nw = max(720, int(start_w + (pt.x - ox) / scale))
                nh = max(560, int(start_h + (pt.y - oy) / scale))
                try:
                    w.resize(nw, nh)
                except Exception:
                    break
                time.sleep(0.03)
        finally:
            try:
                w.evaluate_js("document.body.classList.remove('win-resizing')")
            except Exception:
                pass

    # ---------- 复制 / 粘贴 ----------
    def copy_rate(self):
        """复制当前显示汇率到剪贴板。"""
        if not self._latest:
            return {"ok": False, "msg": "暂无汇率数据，请先抓取"}
        try:
            import pyperclip
            p = self._latest[0] if isinstance(self._latest[0], dict) else None
            value = p["rate"] if p and p.get("rate") else (self._latest[0] if isinstance(self._latest[0], str) else None)
            if not value:
                return {"ok": False, "msg": "暂无可复制的汇率，请先抓取"}
            pyperclip.copy(value)
            self._log("已复制：" + value)
            return {"ok": True, "msg": "已复制：" + value}
        except Exception as e:
            return {"ok": False, "msg": "复制失败：" + str(e)}

    def paste_to_cell(self):
        """3 秒倒计时后，粘贴汇率到当前聚焦单元格（模拟键盘）。"""
        if not self._latest:
            return {"ok": False, "msg": "暂无汇率数据，请先抓取"}
        first = self._latest[0]
        value = first.get("rate") if isinstance(first, dict) else str(first)
        if not value:
            return {"ok": False, "msg": "暂无可粘贴的汇率，请先抓取"}

        def _do():
            try:
                import pyautogui
                import pyperclip
                self._log("3 秒后自动粘贴到当前单元格…")
                time.sleep(3)
                old = pyperclip.paste() or ""
                pyperclip.copy("")
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.3)
                selected = pyperclip.paste().strip()
                if selected and selected != value:
                    self._log("目标单元格已有内容「" + selected + "」，将覆盖")
                pyperclip.copy(value)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyautogui.press("enter")
                pyperclip.copy(old)
                self._log("已写入 " + value + " 到选中单元格")
            except Exception as e:
                self._log("粘贴失败：" + str(e))

        threading.Thread(target=_do, daemon=True).start()
        return {"ok": True, "msg": "3 秒后将自动粘贴到当前单元格"}

    def open_config_dir(self):
        """打开配置目录（资源管理器）。"""
        import subprocess
        d = config.app_data_dir()
        try:
            os.makedirs(d, exist_ok=True)
            subprocess.Popen(["explorer", d])
        except Exception as e:
            print("打开配置目录失败:", e)

    # ---------- 窗口控制 ----------
    def _win(self):
        import webview as _w
        return _w.windows[0] if _w.windows else None

    def minimize_window(self):
        w = self._win()
        if w:
            w.minimize()
        return {"ok": True}

    def maximize_window(self):
        w = self._win()
        if w:
            if w.maximized:
                w.restore()
            else:
                w.maximize()
        return {"ok": True}

    def close_window(self):
        w = self._win()
        if w:
            w.destroy()
        return {"ok": True}

    # ---------- 日志 ----------
    def _log(self, text, mode="info"):
        """内部日志钩子（前端自己渲染日志，这里仅打底）。"""
        print(f"[{mode}] {text}")

    def _notify(self, text, mode="info"):
        """看门狗消息：打底日志 + 尽力推送到前端「运行提示」（JS 死了则静默）。"""
        self._log(text, mode)
        try:
            w = self._win()
            if w:
                w.evaluate_js(
                    "window.frontend && window.frontend.onLog && "
                    "window.frontend.onLog(" + json.dumps(text, ensure_ascii=False) + ", " +
                    json.dumps(mode, ensure_ascii=False) + ")"
                )
        except Exception:
            pass


def _get_hwnd(w):
    """从 pywebview 窗口对象提取原生窗口句柄（多版本兼容）。"""
    native = getattr(w, "native", None) or getattr(w, "gui", None)
    for attr in ("hwnd", "_hwnd", "_wayland_handle", "_window"):
        try:
            v = getattr(native, attr, None)
            if isinstance(v, int) and v:
                return v
            if v is not None and hasattr(v, "hwnd"):
                return v.hwnd
        except Exception:
            continue
    # edgechromium (WinForms)：w.native 就是窗体本身（或 .form 属性）
    for obj in (native, getattr(native, "form", None)):
        if obj is None:
            continue
        for conv in ("ToInt64", "ToInt32"):
            try:
                h = int(getattr(obj.Handle, conv)())
                if h:
                    return h
            except Exception:
                continue
    return None


def _apply_material(w, theme_name="Dark", mode=None):
    """对已就绪窗口应用系统材质。theme_name 决定系统深色/浅色模式。

    材质应用成功后强制 DWM 重绘一次（防偶发全黑）。
    """
    is_dark = _theme_is_dark(theme_name, mode)
    try:
        hwnd = _get_hwnd(w)
        if not hwnd:
            hwnd = _find_hwnd_by_title(APP_TITLE)
        if not hwnd:
            print("WARN: 未取得窗口句柄，跳过材质设置")
            return
        mode = acrylic.enable_acrylic(hwnd)
        acrylic.set_dark_mode(hwnd, is_dark)
        acrylic.set_round_corners(hwnd, True)
        if mode:
            acrylic.nudge_repaint(hwnd)  # 防 DWM 合成卡死
        print("已启用材质:", mode, "  主题:", theme_name)
    except Exception as e:
        print("材质设置失败，回退普通背景:", e)


def _enable_resize_borders(hwnd):
    """给无边框窗口加回原生缩放边框：四边/四角均可鼠标拖拽调整大小。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            0x0001 | 0x0002 | 0x0004 | 0x0020,  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
        )
        return True
    except Exception:
        return False


def _probe_black(hwnd):
    """取窗口中心像素：纯黑/近黑 = 渲染卡死（即使 JS 心跳还活着）。"""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        h = ctypes.wintypes.HWND(int(hwnd))
        r = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(h, ctypes.byref(r)):
            return False
        cx = (r.left + r.right) // 2
        cy = (r.top + r.bottom) // 2
        dc = user32.GetDC(0)
        try:
            px = gdi32.GetPixel(dc, cx, cy)
        finally:
            user32.ReleaseDC(0, dc)
        if px == 0xFFFFFFFF:  # 取色失败
            return False
        rr = px & 0xFF
        gg = (px >> 8) & 0xFF
        bb = (px >> 16) & 0xFF
        return rr < 12 and gg < 12 and bb < 12
    except Exception:
        return False


def _recover(w, api, index_url, nudge_only=False):
    """自动恢复动作（静默）：按需整页重载 → 重刷材质 → 强制重绘。"""
    try:
        if not nudge_only:
            try:
                w.load_url(index_url)
                api._log("已触发页面重载")
            except Exception as e:
                api._log("重载失败:" + str(e))
        try:
            _apply_material(w, api._theme)
        except Exception:
            pass
        hwnd = _get_hwnd(w) or _find_hwnd_by_title(APP_TITLE)
        if hwnd:
            acrylic.nudge_repaint(hwnd)
    except Exception as e:
        api._log("自动恢复异常:" + str(e))


def _watchdog(api, index_url):
    """黑屏看门狗（后台线程）：心跳超时 → 整页重载；心跳正常但中心像素
    纯黑 → 只重刷材质+重绘（不打扰）。连续 RECOVER_MAX 次无效则提示重启。
    """
    import webview as _w
    time.sleep(2)
    failures = 0
    probe_tick = 0
    grace_until = time.time() + RECOVER_GRACE
    while True:
        try:
            if not _w.windows:
                time.sleep(1)
                continue
            w = _w.windows[0]
            now = time.time()
            hb_dead = (now - api._hb) > HB_TIMEOUT
            if now < grace_until:
                hb_dead = False

            recovered = False
            if hb_dead:
                api._notify("页面无响应，正在自动重载…", "warn")
                _recover(w, api, index_url, nudge_only=False)
                failures += 1
                recovered = True
            else:
                failures = 0
                probe_tick += 1
                if probe_tick >= PROBE_EVERY:
                    probe_tick = 0
                    hwnd = _get_hwnd(w) or _find_hwnd_by_title(APP_TITLE)
                    if hwnd and _probe_black(hwnd):
                        api._notify("检测到界面渲染异常（全黑），正在自动恢复…", "warn")
                        _recover(w, api, index_url, nudge_only=True)
                        failures += 1
                        recovered = True

            if recovered:
                grace_until = now + RECOVER_COOLDOWN
                if failures >= RECOVER_MAX:
                    api._notify("多次自动恢复无效，建议重启应用", "err")
                    failures = 0
        except Exception:
            pass
        time.sleep(WATCHDOG_INTERVAL)


def main():
    acrylic.set_dpi_awareness()
    import webview

    api = Api()
    index_url = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    window = webview.create_window(
        APP_TITLE,
        index_url,
        js_api=api,
        width=860,
        height=640,
        min_size=(720, 560),
        resizable=True,
        frameless=True,
        easy_drag=False,  # 由前端顶部区域拖拽
        background_color="#16181D",
    )

    # 页面加载完成后窗口必已创建，此时应用亚克力材质
    def _on_loaded(window):
        hwnd = _get_hwnd(window) or _find_hwnd_by_title(APP_TITLE)
        if hwnd:
            _enable_resize_borders(hwnd)  # 四边可缩放
        _apply_material(window, api._theme)

    window.events.loaded += _on_loaded

    # 黑屏看门狗：独立线程，随主进程存活
    threading.Thread(target=_watchdog, args=(api, index_url), daemon=True).start()

    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
