/* 汇率小宝 v2 — 前端逻辑 */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  const state = {
    theme: "Dark",
    pairs: [],
    activePair: "USD/CNY",
    rate: null,
    busy: false,
  };

  /* ---------- 主题 ---------- */
  const THEMES = ["github", "apple", "dsa", "chrome", "Light", "Dark", "System"];

  /* ---------- 货币中文名 ---------- */
  const CURRENCY_CN = {
    USD: "美元", EUR: "欧元", JPY: "日元", GBP: "英镑", HKD: "港币",
    AUD: "澳大利亚元", CAD: "加拿大元", CHF: "瑞士法郎", SGD: "新加坡元",
    NZD: "新西兰元", CNY: "人民币",
  };

  function getMode(themeName) {
    if (themeName === "Dark")  return "dark";
    if (themeName === "System") return isDarkMode() ? "dark" : "light";
    return "light"; // 浅色 + GitHub/苹果/DSA/Chrome 均为浅色系
  }

  // <html data-theme> 用主题名（System 才解析为 light/dark）
  function themeAttr(name) {
    if (name === "System") return getMode(name);
    return String(name).toLowerCase();
  }

  function setTheme(name) {
    state.theme = name;
    const mode = getMode(name);
    document.documentElement.dataset.theme = themeAttr(name);
    document.documentElement.dataset.manual = "1";
    document.querySelectorAll(".theme-pop-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.theme === name);
    });
    // 通知后端同步系统材质（返回值不一定是 Promise，统一安全兜底）
    if (window.pywebview && window.pywebview.api) {
      safeCall(() => pywebview.api.set_theme(name, mode));
      safeCall(() => pywebview.api.update_window_bg(mode, name));
    }
  }

  // 安全调用：无论后端返回 Promise 还是同步值，都绝不会在前端抛错中断脚本
  function safeCall(fn) {
    try {
      const ret = fn();
      if (ret && typeof ret.then === "function") {
        ret.catch(() => {});
      }
    } catch (e) {
      // 后端方法不存在或调用失败，静默降级（不崩溃）
      console.warn("[safeCall]", e && e.message);
    }
  }

  function isDarkMode() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  /* ---------- 主题下拉交互 ---------- */
  let themePopOpen = false;

  function toggleThemePop() {
    themePopOpen = !themePopOpen;
    $("#themePop").hidden = !themePopOpen;
  }

  document.addEventListener("click", (e) => {
    const pop = $("#themePop");
    if (pop && !pop.hidden) {
      const item = e.target.closest(".theme-pop-item");
      if (item) {
        setTheme(item.dataset.theme);
        pop.hidden = true;
        themePopOpen = false;
        return;
      }
      if (!e.target.closest("#themePop") && !e.target.closest("#btnTheme")) {
        pop.hidden = true;
        themePopOpen = false;
      }
    }
  });

  $("#btnTheme").addEventListener("click", (e) => {
    e.stopPropagation();
    toggleThemePop();
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    setTheme(state.theme);
  });

  /* ---------- 货币对列表 ---------- */
  function renderPairs() {
    const list = $("#pairList");
    list.innerHTML = "";
    state.pairs.forEach((p) => {
      const item = document.createElement("div");
      item.className = "pair-item" + (p.code === state.activePair ? " active" : "");
      item.dataset.code = p.code;
      item.innerHTML = "<span class=\"pair-code\">" + p.code.replace("/", "") + "</span><span class=\"pair-rate\">" + (p.rate || "--") + "</span>";
      item.addEventListener("click", () => selectPair(p.code));
      list.appendChild(item);
    });
  }

  function selectPair(code) {
    state.activePair = code;
    renderPairs();
    updateHero();
    if (window.pywebview && window.pywebview.api) {
      safeCall(() => pywebview.api.select_pair(code));
    }
  }

  function updateHero() {
    const p = state.pairs.find((x) => x.code === state.activePair);
    if (!p) return;
    const [a, b] = p.code.split("/");
    $("#heroPairCode").textContent = p.code;
    $("#heroPairName").textContent = (CURRENCY_CN[a] || a) + " / " + (CURRENCY_CN[b] || b);
    $("#heroRate").textContent = p.rate || "-.----";
    const tagSell = $("#tagSell");
    const tagCash = $("#tagCash");
    const tagCashSell = $("#tagCashSell");
    const setTag = (el, val) => { el.textContent = val; el.classList.toggle("empty", val.includes("--")); };
    setTag(tagSell, "现汇卖出 " + (p.sellRate || "--"));
    setTag(tagCash, "现钞买入 " + (p.cashRate || "--"));
    setTag(tagCashSell, "现钞卖出 " + (p.cashSellRate || "--"));
  }

  /* ---------- 动作 ---------- */
  function appendLog(msg, mode) {
    const body = $("#logBody");
    const empty = body.querySelector(".log-empty");
    if (empty) empty.remove();
    const line = document.createElement("div");
    line.className = "log-line " + (mode || "");
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    line.innerHTML = "<span class=\"log-time\">" + hh + ":" + mm + ":" + ss + "</span><span class=\"log-msg\"></span>";
    line.querySelector(".log-msg").textContent = msg;
    body.appendChild(line);
    body.scrollTop = body.scrollHeight;
  }

  async function fetchRate(pairCode) {
    const code = pairCode || state.activePair;
    if (state.busy) return;
    state.busy = true;
    const btn = $("#btnFetch");
    btn.disabled = true;
    btn.classList.add("loading");
    const dot = $("#statusDot");
    if (dot) dot.classList.add("busy");
    appendLog("正在抓取 " + code + "…", "info");
    try {
      if (window.pywebview && window.pywebview.api) {
        const result = await pywebview.api.fetch_rate(code);
        if (result && result.ok && result.pairs) {
          const idx = state.pairs.findIndex((p) => p.code === code);
          if (idx >= 0) {
            state.pairs[idx] = Object.assign({}, state.pairs[idx], result.pairs[0]);
          }
          renderPairs();
          selectPair(code);
          appendLog(code + " 已更新：" + result.pairs[0].rate, "ok");
        } else {
          appendLog("抓取失败：" + (result?.msg || "未知错误"), "err");
        }
      } else {
        setTimeout(() => {
          const fake = { code: code, rate: (6 + Math.random() * 2).toFixed(4), sellRate: null, cashRate: null, cashSellRate: null };
          const idx = state.pairs.findIndex((p) => p.code === code);
          if (idx >= 0) state.pairs[idx] = Object.assign({}, state.pairs[idx], fake);
          renderPairs();
          selectPair(code);
          appendLog("（演示）" + code + " = " + fake.rate, "ok");
          state.busy = false;
          btn.disabled = false;
          btn.classList.remove("loading");
          if (dot) dot.classList.remove("busy");
        }, 600);
        return;
      }
    } catch (e) {
      appendLog("抓取失败：" + e.message, "err");
      if (dot) { dot.classList.add("err"); setTimeout(() => dot.classList.remove("err"), 2000); }
    } finally {
      state.busy = false;
      btn.disabled = false;
      btn.classList.remove("loading");
      if (dot) dot.classList.remove("busy");
    }
  }

  /* ---------- 全量刷新：更新左侧所有货币对 ---------- */
  async function fetchAll() {
    if (state.busy) return;
    state.busy = true;
    const btn = $("#btnRefresh");
    btn.disabled = true;
    btn.classList.add("loading");
    appendLog("正在同步全部货币对…", "info");
    try {
      if (window.pywebview && window.pywebview.api) {
        const result = await pywebview.api.fetch_all();
        if (result && result.ok && result.pairs && result.pairs.length) {
          const byCode = {};
          result.pairs.forEach((p) => { byCode[p.code] = p; });
          state.pairs = state.pairs.map((p) =>
            byCode[p.code] ? Object.assign({}, p, byCode[p.code]) : p
          );
          renderPairs();
          updateHero();
          if (result.time) $("#syncTime").textContent = "上次更新：" + result.time;
          appendLog("已更新 " + state.pairs.length + " 个货币对", "ok");
        } else {
          appendLog("同步失败：" + (result?.msg || "未知错误"), "err");
        }
      } else {
        // 演示模式
        state.pairs = state.pairs.map((p) =>
          Object.assign({}, p, { rate: (6 + Math.random() * 2).toFixed(4) })
        );
        renderPairs();
        updateHero();
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, "0");
        const mm = String(now.getMinutes()).padStart(2, "0");
        const ss = String(now.getSeconds()).padStart(2, "0");
        $("#syncTime").textContent = "上次更新：" + hh + ":" + mm + ":" + ss;
        appendLog("（演示）已更新全部货币对", "ok");
      }
    } catch (e) {
      appendLog("同步失败：" + e.message, "err");
    } finally {
      state.busy = false;
      btn.disabled = false;
      btn.classList.remove("loading");
    }
  }

  async function copyRate() {
    try {
      if (window.pywebview && window.pywebview.api) await pywebview.api.copy_rate();
      else appendLog("复制汇率（演示）", "ok");
    } catch (e) { appendLog("复制失败：" + e.message, "err"); }
  }

  async function pasteCell() {
    try {
      if (window.pywebview && window.pywebview.api) await pywebview.api.paste_to_cell();
      else appendLog("请在 3 秒内点击表格目标单元格…", "");
    } catch (e) { appendLog("粘贴失败：" + e.message, "err"); }
  }

  /* ---------- 后端事件回调 ---------- */
  function onRateUpdated(data) {
    const idx = state.pairs.findIndex((x) => x.code === data.pair);
    if (idx >= 0) state.pairs[idx] = Object.assign({}, state.pairs[idx], data);
    else state.pairs.push(data);
    renderPairs();
    updateHero();
    if (data.time) $("#syncTime").textContent = "上次更新：" + data.time;
    const dot = $("#statusDot");
    if (dot) dot.classList.remove("busy", "err");
  }

  function onLog(msg, mode) { appendLog(msg, mode); }

  /* ---------- 事件绑定 ---------- */
  $("#btnFetch").addEventListener("click", () => fetchRate(state.activePair));
  $("#btnRefresh").addEventListener("click", fetchAll);
  $("#btnCopy").addEventListener("click", copyRate);
  $("#btnPaste").addEventListener("click", pasteCell);
  $("#btnClearLog").addEventListener("click", () => { $("#logBody").innerHTML = "<div class=\"log-empty\">暂无日志</div>"; });
  $("#btnMin").addEventListener("click", () => { if (window.pywebview && window.pywebview.api) pywebview.api.minimize_window(); });
  $("#btnMax").addEventListener("click", () => { if (window.pywebview && window.pywebview.api) pywebview.api.maximize_window(); });
  $("#btnClose").addEventListener("click", () => { if (window.pywebview && window.pywebview.api) pywebview.api.close_window(); });
  $("#dragRegion").addEventListener("dblclick", () => { if (window.pywebview && window.pywebview.api) pywebview.api.maximize_window(); });

  /* ---------- 心跳上报（黑屏自动纠错） ---------- */
  function startHeartbeat() {
    if (!(window.pywebview && window.pywebview.api)) return;
    const beat = () => safeCall(() => {
      const a = window.pywebview.api;
      if (a && a.heartbeat) a.heartbeat();
    });
    beat();
    setInterval(beat, 5000);
  }

  /* ---------- 左右栏分隔条（按住拖动调整宽度，双击还原） ---------- */
  const SIDEBAR_DEFAULT = 232;
  const splitter = $("#splitter");
  let splitDragging = false;
  let splitTimer = null;

  function applySidebarWidth(w) {
    const appRect = $("#app").getBoundingClientRect();
    const minW = 168;
    const maxW = Math.max(minW, Math.min(420, appRect.width - 440));
    const clamped = Math.round(Math.max(minW, Math.min(maxW, w)));
    document.documentElement.style.setProperty("--sidebar-w", clamped + "px");
    return clamped;
  }

  function persistSidebarWidth(w) {
    if (window.pywebview && window.pywebview.api) {
      safeCall(() => pywebview.api.set_sidebar_width(w));
    }
  }

  if (splitter) {
    splitter.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      splitDragging = true;
      splitter.classList.add("dragging");
      document.body.classList.add("resizing");
      e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
      if (!splitDragging) return;
      const appRect = $("#app").getBoundingClientRect();
      applySidebarWidth(e.clientX - appRect.left);
    });

    window.addEventListener("mouseup", () => {
      if (!splitDragging) return;
      splitDragging = false;
      splitter.classList.remove("dragging");
      document.body.classList.remove("resizing");
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w");
      const w = parseInt(raw, 10) || SIDEBAR_DEFAULT;
      clearTimeout(splitTimer);
      splitTimer = setTimeout(() => persistSidebarWidth(w), 150);
    });

    splitter.addEventListener("dblclick", () => {
      applySidebarWidth(SIDEBAR_DEFAULT);
      persistSidebarWidth(SIDEBAR_DEFAULT);
    });
  }

  /* ---------- 右下角窗口缩放（保持左上角固定） ---------- */
  const grip = $("#resizeGrip");

  if (grip) {
    grip.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      document.body.classList.add("win-resizing");
      e.preventDefault();
      e.stopPropagation();
      if (window.pywebview && window.pywebview.api) {
        safeCall(() => pywebview.api.begin_resize(window.innerWidth, window.innerHeight));
      }
    });
  }

  /* ---------- 渲染自检：DOM 未渲染出来则自动重载（最多 2 次） ---------- */
  function selfCheck() {
    const ok = !!($("#app") && $("#app").clientHeight > 0 && document.documentElement.clientWidth > 0);
    if (ok) {
      window.name = "";
      return;
    }
    const n = (parseInt(window.name || "0", 10) || 0) + 1;
    if (n <= 2) {
      window.name = String(n);
      appendLog("页面渲染异常，自动重载…", "warn");
      location.reload();
    }
  }

  /* ---------- 初始化 ---------- */
  function init(initial) {
    if (initial) {
      if (initial.theme) state.theme = initial.theme;
      if (initial.sidebar_w) {
        document.documentElement.style.setProperty("--sidebar-w", Number(initial.sidebar_w) + "px");
      }
      if (initial.pairs && initial.pairs.length) {
        state.pairs = initial.pairs;
        const saved = initial.pairs.find((x) => x.code === initial.pair);
        state.activePair = (saved || initial.pairs[0]).code;
      }
    }
    setTheme(state.theme);
    renderPairs();
    updateHero();
    appendLog("汇率小宝 v" + (initial && initial.version ? initial.version : "2.0.0") + " 就绪：点击「抓取最新」同步汇率", "");
    startHeartbeat();
    selfCheck();
    setTimeout(selfCheck, 1000);  // 迟到渲染再查一次
  }

  window.frontend = { onRateUpdated, onLog, init, setTheme };

  const FALLBACK = {
    theme: "Dark",
    pairs: [
      { code: "USD/CNY", name: "美元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "EUR/CNY", name: "欧元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "JPY/CNY", name: "日元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "HKD/CNY", name: "港币", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "GBP/CNY", name: "英镑", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "AUD/CNY", name: "澳元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "CAD/CNY", name: "加元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "CHF/CNY", name: "瑞郎", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "SGD/CNY", name: "新元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
      { code: "NZD/CNY", name: "新西兰元", rate: null, sellRate: null, cashRate: null, cashSellRate: null },
    ],
  };

  function _loadFromBackend() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_init) {
      // get_init 返回值可能是 Promise 也可能是同步值，统一安全处理
      try {
        const ret = pywebview.api.get_init();
        if (ret && typeof ret.then === "function") {
          ret.then((data) => init(data)).catch(() => init(FALLBACK));
        } else if (ret) {
          init(ret);
        } else {
          init(FALLBACK);
        }
      } catch (e) {
        console.warn("[get_init]", e && e.message);
        init(FALLBACK);
      }
    } else {
      init(FALLBACK);
    }
  }

  if (window.pywebview && window.pywebview.api) {
    _loadFromBackend();
  } else {
    init(FALLBACK);
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (window.pywebview && window.pywebview.api && window.pywebview.api.get_init) {
        clearInterval(timer);
        _loadFromBackend();
      } else if (tries > 40) {
        clearInterval(timer);
      }
    }, 250);
  }
})();
