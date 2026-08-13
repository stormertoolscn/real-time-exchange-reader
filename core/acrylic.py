"""Windows 11 Acrylic / Mica 系统材质封装 (ctypes)。

核心：
- DWMWA_SYSTEMBACKDROP_TYPE = 38，Acrylic = 4 / Mica = 2（Win11 22000+ 公共 API）
- Windows 10 回退：SetWindowCompositionAttribute（ACCENT_ENABLE_ACRYLICBLURBEHIND）
- DWMWA_USE_IMMERSIVE_DARK_MODE = 20 跟随深色模式
- DWMWA_WINDOW_CORNER_PREFERENCE = 33，圆角 = 2
"""
import ctypes
import ctypes.wintypes as wt

# ---- 常量 ----
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT = 1029  # 旧版，仅 22000-22522

# DWMSBT_* 系统背景类型（Win11）
DWMSBT_NONE = 0            # 无背景效果（回退纯色）
DWMSBT_MAINWINDOW = 1      # Mica（文雅浅色）
DWMSBT_TRANSIENTWINDOW = 2 # Acrylic（亚克力，强毛玻璃）★ 我们要的
DWMSBT_TABBEDWINDOW = 3    # Mica Alt

# SetWindowPos 标志
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# WCA / accent
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
ACCENT_ENABLE_BLURBEHIND = 3

# 圆角偏好
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2

_dwmapi = ctypes.WinDLL("dwmapi")

class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint)]

class WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t)]


def _set_attr(hwnd, attr, value):
    """通用 DwmSetWindowAttribute 调用。"""
    try:
        v = ctypes.c_int(value)
        _dwmapi.DwmSetWindowAttribute(
            wt.HWND(hwnd), ctypes.c_uint(attr),
            ctypes.byref(v), ctypes.sizeof(v),
        )
        return True
    except Exception:
        return False


def _set_win10_accent(hwnd, state, flags=0, color=0):
    """Win10 兼容路径：SetWindowCompositionAttribute。"""
    try:
        user32 = ctypes.windll.user32
        h = wt.HWND(int(hwnd))
        accent = ACCENTPOLICY(state, flags, color, 0)
        data = WINCOMPATTRDATA(WCA_ACCENT_POLICY, ctypes.addressof(accent), ctypes.sizeof(accent))
        return bool(user32.SetWindowCompositionAttribute(h, ctypes.byref(data)))
    except Exception:
        return False


def enable_acrylic(hwnd):
    """优先 Win11 系统级 Acrylic，失败回退 Win10 兼容方案。"""
    ok = _set_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW)
    if ok:
        return "acrylic"
    # Win10 回退
    if _set_win10_accent(hwnd, ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, 0x72141921):
        return "acrylic-win10"
    return None


def disable_acrylic(hwnd):
    """取消系统背景效果（回退纯色背景），用于材质合成异常的兜底恢复。"""
    _set_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
    _set_win10_accent(hwnd, ACCENT_DISABLED)
    return True


def enable_mica(hwnd):
    _set_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_MAINWINDOW)
    return True


def set_dark_mode(hwnd, dark=True):
    _set_attr(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def set_round_corners(hwnd, round=True):
    _set_attr(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND if round else DWMWCP_DONOTROUND)


def set_dpi_awareness():
    """高 DPI 防糊（进程级）。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def nudge_repaint(hwnd):
    """强制 DWM 重新合成：1px 尺寸微调后还原 + FRAMECHANGED。

    修复「亚克力材质 + WebView2 合成偶发全黑」——DWM 在特定显卡/系统
    组合下不刷新画面，微调尺寸可触发重绘。返回是否成功。
    """
    try:
        user32 = ctypes.windll.user32
        h = wt.HWND(int(hwnd))
        r = wt.RECT()
        if not user32.GetWindowRect(h, ctypes.byref(r)):
            return False
        w = r.right - r.left
        hh = r.bottom - r.top
        # 先放大 1px（仅触发重绘，用户几乎无感知）
        user32.SetWindowPos(h, None, r.left, r.top, w + 1, hh + 1,
                            SWP_NOZORDER | SWP_NOACTIVATE)
        # 还原尺寸 + FRAMECHANGED 强制 DWM 重算
        user32.SetWindowPos(h, None, r.left, r.top, w, hh,
                            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True
    except Exception:
        return False