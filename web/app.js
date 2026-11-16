/* TrainerHub 前端逻辑 v1.6.1 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var api = null;
  var state = {
    library: [], config: {}, updates: [],
    detail: null, sort: 'added',
    hkCollapsed: {}, currentModGame: null, allMods: [], modsQuery: '',
    hub: [], hubQuery: '', hubGameId: null,   // 当前下钻到的游戏 id
    hubDetailOpt: null,                        // 当前下钻的内容类型 trainer/mods
    scanCandidates: [], scanChecked: {}, scanFolder: ''
  };

  window.addEventListener('pywebviewready', init);

  function init() {
    api = window.pywebview.api;
    bindNav(); bindLibrary(); bindOnline(); bindHotkeys(); bindSettings();
    bindMods(); bindConfirm(); bindHub();
    loadLibrary(); loadConfig(); renderHotkeys(); renderOnlineIdle(); loadAllMods(); loadHub();
    maybeShowSafety();
  }

  // ---------- 工具 ----------
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function toast(msg, type) {
    var t = $('toast'); t.textContent = msg;
    t.className = 'toast show' + (type ? ' ' + type : '');
    clearTimeout(t._timer); t._timer = setTimeout(function () { t.className = 'toast'; }, 3000);
  }
  function fmtSize(b) {
    if (!b) return '—';
    if (b < 1048576) return (b / 1024).toFixed(0) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }
  // 通用确认框：返回 Promise<bool>，不依赖 window.confirm
  function ask(title, bodyHtml, okText) {
    return new Promise(function (resolve) {
      $('confirmTitle').textContent = title;
      $('confirmBody').innerHTML = bodyHtml;
      $('confirmOk').textContent = okText || '确定';
      $('confirmOverlay').style.display = 'flex';
      function done(v) {
        $('confirmOverlay').style.display = 'none';
        $('confirmOk').onclick = null; $('confirmCancel').onclick = null;
        resolve(v);
      }
      $('confirmOk').onclick = function () { done(true); };
      $('confirmCancel').onclick = function () { done(false); };
    });
  }

  // 通用输入弹窗：fields=[{key,label,placeholder,value}]，返回 Promise<obj|null>
  function prompt(title, bodyHtml, fields, okText) {
    return new Promise(function (resolve) {
      $('promptTitle').textContent = title;
      $('promptBody').innerHTML = bodyHtml || '';
      $('promptOk').textContent = okText || '确定';
      $('promptFields').innerHTML = fields.map(function (f) {
        return '<label class="prompt-field"><span>' + esc(f.label) + '</span>' +
          '<input type="text" data-k="' + esc(f.key) + '" ' +
          'placeholder="' + esc(f.placeholder || '') + '" value="' + esc(f.value || '') + '"></label>';
      }).join('');
      $('promptOverlay').style.display = 'flex';
      var first = $('promptFields').querySelector('input');
      if (first) { first.focus(); }
      function done(v) {
        $('promptOverlay').style.display = 'none';
        $('promptOk').onclick = null; $('promptCancel').onclick = null;
        resolve(v);
      }
      $('promptOk').onclick = function () {
        var out = {};
        $('promptFields').querySelectorAll('input').forEach(function (inp) {
          out[inp.dataset.k] = inp.value.trim();
        });
        done(out);
      };
      $('promptCancel').onclick = function () { done(null); };
    });
  }

  // ---------- 导航 ----------
  var TITLES = { library: '修改器库', hub: '游戏库', online: '修改器在线下载', mods: 'Mod 管理', hotkeys: '快捷键说明', settings: '设置' };
  function bindNav() {
    document.querySelectorAll('.nav-item').forEach(function (it) {
      it.addEventListener('click', function () { goto(it.dataset.page); });
    });
    document.querySelectorAll('[data-goto]').forEach(function (b) {
      b.addEventListener('click', function () { goto(b.dataset.goto); });
    });
  }
  function goto(page) {
    document.querySelectorAll('.nav-item').forEach(function (it) {
      it.classList.toggle('active', it.dataset.page === page);
    });
    document.querySelectorAll('.page').forEach(function (p) {
      p.classList.toggle('active', p.id === 'page-' + page);
    });
    $('pageTitle').textContent = TITLES[page] || '';
    if (page === 'mods') { loadAllMods(); }
    if (page === 'hub') { loadHub(); }
  }

  // ---------- 修改器库 ----------
  function bindLibrary() {
    $('btnImport').addEventListener('click', doImport);
    $('btnOpenFolder').addEventListener('click', openFolder);
    $('btnOpenFolder2').addEventListener('click', openFolder);
    $('libSearch').addEventListener('input', renderLibrary);
    $('libSort').addEventListener('change', function () { state.sort = this.value; renderLibrary(); });
  }

  async function loadLibrary() {
    try {
      state.library = await api.get_library();
      renderLibrary();
      $('libCount').textContent = state.library.length;
      fillHashSelect();
    } catch (e) { toast('读取修改器库失败', 'error'); }
  }

  function renderLibrary() {
    var kw = ($('libSearch').value || '').trim().toLowerCase();
    var list = state.library.filter(function (x) {
      return !kw || (x.name || '').toLowerCase().indexOf(kw) >= 0;
    });

    // 排序
    var sort = state.sort;
    list.sort(function (a, b) {
      if (sort === 'name') return (a.name || '').localeCompare(b.name || '');
      if (sort === 'lastLaunch') return (b.last_launch || '').localeCompare(a.last_launch || '');
      return (b.added || '').localeCompare(a.added || '');
    });

    var grid = $('trainerGrid'), empty = $('libEmpty');
    if (!state.library.length) {
      grid.innerHTML = '';
      empty.innerHTML =
        '<div class="empty-state"><div class="empty-icon">▦</div>' +
        '<div class="empty-title">库里还是空的</div>' +
        '<div class="empty-desc">导入本地修改器，或去「修改器在线下载」从风灵月影官网获取免费独立版。</div>' +
        '<div class="empty-actions"><button class="btn btn-primary" data-goto="online">去在线下载修改器</button>' +
        '<button class="btn btn-ghost" id="btnImport2">导入本地文件</button></div></div>';
      empty.querySelector('[data-goto]').addEventListener('click', function () { goto('online'); });
      $('btnImport2').addEventListener('click', doImport);
      return;
    }
    empty.innerHTML = '';
    if (!list.length) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><div class="empty-title">没有匹配的修改器</div><div class="empty-desc">换个关键词试试。</div></div>';
      return;
    }

    grid.innerHTML = list.map(function (x) {
      var updated = state.updates.indexOf(x.id) >= 0;
      var running = !!x.last_launch;
      return '' +
        '<div class="trainer-card">' +
          (updated ? '<div class="update-flag">有新版</div>' : '') +
          '<div class="card-head">' +
            '<div class="card-icon">▣</div>' +
            '<div class="card-info">' +
              '<div class="card-title">' + esc(x.name) + '</div>' +
              '<div class="card-version">' + esc(x.version || '—') + '</div>' +
            '</div>' +
          '</div>' +
          '<div class="card-detail">' +
            '<div class="detail-line"><span class="dl-k">支持版本</span><span class="dl-v">' + esc(x.version || '未知') + '</span></div>' +
            '<div class="detail-line"><span class="dl-k">EXE 文件</span><span class="dl-v mono" title="' + esc(x.filename) + '">' + esc(x.filename || '—') + '</span></div>' +
            '<div class="detail-line"><span class="dl-k">本地路径</span><span class="dl-v mono path" title="' + esc(x.path) + '">' + esc(x.path || '—') + '</span></div>' +
            (x.options ? '<div class="detail-line"><span class="dl-k">功能项</span><span class="dl-v">' + x.options + ' 项</span></div>' : '') +
            '<div class="detail-line"><span class="dl-k">最近启动</span><span class="dl-v">' + esc(x.last_launch || '从未') + '</span></div>' +
            (x.source_url ? '<div class="detail-line"><span class="dl-k">来源</span><a class="dl-v link" href="' + esc(x.source_url) + '" target="_blank">官网页面 ↗</a></div>' : '') +
          '</div>' +
          '<div class="card-meta">' +
            '<span>◷ ' + esc(x.added || '') + '</span>' +
            '<span class="mono-num">▤ ' + fmtSize(x.size) + '</span>' +
          '</div>' +
          '<div class="card-actions">' +
            '<button class="btn btn-launch btn-sm" data-launch="' + esc(x.id) + '">▶ 启动</button>' +
            '<button class="btn btn-ghost btn-sm" data-mods="' + esc(x.id) + '" title="管理此游戏的 Mod">MOD</button>' +
            (x.source_url && /trainer\//.test(x.source_url)
              ? '<button class="icon-btn" data-history="' + esc(x.id) + '" title="查看版本历史（打开官网）">↻</button>' : '') +
            '<button class="icon-btn del" data-del="' + esc(x.id) + '" title="从库移除">✕</button>' +
          '</div>' +
          (running ? '<div class="running-flag">最近启动过</div>' : '') +
        '</div>';
    }).join('');

    grid.querySelectorAll('[data-launch]').forEach(function (b) {
      b.addEventListener('click', function () { doLaunch(b.dataset.launch); });
    });
    grid.querySelectorAll('[data-del]').forEach(function (b) {
      b.addEventListener('click', function () { doRemove(b.dataset.del); });
    });
    grid.querySelectorAll('[data-mods]').forEach(function (b) {
      b.addEventListener('click', function () {
        var it = state.library.find(function (x) { return x.id === b.dataset.mods; });
        var gid = it && it.game_id ? it.game_id : b.dataset.mods;
        gotoGameMods(gid);
      });
    });
    grid.querySelectorAll('[data-history]').forEach(function (b) {
      b.addEventListener('click', function () {
        var it = state.library.find(function (x) { return x.id === b.dataset.history; });
        if (it && it.source_url) api.open_url(it.source_url);
      });
    });
  }

  async function doImport(gameId) {
    try {
      var paths = await api.pick_files();
      if (!paths || !paths.length) return;
      toast('正在导入 ' + paths.length + ' 个文件…');
      var results = await api.import_trainer(paths, gameId || '');
      var ok = 0, fail = 0;
      results.forEach(function (r) { if (r.ok) ok++; else fail++; });
      await loadLibrary();
      await loadHub();
      toast('导入完成：成功 ' + ok + ' 个（已归入游戏）' + (fail ? '，失败 ' + fail + ' 个' : ''), ok ? 'success' : 'error');
    } catch (e) { toast('导入失败：' + e, 'error'); }
  }

  async function doLaunch(id) {
    var item = state.library.find(function (x) { return x.id === id; });
    if (state.config.confirm_before_launch) {
      var ok = await ask('启动修改器',
        '<p>即将启动：<strong>' + esc(item ? item.name : '') + '</strong></p>' +
        '<p>请确认：</p><ul><li>游戏已经打开并进入游戏画面</li><li>仅用于单机游戏</li></ul>', '确定启动');
      if (!ok) return;
    }
    try {
      var r = await api.launch_trainer(id);
      if (r.ok) {
        toast(r.elevated ? '已请求管理员权限启动：' + r.name : '已启动：' + r.name, 'success');
        item.last_launch = new Date().toLocaleString('zh-CN', { hour12: false });
        renderLibrary();
        loadHub();  // 同步游戏库里的"最近启动"
      } else toast('启动失败：' + r.error, 'error');
    } catch (e) { toast('启动失败：' + e, 'error'); }
  }

  async function doRemove(id) {
    var item = state.library.find(function (x) { return x.id === id; });
    var ok = await ask('移除修改器',
      '<p>从库中移除「<strong>' + esc(item ? item.name : '') + '</strong>」？</p>' +
      '<p class="muted">仅移除记录，不会删除本地文件。</p>', '确认移除');
    if (!ok) return;
    try {
      var r = await api.remove_trainer(id, false);
      if (r.ok) { toast('已移除', 'success'); loadLibrary(); }
      else toast('移除失败：' + r.error, 'error');
    } catch (e) { toast('移除失败：' + e, 'error'); }
  }

  async function openFolder() {
    try { await api.open_trainer_folder(); } catch (e) { toast('打开失败：' + e, 'error'); }
  }

  // ---------- 在线下载（四态） ----------
  function bindOnline() {
    $('btnSearch').addEventListener('click', doSearch);
    $('onlineQuery').addEventListener('keydown', function (e) { if (e.key === 'Enter') doSearch(); });
    $('pickGameCancel').addEventListener('click', function () {
      if (state._closePickGame) state._closePickGame(null);
    });
  }

  // 选择下载归属的游戏：返回 Promise<{game_id, name}|null>
  // 列出已有游戏下拉；也可新建。默认按官网名智能预选最接近的一个，但必须用户点确认。
  async function pickGame(suggestName) {
    // 确保游戏列表是最新的
    try { await loadHub(); } catch (e) {}
    return new Promise(function (resolve) {
      var games = (state.hub || []).slice();
      $('pickGameBody').innerHTML =
        '<p>下载前请先选择这款修改器要放进哪个游戏。修改器会归入你选的游戏，<b>不会自动生成新游戏</b>。</p>' +
        (suggestName ? '<p>官网名称：<strong>' + esc(suggestName) + '</strong></p>' : '');
      if (!games.length) {
        $('pickGameSelect').innerHTML = '<option value="">（库里还没有游戏，请在下面新建一个）</option>';
        $('pickGameNew').value = suggestName || '';
      } else {
        // 智能预选：名字归一化后包含关系
        var key = (suggestName || '').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
        var best = '';
        games.forEach(function (g) {
          var gn = (g.name || '').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
          if (key && gn && (key.indexOf(gn) >= 0 || gn.indexOf(key) >= 0)) best = g.id;
        });
        $('pickGameSelect').innerHTML = games.map(function (g) {
          return '<option value="' + esc(g.id) + '"' + (g.id === best ? ' selected' : '') + '>' +
            esc(g.name) + '（现有 ' + ((g.trainers || []).length) + ' 修改器）</option>';
        }).join('');
        $('pickGameNew').value = '';
      }
      $('pickGameOverlay').style.display = 'flex';
      $('pickGameOk').onclick = function () {
        var newName = $('pickGameNew').value.trim();
        var picked = $('pickGameSelect').value;
        if (newName) {
          // 新建游戏：先查重，已存在则直接归入
          var exist = games.find(function (g) { return (g.name || '').toLowerCase() === newName.toLowerCase(); });
          if (exist) { state._closePickGame({ game_id: exist.id, name: exist.name, reused: true }); return; }
          api.create_game(newName).then(function (r) {
            if (r && r.ok) state._closePickGame({ game_id: r.game.id, name: r.game.name, created: true });
            else toast('新建游戏失败：' + ((r && r.error) || '未知错误'), 'error');
          }).catch(function (e) { toast('新建游戏失败：' + e, 'error'); });
          return;
        }
        if (!picked) { toast('请选择游戏或输入新游戏名', 'error'); return; }
        var g = games.find(function (x) { return x.id === picked; });
        state._closePickGame({ game_id: picked, name: g ? g.name : '', reused: true });
      };
      state._closePickGame = function (v) {
        $('pickGameOverlay').style.display = 'none';
        $('pickGameOk').onclick = null;
        state._closePickGame = null;
        resolve(v);
      };
    });
  }

  function renderOnlineIdle() {
    var recent = state.config.last_search || '';
    var hot = ['Black Myth Wukong', 'Elden Ring', 'Cyberpunk 2077', 'Sekiro', 'Hollow Knight'];
    $('searchResults').innerHTML =
      '<div class="state-card idle-state">' +
        '<div class="state-icon">⌕</div>' +
        '<div class="state-title">输入游戏英文名开始搜索</div>' +
        '<div class="state-desc">风灵月影官网按英文名索引——中文名往往搜不到，请用英文原名。</div>' +
        (recent ? '<div class="recent-search">最近搜索：<span class="chip-hot" data-q="' + esc(recent) + '">' + esc(recent) + '</span></div>' : '') +
        '<div class="hot-label">热门搜索</div>' +
        '<div class="hot-list">' + hot.map(function (h) {
          return '<span class="chip-hot" data-q="' + esc(h) + '">' + esc(h) + '</span>';
        }).join('') + '</div>' +
      '</div>';
    $('searchResults').querySelectorAll('[data-q]').forEach(function (el) {
      el.addEventListener('click', function () { $('onlineQuery').value = el.dataset.q; doSearch(); });
    });
    $('detailPanel').style.display = 'none';
  }

  function renderOnlineLoading() {
    $('searchResults').innerHTML =
      '<div class="skeleton-list">' +
        '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>' +
      '</div>';
  }

  function renderOnlineError(err) {
    $('searchResults').innerHTML =
      '<div class="state-card error-state">' +
        '<div class="state-icon">!</div>' +
        '<div class="state-title">搜索失败</div>' +
        '<div class="state-desc">' + esc(err || '网络不可用或官网暂时无法访问') + '</div>' +
        '<button class="btn btn-ghost" id="btnRetry">重试</button>' +
      '</div>';
    $('btnRetry').addEventListener('click', doSearch);
  }

  function renderOnlineEmpty(q, r) {
    var tip = (r && r.translated)
      ? '<div class="translated-tip">已尝试把「' + esc(r.hit_cn) + '」转换为 <b class="mono-num">' +
        esc(r.en_term) + '</b>，官网仍无匹配。</div>'
      : '';
    $('searchResults').innerHTML =
      '<div class="state-card empty-result-state">' +
        '<div class="state-icon">∅</div>' +
        '<div class="state-title">没有找到「' + esc(q) + '」</div>' +
        '<div class="state-desc">试试游戏的<strong>英文原名</strong>，或更短的关键词。<br>例如「黑神话：悟空」→ Black Myth Wukong。</div>' +
        tip +
        '<button class="btn btn-ghost" id="btnOpenSite">去官网手动搜索</button>' +
      '</div>';
    $('btnOpenSite').addEventListener('click', function () {
      api.open_url('https://flingtrainer.com/?s=' + encodeURIComponent(q));
    });
  }

  async function doSearch() {
    var q = $('onlineQuery').value.trim();
    if (!q) { toast('请输入游戏名称'); return; }
    renderOnlineLoading();
    $('detailPanel').style.display = 'none';
    try {
      var r = await api.search_games(q);
      if (!r.ok) { renderOnlineError(r.error); return; }
      if (!r.items.length) { renderOnlineEmpty(q, r); return; }
      var tip = r.translated
        ? '<div class="translated-tip">已把「' + esc(r.hit_cn) + '」自动转换为 <b class="mono-num">' +
          esc(r.en_term) + '</b> 搜索 · 官网按英文索引</div>'
        : '';
      $('searchResults').innerHTML = tip + '<div class="result-list">' + r.items.map(function (it) {
        return '<div class="result-item" data-url="' + esc(it.url) + '">' +
          '<span class="result-title">' + esc(it.title) + '</span>' +
          '<span class="result-arrow">›</span></div>';
      }).join('') + '</div><div class="result-hint">共 ' + r.items.length + ' 个结果，点击查看详情与下载版本</div>';
      $('searchResults').querySelectorAll('.result-item').forEach(function (el) {
        el.addEventListener('click', function () { doDetail(el.dataset.url); });
      });
    } catch (e) { renderOnlineError(String(e)); }
  }

  async function doDetail(url) {
    $('detailPanel').style.display = 'block';
    $('detailTitle').textContent = '加载中…';
    $('detailMeta').innerHTML = '';
    $('downloadList').innerHTML = '';
    try {
      var d = await api.get_game_detail(url);
      if (!d.ok) { toast(d.error, 'error'); $('detailPanel').style.display = 'none'; return; }
      state.detail = d;
      $('detailTitle').textContent = d.title;
      $('detailMeta').innerHTML =
        '<span>版本 <b class="mono-num">' + esc(d.version || '—') + '</b></span>' +
        '<span>更新 <b class="mono-num">' + esc(d.updated || '—') + '</b></span>' +
        '<span>功能 <b class="mono-num">' + (d.options || '—') + ' 项</b></span>';
      $('detailSource').href = d.url;
      if (!d.downloads.length) {
        $('downloadList').innerHTML = '<div class="state-card" style="padding:24px">该页面未解析到下载链接，请点「在官网打开」手动下载。</div>';
        return;
      }
      $('downloadList').innerHTML = d.downloads.map(function (dl, i) {
        var isAuto = dl.type === '自动更新版';
        return '<div class="download-row">' +
          '<span class="dl-type ' + (isAuto ? 'auto' : 'standalone') + '">' + esc(dl.type) + '</span>' +
          '<div class="dl-info">' +
            '<div class="dl-name" title="' + esc(dl.filename) + '">' + esc(dl.filename) + '</div>' +
            '<div class="dl-sub mono-num">' + esc(dl.date) + ' · ' + esc(dl.size) + ' · ' + esc(dl.downloads) + ' 次下载</div>' +
          '</div>' +
          '<button class="btn btn-primary btn-sm" data-dl="' + i + '">下载修改器</button>' +
        '</div>';
      }).join('');
      $('downloadList').querySelectorAll('[data-dl]').forEach(function (b) {
        b.addEventListener('click', function () {
          var dl = d.downloads[parseInt(b.dataset.dl, 10)];
          doDownload(dl, d.title, d.options, d.version, d.url);
        });
      });
    } catch (e) { toast('获取详情失败：' + e, 'error'); }
  }

  function pollProgress(getState, overlayId, fillId, pctId, nameId) {
    var timer = setInterval(async function () {
      try {
        var s = await api[getState]();
        $(fillId).style.width = s.percent + '%';
        $(pctId).textContent = s.percent + '%';
      } catch (e) {}
    }, 200);
    return timer;
  }

  async function doDownload(dl, gameName, options, version, detailUrl) {
    // 先选归属游戏：不传 game_id 后端就会凭空新建游戏，这是重复的根源
    var pick = await pickGame(gameName);
    if (!pick) return;  // 用户取消
    $('downloadOverlay').style.display = 'flex';
    $('progressTitle').textContent = '正在下载修改器…';
    $('progressFilename').textContent = dl.filename;
    $('progressFill').style.width = '0%';
    $('progressPct').textContent = '0%';
    var timer = pollProgress('get_download_state', 'downloadOverlay', 'progressFill', 'progressPct');
    try {
      var r = await api.download_trainer(dl.link, dl.filename, gameName,
        options || 0, version || '', detailUrl || '', pick.game_id);
      clearInterval(timer); $('downloadOverlay').style.display = 'none';
      if (r.ok) {
        toast('下载完成，已归入「' + pick.name + '」', 'success');
        loadLibrary(); loadHub(); loadAllMods();
      } else toast('下载失败：' + r.error, 'error');
    } catch (e) {
      clearInterval(timer); $('downloadOverlay').style.display = 'none';
      toast('下载失败：' + e, 'error');
    }
  }

  // ---------- 快捷键说明 ----------
  var HOTKEY_GROUPS = [
    { title: '基础功能（小键盘）', rows: [
      ['Num 1', '无敌 / 忽略伤害'], ['Num 2', '无限生命'], ['Num 3', '无限法力'],
      ['Num 4', '无限体力'], ['Num 5', '无限专注'], ['Num 0', '一击必杀'],
      ['Num .', '无限灵魂能量'], ['Num +', '最大暴击率'], ['Num -', '最大韧性']
    ]},
    { title: '资源与数值', rows: [
      ['Ctrl+Num /', '掉落倍率'], ['Ctrl+Num *', '经验倍率'], ['Ctrl+Num -', '100% 掉落率'],
      ['Ctrl+Num 1', '超级伤害/一击必杀'], ['Ctrl+Num 2', '伤害倍率'], ['Ctrl+Num 3', '防御倍率'],
      ['Ctrl+Num 4', '体力消耗倍率'], ['Ctrl+Num 5', '游戏速度']
    ]},
    { title: '编辑类（Alt / Shift）', rows: [
      ['Alt+Num 1', '编辑货币/意志'], ['Alt+Num 2', '编辑点击物品数量'], ['Alt+Num 3', '增加经验'],
      ['Alt+Num 4', '编辑技能点'], ['Alt+Num 5', '编辑玩家速度'],
      ['Shift+F1', '编辑最大生命'], ['Shift+F2', '编辑最大法力'], ['Shift+F3', '编辑最大体力'],
      ['Shift+F4', '编辑攻击力'], ['Shift+F5', '编辑防御力'], ['Shift+F6', '编辑体力恢复'],
      ['Shift+F7', '编辑暴击率'], ['Shift+F8', '编辑暴击伤害'], ['Shift+F9', '编辑伤害加成'], ['Shift+F10', '编辑伤害减免']
    ]},
    { title: '通用控制键', rows: [
      ['Home', '展开/收起全部选项'], ['End', '关闭全部功能'], ['Delete', '关闭所有已激活项'],
      ['F1', '显示/隐藏功能列表'], ['数字键', '开关对应功能']
    ]}
  ];

  function bindHotkeys() {
    $('hkSearch').addEventListener('input', renderHotkeys);
    $('btnHkToggle').addEventListener('click', function () {
      var anyOpen = HOTKEY_GROUPS.some(function (g, i) { return !state.hkCollapsed[i]; });
      HOTKEY_GROUPS.forEach(function (g, i) { state.hkCollapsed[i] = anyOpen; });
      $('btnHkToggle').textContent = anyOpen ? '全部展开' : '全部收起';
      renderHotkeys();
    });
    $('btnHkPrint').addEventListener('click', function () { window.print(); });
    // 默认只展开第一组
    HOTKEY_GROUPS.forEach(function (g, i) { state.hkCollapsed[i] = i !== 0; });
  }

  function renderHotkeys() {
    var kw = ($('hkSearch').value || '').trim().toLowerCase();
    var anyOpen = HOTKEY_GROUPS.some(function (g, i) { return !state.hkCollapsed[i]; });
    $('btnHkToggle').textContent = anyOpen ? '全部收起' : '全部展开';
    var html = HOTKEY_GROUPS.map(function (g, gi) {
      var rows = g.rows.filter(function (r) {
        return !kw || r[0].toLowerCase().indexOf(kw) >= 0 || r[1].toLowerCase().indexOf(kw) >= 0;
      });
      if (kw && !rows.length) return '';
      var collapsed = state.hkCollapsed[gi] && !kw;
      return '' +
        '<div class="hotkey-card">' +
          '<div class="hotkey-card-title" data-group="' + gi + '">' +
            '<span class="caret">' + (collapsed ? '▸' : '▾') + '</span>' + esc(g.title) +
            '<span class="hk-count">' + rows.length + '</span>' +
          '</div>' +
          (collapsed ? '' : '<div class="hotkey-rows">' + rows.map(function (r) {
            return '<div class="hotkey-row"><kbd class="hk">' + esc(r[0]) + '</kbd><span class="desc">' + esc(r[1]) + '</span></div>';
          }).join('') + '</div>') +
        '</div>';
    }).join('');
    $('hotkeyGrid').innerHTML = html || '<div class="empty-state" style="grid-column:1/-1"><div class="empty-title">没有匹配的键位</div></div>';
    $('hotkeyGrid').querySelectorAll('[data-group]').forEach(function (h) {
      h.addEventListener('click', function () {
        var i = parseInt(h.dataset.group, 10);
        state.hkCollapsed[i] = !state.hkCollapsed[i];
        renderHotkeys();
      });
    });
  }

  // ---------- 设置 ----------
  function bindSettings() {
    $('settingConfirm').addEventListener('change', function () {
      state.config.confirm_before_launch = this.checked;
      api.save_config(state.config);
    });
    $('btnCheckUpdate').addEventListener('click', doCheckUpdate);
    $('btnHash').addEventListener('click', doHash);
  }

  async function loadConfig() {
    try {
      state.config = await api.get_config();
      $('settingDir').value = state.config.trainer_dir || '';
      $('settingConfirm').checked = state.config.confirm_before_launch !== false;
      if (state.config.last_update_check) {
        $('updateResult').innerHTML = '上次检查：<span class="mono-num">' + esc(state.config.last_update_check) + '</span>。根据官网 Last Updated 日期比对。';
      }
      renderOnlineIdle();
    } catch (e) {}
  }

  async function doCheckUpdate() {
    $('updateResult').textContent = '正在检测…';
    try {
      var r = await api.check_updates();
      state.updates = r.has_update || [];
      state.library = r.library || state.library;
      state.config = await api.get_config();
      $('updateResult').innerHTML = (state.updates.length
        ? '<span style="color:var(--yellow)">发现 ' + state.updates.length + ' 个可能有新版，已在库中标记。</span>'
        : '<span style="color:var(--green)">✓ 本地修改器均为最新（或无需检测）。</span>') +
        '<br><span class="muted mono-num">上次检查：' + esc(state.config.last_update_check || '') + '</span>';
      renderLibrary();
    } catch (e) { $('updateResult').textContent = '检测失败：' + e; }
  }

  function fillHashSelect() {
    var sel = $('hashSelect');
    var cur = sel.value;
    sel.innerHTML = state.library.map(function (x) {
      return '<option value="' + esc(x.id) + '">' + esc(x.name) + '</option>';
    }).join('');
    if (cur) sel.value = cur;
  }

  async function doHash() {
    var id = $('hashSelect').value;
    var item = state.library.find(function (x) { return x.id === id; });
    if (!item) { toast('请先选择修改器'); return; }
    $('hashResult').style.display = 'block';
    $('hashResult').textContent = '正在计算 ' + item.name + ' 的 SHA-256…';
    try {
      var h = await api.file_sha256(item.path);
      $('hashResult').innerHTML = '<div class="hash-label">' + esc(item.name) + ' · SHA-256</div>' +
        '<code class="hash-value">' + esc(h.hash || h.error || '计算失败') + '</code>';
    } catch (e) { $('hashResult').textContent = '计算失败：' + e; }
  }

  // ---------- 首次启动确认 ----------
  async function maybeShowSafety() {
    try {
      // 直接从后端读最新配置，不依赖 loadConfig 的异步加载时序
      var cfg = await api.get_config();
      state.config = cfg;
      if (!cfg.safety_acknowledged) {
        $('safetyOverlay').style.display = 'flex';
      }
    } catch (e) {}
  }
  function bindConfirm() {
    $('safetyOk').addEventListener('click', async function () {
      if ($('safetyDontShow').checked) {
        try {
          // 基于最新配置落盘，避免用旧 state 覆盖其它设置
          var cfg = await api.get_config();
          cfg.safety_acknowledged = true;
          await api.save_config(cfg);
          state.config = cfg;
        } catch (e) {}
      }
      $('safetyOverlay').style.display = 'none';
    });
  }

  // ---------- 游戏库（三级下钻：游戏 → 修改器/Mod → 详情） ----------
  function bindHub() {
    $('hubQuery').addEventListener('input', function () {
      state.hubQuery = this.value.trim().toLowerCase();
      renderHubList();
    });
    $('hubBackList').addEventListener('click', backToHubList);
    $('hubBackOptions').addEventListener('click', function () { showHubOptions(); });
    $('hubRename').addEventListener('click', doRenameGame);
    $('hubImport').addEventListener('click', function () { doImport(state.hubGameId); });
    $('hubAdd').addEventListener('click', doAddGame);
    $('hubScan').addEventListener('click', openScan);
    bindScan();
  }

  function backToHubList() {
    state.hubGameId = null;
    state.hubDetailOpt = null;
    showHubList();
    renderHubList();
  }

  async function loadHub() {
    try {
      var r = await api.get_game_hub();
      state.hub = r.items || [];
      $('libCount').textContent = state.hub.length;
      if (state.hubGameId && !state.hub.some(function (g) { return g.id === state.hubGameId; })) {
        state.hubGameId = null;
      }
      if (state.hubGameId) {
        if (state.hubDetailOpt && $('hubDetail').style.display !== 'none') openHubDetail(state.hubDetailOpt, true);
        else showHubOptions();
      } else { showHubList(); }
      renderHubList();
    } catch (e) { toast('加载游戏库失败：' + e, 'error'); }
  }

  function showHubList() {
    $('hubList').style.display = '';
    $('hubGame').style.display = 'none';
    $('hubDetail').style.display = 'none';
    $('hubCrumb').innerHTML = '';
  }
  function showHubOptions() {
    state.hubDetailOpt = null;
    $('hubList').style.display = 'none';
    $('hubGame').style.display = '';
    $('hubDetail').style.display = 'none';
    renderHubOptions();
  }
  function showHubDetail() {
    $('hubList').style.display = 'none';
    $('hubGame').style.display = 'none';
    $('hubDetail').style.display = '';
  }
  function hubGameById(id) {
    return state.hub.find(function (g) { return g.id === id; });
  }

  function renderHubList() {
    var q = state.hubQuery || '';
    var list = state.hub.filter(function (g) {
      return !q || (g.name || '').toLowerCase().indexOf(q) >= 0;
    });
    var grid = $('hubGrid'), empty = $('hubEmpty');
    if (!state.hub.length) {
      grid.innerHTML = '';
      empty.innerHTML =
        '<div class="state-card idle-state"><div class="state-icon">▦</div>' +
        '<div class="state-title">库里还没有游戏</div>' +
        '<div class="state-desc">点右上「＋ 添加游戏」手动建立，或「扫描游戏」从本地目录导入。修改器和 Mod 都会放进游戏里，不会重复生成游戏。</div>' +
        '<div class="empty-actions"><button class="btn btn-primary" id="hubAddEmpty">＋ 添加游戏</button>' +
        '<button class="btn btn-ghost" id="hubScanEmpty">扫描游戏</button></div></div>';
      $('hubAddEmpty').addEventListener('click', doAddGame);
      $('hubScanEmpty').addEventListener('click', openScan);
      return;
    }
    empty.innerHTML = '';
    if (!list.length) {
      grid.innerHTML = '<div class="state-card empty-result-state" style="grid-column:1/-1"><div class="state-icon">∅</div><div class="state-title">没有匹配的游戏</div><div class="state-desc">换个关键词试试。</div></div>';
      return;
    }
    grid.innerHTML = list.map(function (g) {
      var tN = (g.trainers || []).length, modN = (g.mods || []).length;
      return '<div class="hub-card" data-game="' + esc(g.id) + '">' +
        '<div class="hub-card-top">' +
          '<div class="hub-card-icon"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 12h4M8 10v4M15 11h.01M18 13h.01"/><rect x="2" y="7" width="20" height="10" rx="4"/></svg></div>' +
          '<div class="hub-card-main">' +
            '<div class="hub-card-name">' + esc(g.name) + '</div>' +
            '<div class="hub-card-date mono-num">◷ 添加于 ' + esc(g.added || '—') + '</div>' +
          '</div>' +
          '<span class="hub-card-arrow">›</span>' +
        '</div>' +
        '<div class="hub-card-stats">' +
          '<span class="hub-stat"><b>' + tN + '</b> 修改器</span>' +
          '<span class="hub-stat"><b>' + modN + '</b> Mod</span>' +
        '</div>' +
        '<div class="hub-card-actions">' +
          (g.exe_path
            ? '<button class="btn btn-launch btn-sm" data-launchgame="' + esc(g.id) + '">▶ 启动游戏</button>'
            : '<button class="btn btn-ghost btn-sm" data-setexe="' + esc(g.id) + '">设置游戏路径</button>') +
          '<button class="btn btn-ghost btn-sm" data-entergame="' + esc(g.id) + '">查看内容</button>' +
        '</div>' +
      '</div>';
    }).join('');
    grid.querySelectorAll('[data-entergame]').forEach(function (c) {
      c.addEventListener('click', function (e) { e.stopPropagation(); openHubGame(c.dataset.entergame); });
    });
    grid.querySelectorAll('[data-launchgame]').forEach(function (c) {
      c.addEventListener('click', function (e) { e.stopPropagation(); doLaunchGame(c.dataset.launchgame); });
    });
    grid.querySelectorAll('[data-setexe]').forEach(function (c) {
      c.addEventListener('click', function (e) { e.stopPropagation(); doSetExe(c.dataset.setexe); });
    });
    grid.querySelectorAll('[data-game]').forEach(function (c) {
      c.addEventListener('click', function () { openHubGame(c.dataset.game); });
    });
  }

  function openHubGame(id) {
    state.hubGameId = id;
    var g = hubGameById(id);
    showHubOptions();
    $('hubCrumb').innerHTML = '<span class="crumb-link" id="crumbHome">游戏库</span><span class="crumb-sep">›</span><span class="crumb-cur">' + esc(g ? g.name : '') + '</span>';
    $('crumbHome').addEventListener('click', backToHubList);
  }

  function renderHubOptions() {
    var g = hubGameById(state.hubGameId);
    if (!g) { showHubList(); return; }
    $('hubGameName').textContent = g.name;
    $('hubGameVer').textContent = '添加于 ' + (g.added || '—');
    var tN = (g.trainers || []).length, modN = (g.mods || []).length;
    $('hubGameActions').innerHTML =
      (g.exe_path
        ? '<button class="btn btn-launch" id="hubLaunchGame">▶ 启动游戏</button>'
        : '<button class="btn btn-ghost" id="hubSetExe">设置游戏本体路径</button>') +
      '<button class="btn btn-ghost" id="hubRemoveGame">删除游戏</button>';
    var lg = $('hubLaunchGame'); if (lg) lg.addEventListener('click', function () { doLaunchGame(g.id); });
    var se = $('hubSetExe'); if (se) se.addEventListener('click', function () { doSetExe(g.id); });
    $('hubRemoveGame').addEventListener('click', function () { doRemoveGame(g); });
    $('hubOptions').innerHTML =
      '<div class="hub-option" data-opt="trainer">' +
        '<div class="hub-option-icon trainer"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3v6a6 6 0 0012 0V3M4 3h4M16 3h4M12 15v6M9 21h6"/></svg></div>' +
        '<div class="hub-option-info"><div class="hub-option-title">修改器</div><div class="hub-option-desc">' +
          (tN ? tN + ' 个修改器 · ' + esc((g.trainers[0] || {}).version || '本地 exe') : '暂无，点此添加') + '</div></div>' +
        '<span class="hub-option-arrow">›</span></div>' +
      '<div class="hub-option" data-opt="mods">' +
        '<div class="hub-option-icon mod"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M10 3h4v4h4a1 1 0 011 1v4h-3v4h-4v-4H8v4H4v-4a1 1 0 011-1h4V8H6a1 1 0 01-1-1V4a1 1 0 011-1h4z"/></svg></div>' +
        '<div class="hub-option-info"><div class="hub-option-title">Mod</div><div class="hub-option-desc">' + (modN ? modN + ' 个已关联补丁' : '暂无，点此添加') + '</div></div>' +
        '<span class="hub-option-arrow">›</span></div>';
    $('hubOptions').querySelectorAll('[data-opt]').forEach(function (c) {
      c.addEventListener('click', function () { openHubDetail(c.dataset.opt); });
    });
  }

  function openHubDetail(opt, silent) {
    var g = hubGameById(state.hubGameId);
    if (!g) return;
    state.hubDetailOpt = opt;
    showHubDetail();
    $('hubDetailTitle').textContent = g.name + ' · ' + (opt === 'trainer' ? '修改器' : 'Mod');
    $('hubCrumb').innerHTML = '<span class="crumb-link" id="crumbHome">游戏库</span><span class="crumb-sep">›</span>' +
      '<span class="crumb-link" id="crumbGame">' + esc(g.name) + '</span><span class="crumb-sep">›</span><span class="crumb-cur">' +
      (opt === 'trainer' ? '修改器' : 'Mod') + '</span>';
    $('crumbHome').addEventListener('click', backToHubList);
    $('crumbGame').addEventListener('click', function () { showHubOptions(); });
    if (opt === 'trainer') renderHubTrainer(g);
    else renderHubMods(g);
  }

  function renderHubTrainer(g) {
    var trainers = g.trainers || [];
    var html = '';
    if (!trainers.length) {
      html = '<div class="state-card idle-state"><div class="state-icon">▣</div>' +
        '<div class="state-title">还没有修改器</div>' +
        '<div class="state-desc">导入本地修改器，或从在线下载一个——都会归到这个游戏下，不会重复生成游戏。</div>' +
        '<button class="btn btn-primary" id="hubAddTrainer">＋ 导入修改器</button></div>';
    } else {
      html = '<div class="hub-mods-sub">该游戏下有 ' + trainers.length + ' 个修改器</div>' +
        trainers.map(function (t) {
          var updated = state.updates.indexOf(t.id) >= 0;
          return '<div class="hub-trainer-card">' +
            (updated ? '<div class="update-flag">有新版</div>' : '') +
            '<div class="hub-trainer-head"><div class="card-icon">▣</div><div>' +
              '<div class="hub-trainer-title">' + esc(t.name) + '</div>' +
              '<div class="card-version">' + esc(t.version || '—') + '</div></div></div>' +
            '<div class="card-detail">' +
              '<div class="detail-line"><span class="dl-k">EXE 文件</span><span class="dl-v mono" title="' + esc(t.filename) + '">' + esc(t.filename || '—') + '</span></div>' +
              (t.options ? '<div class="detail-line"><span class="dl-k">功能项</span><span class="dl-v">' + t.options + ' 项</span></div>' : '') +
              '<div class="detail-line"><span class="dl-k">添加时间</span><span class="dl-v mono-num">' + esc(t.added || '—') + '</span></div>' +
              '<div class="detail-line"><span class="dl-k">最近启动</span><span class="dl-v">' + esc(t.last_launch || '从未') + '</span></div>' +
              '<div class="detail-line"><span class="dl-k">大小</span><span class="dl-v mono-num">' + fmtSize(t.size) + '</span></div>' +
              (t.source_url ? '<div class="detail-line"><span class="dl-k">来源</span><a class="dl-v link" href="' + esc(t.source_url) + '" target="_blank">官网页面 ↗</a></div>' : '') +
            '</div>' +
            '<div class="hub-trainer-actions">' +
              '<button class="btn btn-launch" data-hlaunch="' + esc(t.id) + '">▶ 启动修改器</button>' +
              '<button class="btn btn-ghost" data-hdel="' + esc(t.id) + '">从库移除</button>' +
            '</div></div>';
        }).join('') +
        '<button class="btn btn-primary hub-mods-add" id="hubAddTrainer">＋ 导入更多修改器</button>' +
        '<div class="hub-trainer-tip">提示：先打开游戏进入画面，再启动修改器。仅限单机。</div>';
    }
    $('hubDetailBody').innerHTML = html;
    var at = $('hubAddTrainer'); if (at) at.addEventListener('click', function () { doImport(g.id); });
    $('hubDetailBody').querySelectorAll('[data-hlaunch]').forEach(function (b) {
      b.addEventListener('click', function () { doLaunch(b.dataset.hlaunch); });
    });
    $('hubDetailBody').querySelectorAll('[data-hdel]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var ok = await ask('移除修改器',
          '<p>从库中移除这个修改器？</p><p class="muted">仅移除记录，不删除本地文件。该游戏和它的 Mod 会保留。</p>', '确认移除');
        if (!ok) return;
        var r = await api.remove_trainer(b.dataset.hdel, false);
        if (r.ok) { toast('已移除', 'success'); loadHub(); openHubDetail('trainer', true); }
        else toast('移除失败：' + r.error, 'error');
      });
    });
  }

  // ---- 游戏管理：添加 / 重命名 / 设置本体 / 启动 / 删除 ----
  async function doAddGame() {
    var v = await prompt('添加游戏',
      '<p>手动建立一个游戏，之后把修改器和 Mod 放进它里面。</p>',
      [{ key: 'name', label: '游戏名称', placeholder: '如 黑神话：悟空' }], '添加');
    if (!v || !v.name) { if (v) toast('请输入游戏名称'); return; }
    try {
      var r = await api.create_game(v.name, '');
      if (r.ok) { toast('已添加游戏：' + r.game.name, 'success'); loadHub(); }
      else toast('添加失败：' + r.error, 'error');
    } catch (e) { toast('添加失败：' + e, 'error'); }
  }

  async function doRenameGame() {
    var g = hubGameById(state.hubGameId);
    if (!g) return;
    var v = await prompt('重命名游戏', '<p>给游戏换个名字（不影响已关联的修改器和 Mod）。</p>',
      [{ key: 'name', label: '新名称', value: g.name }], '保存');
    if (!v || !v.name) { if (v) toast('名称不能为空'); return; }
    try {
      var r = await api.rename_game(g.id, v.name);
      if (r.ok) { toast('已重命名', 'success'); loadHub(); }
      else toast('重命名失败：' + r.error, 'error');
    } catch (e) { toast('重命名失败：' + e, 'error'); }
  }

  // 重命名 Mod 的显示名：不改实际文件，不影响已安装到游戏里的 Mod
  async function doRenameMod(gameId, modId, oldName, after) {
    var v = await prompt('重命名 Mod',
      '<p>给这个 Mod 换个方便识别的名字。</p>' +
      '<p class="muted">只改工具里显示的名称，不会重命名实际文件，也不影响已安装到游戏里的 Mod。</p>',
      [{ key: 'name', label: '新名称', value: oldName || '' }], '保存');
    if (!v) return;
    if (!v.name) { toast('名称不能为空'); return; }
    try {
      var r = await api.rename_mod(gameId, modId, v.name);
      if (!r.ok) { toast('重命名失败：' + r.error, 'error'); return; }
      toast('已重命名为：' + r.name, 'success');
      if (after) await after();
    } catch (e) { toast('重命名失败：' + e, 'error'); }
  }

  async function doSetExe(id) {
    id = id || state.hubGameId;
    try {
      var p = await api.pick_game_exe();
      if (!p) return;
      var r = await api.set_game_exe(id, p);
      if (r.ok) { toast('游戏路径已设置：' + p.split(/[\\/]/).pop(), 'success'); loadHub(); }
      else toast('设置失败：' + r.error, 'error');
    } catch (e) { toast('设置失败：' + e, 'error'); }
  }

  async function doLaunchGame(id) {
    id = id || state.hubGameId;
    var g = hubGameById(id);
    if (!g) return;
    if (!g.exe_path) { await doSetExe(id); return; }
    try {
      var r = await api.launch_game(id);
      if (r.ok) {
        var extra = (r.args && r.args.length) ? '（已带 ' + r.args.join(' ') + ' 加载 Mod）' : '';
        toast((r.elevated ? '已请求管理员权限启动游戏：' : '已启动游戏：') + r.name + extra, 'success');
        loadHub();
      }
      else toast('启动失败：' + r.error, 'error');
    } catch (e) { toast('启动失败：' + e, 'error'); }
  }

  async function doRemoveGame(g) {
    var ok = await ask('删除游戏',
      '<p>删除「<strong>' + esc(g.name) + '</strong>」？</p>' +
      '<p class="muted">会同时移除它下面的 ' + (g.trainers || []).length + ' 个修改器记录和 ' +
      (g.mods || []).length + ' 个 Mod 记录，但<strong>本地文件不会被删除</strong>。</p>', '确认删除');
    if (!ok) return;
    try {
      var r = await api.remove_game(g.id);
      if (r.ok) { toast('已删除游戏', 'success'); backToHubList(); loadHub(); }
      else toast('删除失败：' + r.error, 'error');
    } catch (e) { toast('删除失败：' + e, 'error'); }
  }

  // ---- 扫描本地游戏 ----
  function bindScan() {
    $('scanClose').addEventListener('click', function () { $('scanOverlay').style.display = 'none'; });
    $('scanPick').addEventListener('click', doScanPick);
    $('scanAdd').addEventListener('click', doScanAdd);
  }
  function openScan() {
    state.scanCandidates = [];
    state.scanChecked = {};
    state.scanFolder = '';
    $('scanPath').textContent = '尚未选择';
    $('scanList').innerHTML = '<div class="mod-empty">点上方「选择游戏目录」开始扫描。</div>';
    $('scanCount').textContent = '0';
    $('scanOverlay').style.display = 'flex';
  }
  async function doScanPick() {
    try {
      var folder = await api.pick_folder();
      if (!folder) return;
      state.scanFolder = folder;
      $('scanPath').textContent = folder;
      $('scanList').innerHTML = '<div class="mod-empty">扫描中…</div>';
      var r = await api.scan_directory(folder);
      if (!r.ok) { toast('扫描失败：' + r.error, 'error'); $('scanList').innerHTML = '<div class="mod-empty">扫描失败。</div>'; return; }
      state.scanCandidates = r.items || [];
      state.scanChecked = {};
      state.scanCandidates.forEach(function (c, i) { state.scanChecked[i] = true; });
      renderScanList();
    } catch (e) { toast('扫描失败：' + e, 'error'); }
  }
  function renderScanList() {
    var items = state.scanCandidates;
    $('scanCount').textContent = items.length;
    if (!items.length) {
      $('scanList').innerHTML = '<div class="mod-empty">该目录下未识别到游戏本体 exe。可换个目录，或用「＋ 添加游戏」手动添加。</div>';
      return;
    }
    $('scanList').innerHTML = items.map(function (c, i) {
      return '<label class="scan-item">' +
        '<input type="checkbox" data-i="' + i + '" ' + (state.scanChecked[i] ? 'checked' : '') + '>' +
        '<span class="scan-item-main"><span class="scan-item-name">' + esc(c.name) + '</span>' +
        '<span class="scan-item-path mono" title="' + esc(c.exe_path) + '">' + esc(c.exe_path) + '</span></span>' +
        '<span class="scan-item-size mono-num">' + fmtSize(c.size) + '</span></label>';
    }).join('');
    $('scanList').querySelectorAll('input[data-i]').forEach(function (c) {
      c.addEventListener('change', function () { state.scanChecked[c.dataset.i] = c.checked; });
    });
  }
  async function doScanAdd() {
    var picked = state.scanCandidates.filter(function (c, i) { return state.scanChecked[i]; });
    if (!picked.length) { toast('请先勾选要添加的游戏'); return; }
    var added = 0, skipped = 0;
    for (var i = 0; i < picked.length; i++) {
      try {
        var r = await api.create_game(picked[i].name, picked[i].exe_path);
        if (r.ok) added++; else skipped++;
      } catch (e) { skipped++; }
    }
    $('scanOverlay').style.display = 'none';
    toast('扫描添加完成：' + added + ' 个游戏' + (skipped ? '，跳过 ' + skipped + ' 个（可能重名）' : ''), added ? 'success' : 'error');
    loadHub();
  }

  function renderHubMods(g) {
    var mods = g.mods || [];
    var body = '<div class="mod-install-dir hub-install-dir" id="hubModDir"></div>';
    if (!mods.length) {
      body += '<div class="state-card idle-state"><div class="state-icon">⊞</div>' +
        '<div class="state-title">还没有 Mod</div>' +
        '<div class="state-desc">从 mod 站点下载补丁后，添加下载直链或导入本地文件，关联到这个游戏。</div>' +
        '<button class="btn btn-primary" data-hmodmanage="1">添加第一个 Mod</button></div>';
    } else {
      body += '<div class="hub-mods-sub">已关联 ' + mods.length + ' 个 Mod</div>' +
        '<div class="hub-mod-list">' + mods.map(function (m) {
          var isLink = m.source === 'link';
          var installed = !!(m.install_names && m.install_names.length);
          return '<div class="hub-mod-item">' +
            '<div class="hub-mod-head"><span class="mod-item-name">' + esc(m.name) + '</span>' +
            '<span class="mod-source-tag">' + (isLink ? '链接' : '文件') + '</span>' +
            '<span class="mod-state-tag ' + (installed ? 'on' : 'off') + '">' + (installed ? '已安装' : '未安装') + '</span></div>' +
            '<div class="mod-added mono-num">◷ 添加于 ' + esc(m.added || '—') + '</div>' +
            (m.note ? '<div class="mod-note">' + esc(m.note) + '</div>' : '') +
            (m.url ? '<a class="mod-url link" href="' + esc(m.url) + '" target="_blank">' + esc(m.url.slice(0, 70)) + '…</a>' : '') +
            (m.path ? '<div class="mod-path mono" title="' + esc(m.path) + '">' + esc(m.path) + '</div>' : '') +
            (installed ? '<div class="mod-path mono">游戏内：' + esc((m.install_names || []).join('、')) + '</div>' : '') +
            '<div class="mod-item-actions">' +
              (!isLink && m.path ? (installed
                ? '<button class="btn btn-ghost btn-sm" data-hmunins="' + esc(m.id) + '">从游戏卸载</button>'
                : '<button class="btn btn-primary btn-sm" data-hmins="' + esc(m.id) + '">安装到游戏</button>') : '') +
              (m.url ? '<button class="btn btn-ghost btn-sm" data-hmopen="' + esc(m.id) + '">打开链接</button>' : '') +
              (m.path ? '<button class="btn btn-ghost btn-sm" data-hmpath="' + esc(m.id) + '">打开目录</button>' : '') +
              '<button class="btn btn-ghost btn-sm" data-hmrename="' + esc(m.id) + '">重命名</button>' +
              '<button class="btn btn-danger btn-sm" data-hmdel="' + esc(m.id) + '">移除</button>' +
            '</div></div>';
        }).join('') + '</div>';
    }
    body += '<button class="btn btn-primary hub-mods-add" data-hmodmanage="1">＋ 添加 Mod</button>' +
      '<button class="btn btn-ghost btn-sm hub-mods-clean" id="hubCleanOrphan">清理残留备份</button>';
    $('hubDetailBody').innerHTML = body;
    renderModDirBox($('hubModDir'), g.id);

    var cleanBtn = $('hubCleanOrphan');
    if (cleanBtn) cleanBtn.addEventListener('click', async function () {
      var ok = await ask('清理残留备份',
        '<p>删除工具内<strong>已无 Mod 记录引用</strong>的备份文件（例如删掉 Mod 记录后留下的副本）。</p>' +
        '<p class="muted">只清理工具自己的备份目录，不碰游戏里的文件；仍在使用的 Mod 不会被删。</p>', '开始清理');
      if (!ok) return;
      try {
        var r = await api.cleanup_orphan_backups(g.id);
        toast(r.ok ? ('已清理 ' + ((r.removed || []).length) + ' 个残留备份') : ('清理失败：' + r.error), r.ok ? 'success' : 'error');
        loadHub();
      } catch (e) { toast('清理失败：' + e, 'error'); }
    });
    $('hubDetailBody').querySelectorAll('[data-hmodmanage]').forEach(function (b) {
      b.addEventListener('click', function () { openMods(g.id); });
    });
    $('hubDetailBody').querySelectorAll('[data-hmopen]').forEach(function (b) {
      b.addEventListener('click', function () {
        var m = mods.find(function (x) { return x.id === b.dataset.hmopen; });
        if (m && m.url) api.open_url(m.url);
      });
    });
    $('hubDetailBody').querySelectorAll('[data-hmpath]').forEach(function (b) {
      b.addEventListener('click', async function () {
        await api.open_mod_path(g.id, b.dataset.hmpath);
      });
    });
    $('hubDetailBody').querySelectorAll('[data-hmrename]').forEach(function (b) {
      b.addEventListener('click', function () {
        var m = mods.find(function (x) { return x.id === b.dataset.hmrename; });
        if (m) doRenameMod(g.id, m.id, m.name, function () { return loadHub(); });
      });
    });
    $('hubDetailBody').querySelectorAll('[data-hmins]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var r = await api.install_mod(g.id, b.dataset.hmins);
        toast(r.ok ? '已安装到游戏目录，重启游戏生效' : ('安装失败：' + r.error), r.ok ? 'success' : 'error');
        await loadHub();
      });
    });
    $('hubDetailBody').querySelectorAll('[data-hmunins]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var r = await api.uninstall_mod(g.id, b.dataset.hmunins);
        toast(r.ok ? '已从游戏目录卸载' : ('卸载失败：' + r.error), r.ok ? 'success' : 'error');
        await loadHub();
      });
    });
    $('hubDetailBody').querySelectorAll('[data-hmdel]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var ok = await ask('删除 Mod', '<p>删除该 mod 记录，并<strong>自动从游戏目录移除本工具安装的文件</strong>（不碰游戏本体）。游戏运行中需先关闭。</p>', '确认删除');
        if (!ok) return;
        var r = await api.remove_mod(g.id, b.dataset.hmdel);
        if (!r.ok) { toast('删除失败：' + r.error, 'error'); return; }
        toast('已删除' + ((r.uninstalled || []).length ? '，并已从游戏目录移除' : ''), 'success');
        loadHub(); openHubDetail('mods'); loadAllMods();
      });
    });
  }

  // ---------- Mod 管理 ----------
  function bindMods() {
    $('modClose').addEventListener('click', function () {
      $('modOverlay').style.display = 'none';
      loadAllMods();  // 关闭抽屉后刷新 Mod 管理页与角标
      loadHub();      // 同步游戏库页的 mod 列表
    });
    $('modAddLink').addEventListener('click', doModAddLink);
    $('modImportFile').addEventListener('click', doModImportFile);
    $('modsQuery').addEventListener('input', function () {
      state.modsQuery = this.value.trim().toLowerCase();
      renderModsGrid();
    });
  }

  async function loadAllMods() {
    try {
      var r = await api.get_all_mods();
      state.allMods = r.items || [];
      renderModsGrid();
    } catch (e) { toast('加载 Mod 列表失败：' + e, 'error'); }
  }

  function renderModsGrid() {
    var all = state.allMods || [];
    var q = state.modsQuery || '';
    var total = all.reduce(function (n, t) { return n + (t.trainer_count || 0); }, 0);
    $('modTotalBadge').textContent = total;

    if (!all.length) {
      $('modsGrid').innerHTML = '';
      $('modsEmpty').innerHTML =
        '<div class="state-card idle-state">' +
          '<div class="state-icon">⊞</div>' +
          '<div class="state-title">库里还没有游戏</div>' +
          '<div class="state-desc">Mod 是关联到游戏下的。先在「游戏库」添加一个游戏，再来这里添加 Mod。</div>' +
          '<button class="btn btn-primary" data-goto="hub">去游戏库添加游戏</button>' +
        '</div>';
      var g = $('modsEmpty').querySelector('[data-goto]');
      if (g) g.addEventListener('click', function () { goto('hub'); });
      return;
    }

    var shown = all.filter(function (t) {
      if (!q) return true;
      if ((t.name || '').toLowerCase().indexOf(q) >= 0) return true;
      return (t.mods || []).some(function (m) { return (m.name || '').toLowerCase().indexOf(q) >= 0; });
    });

    if (!shown.length) {
      $('modsGrid').innerHTML = '';
      $('modsEmpty').innerHTML =
        '<div class="state-card empty-result-state"><div class="state-icon">∅</div>' +
        '<div class="state-title">没有匹配的游戏或 Mod</div>' +
        '<div class="state-desc">换个关键词试试。</div></div>';
      return;
    }
    $('modsEmpty').innerHTML = '';
    $('modsGrid').innerHTML = shown.map(function (t) {
      var mods = t.mods || [];
      var preview = mods.length
        ? '<div class="mods-preview">' + mods.slice(0, 3).map(function (m) {
            return '<span class="mod-chip" title="添加于 ' + esc(m.added || '—') + '">' + esc(m.name) + '</span>';
          }).join('') + (mods.length > 3 ? '<span class="mod-chip more">+' + (mods.length - 3) + '</span>' : '') + '</div>'
        : '<div class="mods-preview empty">暂无关联 mod</div>';
      return '<div class="mods-card" data-mods="' + esc(t.id) + '">' +
        '<div class="mods-card-top">' +
          '<div class="mods-card-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 12h4M8 10v4M15 11h.01M18 13h.01"/><rect x="2" y="7" width="20" height="10" rx="4"/></svg></div>' +
          '<div class="mods-card-main">' +
            '<div class="mods-card-name">' + esc(t.name) + '</div>' +
            '<div class="mods-card-ver mono-num">◷ ' + esc(t.added || '—') + '</div>' +
          '</div>' +
          '<span class="mods-card-count">' + mods.length + ' mod</span>' +
        '</div>' +
        preview +
        '<button class="btn btn-primary btn-sm mods-card-btn">管理此游戏的 Mod →</button>' +
      '</div>';
    }).join('');
    $('modsGrid').querySelectorAll('[data-mods]').forEach(function (card) {
      card.addEventListener('click', function () { gotoGameMods(card.dataset.mods); });
    });
  }

  // 从 Mod 管理页跳到「游戏库 → 该游戏 → Mod」详情页（管理入口）
  async function gotoGameMods(gameId) {
    state.hubGameId = null;
    state.hubDetailOpt = null;
    goto('hub');
    await loadHub();
    openHubGame(gameId);       // 选中游戏，显示选项层
    openHubDetail('mods');     // 直接进 Mod 详情页
  }

  async function openMods(gameId) {
    var g = state.hub.find(function (x) { return x.id === gameId; });
    state.currentModGame = gameId;
    $('modGameName').textContent = g ? g.name : '';
    $('modOverlay').style.display = 'flex';
    try {
      var links = await api.mod_search_links(g ? g.name : '');
      $('modLinks').innerHTML = links.map(function (l, i) {
        return '<button class="mod-site-btn" data-i="' + i + '">' +
          '<span class="site-name">' + esc(l.site) + '</span>' +
          '<span class="site-note">' + esc(l.note) + '</span><span class="site-arrow">↗</span></button>';
      }).join('');
      $('modLinks').querySelectorAll('[data-i]').forEach(function (b) {
        b.addEventListener('click', function () { api.open_url(links[parseInt(b.dataset.i, 10)].url); });
      });
      await loadModDir();
    } catch (e) { toast('加载 mod 失败：' + e, 'error'); }
  }

  // 渲染「安装目录」区块，Mod 抽屉与游戏详情 Mod 页共用
  async function renderModDirBox(container, tid) {
    if (!container || !tid) return;
    try {
      var r = await api.get_game_mod_dir(tid);
      var d = (r.dir || '');
      var sugs = r.suggestions || [];
      var g = state.hub.find(function (x) { return x.id === tid; });
      var exeDir = g && g.exe_path ? g.exe_path.substring(0, Math.max(g.exe_path.lastIndexOf('\\'), g.exe_path.lastIndexOf('/'))) : '';
      var html = '<div class="dir-row"><span class="dir-label">安装目录</span>' +
        '<span class="dir-path' + (d ? '' : ' unset') + '">' + esc(d || '未设置 · 导入的文件只会保存在本工具内') + '</span>' +
        '<button class="btn btn-ghost btn-sm js-dir-pick">选择目录</button>' +
        (d ? '<button class="btn btn-ghost btn-sm js-dir-open">打开</button>' : '') +
        '</div>';
      if (sugs.length) {
        html += '<div class="dir-sug">自动识别：' + sugs.map(function (s, i) {
          return '<button class="js-dir-sug" data-sug="' + i + '">' + esc(s) + '</button>';
        }).join('') + '</div>';
      }
      html += '<div class="dir-tip">点「选择目录」，选中<strong>含游戏 exe 的根目录</strong>即可，本工具会自动建立并使用 <code>~mods</code>（虚幻引擎游戏只有放进这里才会加载）。删除时只移除本工具安装的文件，不碰游戏本体。' +
        (d && d.replace(/[\\/]/g, '').toLowerCase().indexOf('~mods') >= 0 ? '<div class="dir-tip-ok">✓ 当前为 <code>~mods</code> 目录，从本工具「启动游戏」会自动带上 <code>-fileopenlog</code> 参数加载 Mod。</div>' : '') +
        (exeDir ? '<div class="dir-tip-exe">游戏目录：<span class="mono">' + esc(exeDir) + '</span></div>' : '') +
        '</div>';
      container.innerHTML = html;
      container.querySelector('.js-dir-pick').addEventListener('click', async function () {
        var go = await ask('选择 Mod 安装目录',
          '<p>请选择<strong>游戏本体所在的文件夹</strong>（里面有游戏 exe 的那一层），本工具会自动在该目录下寻找 <code>~mods</code> 子文件夹来安装 Mod。</p>' +
          '<p>常见结构：<code>游戏目录/Content/Paks/~mods</code>，通常直接选择含 exe 的<strong>游戏根目录</strong>即可。</p>' +
          (sugs.length ? '<p class="guide-ok">已自动识别到候选目录，可直接点上方按钮采用：<br>' + sugs.map(function (s) { return '<code>' + esc(s) + '</code>'; }).join('<br>') + '</p>' : '') +
          (exeDir ? '<p class="muted">当前游戏所在目录：<code>' + esc(exeDir) + '</code></p>' : '') +
          '<p class="muted">若暂时找不到也没关系，先跳过，导入的 Mod 只会保存在本工具内，之后随时可以回来设置。</p>',
          '去选择文件夹');
        if (!go) return;
        var folder = await api.pick_folder();
        if (!folder) return;
        var s = await api.set_game_mod_dir(tid, folder);
        if (!s.ok) { toast('设置失败：' + s.error, 'error'); return; }
        toast(s.auto ? ('Mod 安装目录已设置（自动定位到 ' + s.dir + '）') : 'Mod 安装目录已设置', 'success');
        renderModDirBox(container, tid);
      });
      var ob = container.querySelector('.js-dir-open');
      if (ob) ob.addEventListener('click', function () { api.open_mod_path(tid, '__dir__'); });
      container.querySelectorAll('.js-dir-sug').forEach(function (b) {
        b.addEventListener('click', async function () {
          var s = await api.set_game_mod_dir(tid, sugs[parseInt(b.dataset.sug, 10)]);
          if (!s.ok) { toast('设置失败：' + s.error, 'error'); return; }
          toast('已使用自动识别的目录', 'success'); renderModDirBox(container, tid);
        });
      });
    } catch (e) { container.innerHTML = ''; }
  }

  async function loadModDir() {
    await renderModDirBox($('modInstallDir'), state.currentModGame);
  }

  async function doModAddLink() {
    var tid = state.currentModGame;
    if (!tid) return;
    var name = $('modName').value.trim();
    var url = $('modUrl').value.trim();
    var note = $('modNote').value.trim();
    if (!name) { toast('请填写名称'); return; }
    if (!url) { toast('请填写下载链接'); return; }
    // 若是直链则下载，否则仅记录链接
    if (/^https?:\/\//.test(url) && /\.(zip|rar|7z|exe|dll|lua|asi|pak)(\?|$)/i.test(url)) {
      $('downloadOverlay').style.display = 'flex';
      $('progressTitle').textContent = '正在下载 Mod…';
      $('progressFilename').textContent = url.split('/').pop().split('?')[0];
      $('progressFill').style.width = '0%'; $('progressPct').textContent = '0%';
      var timer = pollProgress('get_mod_download_state', 'downloadOverlay', 'progressFill', 'progressPct');
      try {
        var r = await api.download_mod(tid, url, name, note);
        clearInterval(timer); $('downloadOverlay').style.display = 'none';
        if (!r.ok) { toast('下载失败：' + r.error + '（已改为仅记录链接）', 'error'); await api.add_mod_link(tid, name, url, note); }
        else toast('Mod 已下载并关联', 'success');
      } catch (e) {
        clearInterval(timer); $('downloadOverlay').style.display = 'none';
        await api.add_mod_link(tid, name, url, note);
        toast('下载失败，已记录链接', 'error');
      }
    } else {
      await api.add_mod_link(tid, name, url, note);
      toast('链接已关联', 'success');
    }
    $('modName').value = ''; $('modUrl').value = ''; $('modNote').value = '';
    loadAllMods(); loadHub();
  }

  async function doModImportFile() {
    var tid = state.currentModGame;
    if (!tid) return;
    try {
      var paths = await api.pick_mod_files();
      if (!paths || !paths.length) return;
      var r = await api.import_mod_files(tid, paths);
      var items = r.items || [];
      var ins = items.filter(function (x) { return (x.install_names || []).length; }).length;
      var pending = items.filter(function (x) { return !(x.install_names || []).length && x.path; }).length;
      if (ins) toast('已导入并自动安装 ' + ins + ' 个 Mod 到游戏目录，重启游戏生效', 'success');
      else if (pending) toast('已导入 ' + pending + ' 个 Mod，请设置安装目录后点「安装到游戏」', 'error');
      else toast('已导入 ' + items.length + ' 个 mod 文件', 'success');
      loadAllMods(); loadHub();
    } catch (e) { toast('导入失败：' + e, 'error'); }
  }
})();
