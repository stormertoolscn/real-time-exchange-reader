# 汇率小宝 v2（fx-helper）

中国银行实时牌价桌面小工具：无边框窗口、实时汇率、一键复制 / 粘贴单元格。

## 功能

- 实时抓取中国银行外汇牌价，内置世界最常用的 10 个货币对（美元、欧元、日元、英镑、澳元、加元、瑞郎、港币、新加坡元、新西兰元）
- 右侧大卡显示当前货币对：现汇买入价、现汇卖出、现钞买入、现钞卖出
- 点击顶栏「刷新」按钮一键更新全部货币对
- 主题：浅色 / 深色 / 跟随系统，以及 GitHub、苹果、DSA、Chrome 四种风格
- 无边框窗口：顶部拖拽移动、左右栏分隔条调整宽度（双击还原）、右下角拖拽缩放
- 复制汇率到剪贴板；3 秒倒计时后自动粘贴到当前选中的表格单元格
- 自动记忆主题、当前货币对、侧栏宽度；黑屏自动纠错（看门狗）

## 运行

```powershell
py app.py
```

或直接双击 `run.bat`。

依赖：`pip install -r requirements.txt`（Python 3.11+，Windows 10/11，需要 WebView2 运行时）。

## 打包

```powershell
.\build.ps1
```

产物在 `dist\汇率小宝 v2.0.1.exe`。

## 技术栈

- Python + [pywebview](https://pywebview.flowrl.com/)（WebView2）
- 中国银行牌价接口（`https://www.boc.cn/sourcedb/whpj/`）
- 前端为原生 HTML / CSS / JavaScript，无框架
