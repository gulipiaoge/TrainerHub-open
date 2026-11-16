# -*- coding: utf-8 -*-
"""
TrainerHub 后端核心
- 本地修改器库管理（导入 / 启动 / 删除）
- 风灵月影官网搜索与下载
- 版本更新检测
- 每个游戏的 Mod 管理（站点直达搜索 + 手动添加 / 下载 / 关联）
所有数据仅保存在项目目录 data/ 下，不写系统、不写注册表。
"""
import os
import re
import json
import html as html_mod
import shutil
import subprocess
import webbrowser
import zipfile
import urllib.parse
from pathlib import Path
from datetime import datetime

import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
TRAINERS_DIR = DATA / "trainers"
MODS_DIR = DATA / "mods"
GAMES_FILE = DATA / "games.json"        # 游戏实体（用户添加 / 扫描得到）
LIBRARY_FILE = DATA / "library.json"    # 修改器，通过 game_id 归属游戏
CONFIG_FILE = DATA / "config.json"
SITE = "https://flingtrainer.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": SITE + "/",
}


def _safe_name(name: str) -> str:
    """清洗文件名，移除 Windows 非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name[:120] or "trainer"


# 中文游戏名 -> 官网英文索引名（风灵月影官网用英文标题，中文直接搜必然 0 结果）
CN_TO_EN = {
    "黑神话": "Black Myth Wukong", "悟空": "Black Myth Wukong", "黑神话悟空": "Black Myth Wukong",
    "艾尔登法环": "Elden Ring", "老头环": "Elden Ring", "法环": "Elden Ring",
    "只狼": "Sekiro", "赛博朋克": "Cyberpunk 2077", "2077": "Cyberpunk 2077",
    "荒野大镖客": "Red Dead Redemption", "大镖客": "Red Dead Redemption", "r星": "Red Dead Redemption",
    "侠盗猎车手": "Grand Theft Auto", "gta": "Grand Theft Auto",
    "巫师": "The Witcher", "上古卷轴": "The Elder Scrolls", "老滚": "The Elder Scrolls",
    "辐射": "Fallout", "刺客信条": "Assassin's Creed", "看门狗": "Watch Dogs",
    "孤岛惊魂": "Far Cry", "生化危机": "Resident Evil", "怪物猎人": "Monster Hunter",
    "鬼泣": "Devil May Cry", "战神": "God of War", "最后生还者": "The Last of Us", "美国末日": "The Last of Us",
    "神秘海域": "Uncharted", "对马岛": "Ghost of Tsushima", "霍格沃茨": "Hogwarts Legacy",
    "博德之门": "Baldur's Gate", "龙之信条": "Dragon's Dogma", "星空": "Starfield",
    "死亡搁浅": "Death Stranding", "合金装备": "Metal Gear", "细胞分裂": "Splinter Cell",
    "暗黑破坏神": "Diablo", "流放之路": "Path of Exile", "文明": "Civilization",
    "全面战争": "Total War", "城市天际线": "Cities Skylines", "欧洲卡车": "Euro Truck Simulator",
    "模拟人生": "The Sims", "星露谷": "Stardew Valley", "泰拉瑞亚": "Terraria",
    "我的世界": "Minecraft", "空洞骑士": "Hollow Knight", "哈迪斯": "Hades", "死亡细胞": "Dead Cells",
    "以撒": "The Binding of Isaac", "蔚蓝": "Celeste", "茶杯头": "Cuphead", "奥日": "Ori",
    "鬼谷": "Black Myth Wukong", "红色沙漠": "Crimson Desert", "寂静岭": "Silent Hill",
    "生化": "Resident Evil", "逆转裁判": "Ace Attorney", "火焰纹章": "Fire Emblem",
    "集合啦动物森友会": "Animal Crossing", "动物森友会": "Animal Crossing", "塞尔达": "The Legend of Zelda",
    "超级马力欧": "Super Mario", "马力欧": "Super Mario", "斯普拉遁": "Splatoon",
    "猎天使魔女": "Bayonetta", "崩坏": "Honkai", "原神": "Genshin Impact",
}


def _translate_query(text: str):
    """把中文游戏名转成英文关键词。返回 (英文词, 命中的中文) 或 (None, None)"""
    if not text or not re.search(r"[\u4e00-\u9fff]", text):
        return None, None
    low = text.strip().lower()
    # 长词优先，避免"黑神话悟空"被"悟空"截断
    for cn in sorted(CN_TO_EN, key=len, reverse=True):
        if cn.lower() in low:
            return CN_TO_EN[cn], cn
    return None, None


class Backend:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        TRAINERS_DIR.mkdir(parents=True, exist_ok=True)
        MODS_DIR.mkdir(parents=True, exist_ok=True)
        self._download_state = {"active": False, "percent": 0, "filename": "", "done": False, "error": ""}
        self._mod_download_state = {"active": False, "percent": 0, "filename": "", "done": False, "error": ""}
        self._migrate_to_games()
        self._migrate_mod_installed_flags()

    # ---------- 游戏实体 ----------
    def _load_games(self):
        if GAMES_FILE.exists():
            try:
                data = json.loads(GAMES_FILE.read_text("utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def _save_games(self, games):
        GAMES_FILE.write_text(json.dumps(games, ensure_ascii=False, indent=2), "utf-8")

    def _migrate_to_games(self):
        """旧版把每个修改器当游戏；迁移为：游戏实体 + 修改器按 game_id 归属。
        按文件 SHA-256 分组：内容相同的 exe = 同一修改器 = 同一游戏（合并重复副本），
        内容不同的 exe = 不同游戏。仅首次执行。"""
        if GAMES_FILE.exists():
            return  # 已迁移过
        lib = self._load_library()
        games = []
        new_lib = []
        groups = {}  # digest -> game index
        # 先按 hash 分组
        for item in lib:
            p = Path(item.get("path", ""))
            h = self.file_sha256(str(p))
            digest = h.get("hash", "") if h.get("ok") else ("size%d_%s" % (
                item.get("size", 0), item.get("filename", "")))
            item = dict(item)
            item["_digest"] = digest
            if digest not in groups:
                base = self._game_name_from_trainer(item.get("name", ""), item.get("filename", ""))
                gid = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(len(games))
                games.append({
                    "id": gid, "name": base, "exe_path": "",
                    "added": item.get("added", datetime.now().strftime("%Y-%m-%d %H:%M")),
                    "last_launch": "",
                })
                groups[digest] = len(games) - 1
            item["game_id"] = games[groups[digest]]["id"]
            new_lib.append(item)
        if lib:  # 有旧数据才写，避免空迁移
            self._save_games(games)
            for it in new_lib:
                it.pop("_digest", None)
            self._save_library(new_lib)
            # mods 记录：同一 game 的所有旧 trainer id 的 mod 合并到 game_id
            for g in games:
                merged = []
                for it in new_lib:
                    if it.get("game_id") != g["id"]:
                        continue
                # 用旧 id -> game_id 映射合并
                id_map = {x.get("id"): x.get("game_id") for x in lib}
                for old_id, gid in id_map.items():
                    src = DATA / ("mods_%s.json" % old_id)
                    if not src.exists():
                        continue
                    try:
                        merged += json.loads(src.read_text("utf-8"))
                    except Exception:
                        pass
                    src.unlink()
                if merged:
                    (DATA / ("mods_%s.json" % g["id"])).write_text(
                        json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
            # 删除重复 exe 文件：每个 digest 只保留第一个（在 trainers 目录内的）
            kept = set()
            to_remove = []
            for it in new_lib:
                d = it.get("_digest", "")
                if d in kept:
                    to_remove.append(it)
                else:
                    kept.add(d)
            for it in to_remove:
                p = Path(it.get("path", ""))
                if p.exists() and TRAINERS_DIR.resolve() in p.resolve().parents:
                    try:
                        p.unlink()
                    except Exception:
                        pass
            final_lib = []
            for it in new_lib:
                it.pop("_digest", None)
                p = Path(it.get("path", ""))
                if p.exists():
                    final_lib.append(it)
            self._save_library(final_lib)

    def _game_name_from_trainer(self, name: str, filename: str) -> str:
        """从修改器名称提取干净的游戏名，去掉 Trainer / FLiNG / 版本等"""
        s = (name or "").strip()
        # "Black Myth: Wukong Trainer" -> "Black Myth: Wukong"
        s = re.sub(r"\s+(v?\d[\d.]*\+?.*|Plus\s*\d+.*|Trainer.*|FLiNG.*)$", "", s, flags=re.I)
        s = re.sub(r"[_-]?v?\d[\d.]*.*$", "", s, flags=re.I) if "v1." in s.lower() else s
        s = re.sub(r"[_\-]\s*(修改器|Trainer|FLiNG).*$", "", s, flags=re.I)
        s = s.strip(" :_-·")
        return s or _safe_name(filename or "游戏")

    def get_games(self):
        """返回游戏实体列表，附带修改器数量 / mod 数量 / 最近启动"""
        games = self._load_games()
        lib = self._load_library()
        out = []
        for g in games:
            trainers = [t for t in lib if t.get("game_id") == g["id"]]
            mods = self._load_mods(g["id"])
            out.append({
                "id": g["id"],
                "name": g.get("name", ""),
                "exe_path": g.get("exe_path", ""),
                "mod_dir": g.get("mod_dir", ""),
                "added": g.get("added", ""),
                "last_launch": g.get("last_launch", "") or max(
                    [t.get("last_launch", "") for t in trainers] or [""]),
                "trainer_count": len(trainers),
                "mod_count": len(mods),
            })
        out.sort(key=lambda x: x.get("added", ""), reverse=True)
        return out

    def create_game(self, name: str, exe_path: str = ""):
        """用户手动添加一个游戏"""
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "游戏名不能为空"}
        games = self._load_games()
        for g in games:
            if g.get("name", "").lower() == name.lower():
                return {"ok": False, "error": "该游戏已存在"}
        game = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f") + str(len(games)),
            "name": name,
            "exe_path": exe_path,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_launch": "",
        }
        games.append(game)
        self._save_games(games)
        return {"ok": True, "game": game}

    def rename_game(self, game_id: str, name: str):
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "游戏名不能为空"}
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        g["name"] = name
        self._save_games(games)
        return {"ok": True, "name": name}

    def set_game_exe(self, game_id: str, exe_path: str):
        """设置游戏本体 exe 路径（用于启动游戏）"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        g["exe_path"] = exe_path
        g["last_launch"] = g.get("last_launch", "")
        self._save_games(games)
        return {"ok": True}

    @staticmethod
    def _find_paks_dir(base: Path):
        """在 base 及其下层（最多 3 层）里找虚幻引擎的 Content/Paks 目录。
        兼容 exe 在根目录（Paks 在 b1/Content/Paks）和 exe 就在项目目录两种情况。"""
        base = Path(base)
        candidates = [base]
        try:
            candidates += [p for p in base.iterdir() if p.is_dir()]
        except Exception:
            pass
        # 再往下钻一层（如 base/b1）
        for c in list(candidates):
            try:
                candidates += [p for p in c.iterdir() if p.is_dir()]
            except Exception:
                pass
        for c in candidates:
            if c.name.lower() == "paks" and c.is_dir():
                return c
        for c in candidates:
            p = c / "Content" / "Paks"
            if p.is_dir():
                return p
            p2 = c / "Paks"
            if p2.is_dir():
                return p2
        return None

    def set_game_mod_dir(self, game_id: str, path: str):
        """设置该游戏的 Mod 安装目录（一般是 Content/Paks/~mods）

        若玩家选的是游戏根目录（含 exe 那层），自动向下寻找常见的 mod 子目录，
        避免玩家不清楚该选哪一层。
        """
        path = (path or "").strip()
        if not path or not Path(path).is_dir():
            return {"ok": False, "error": "目录不存在"}
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        chosen = Path(path).resolve()
        requested = str(chosen)
        # 虚幻引擎游戏（黑神话等）的 mod 必须放进 Content/Paks/~mods 才会加载。
        # 若玩家选到 Paks 或其上级，自动建立 ~mods（不存在就创建），
        # 绝不能退回到 Paks 根目录——那样游戏读不到，表现为"装了不生效"。
        paks = self._find_paks_dir(chosen)
        if paks is not None:
            mods_sub = paks / "~mods"
            try:
                mods_sub.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {"ok": False, "error": "无法创建 ~mods 目录：%s" % e}
            chosen = mods_sub.resolve()
        else:
            for rel in ("Content/Paks/~mods", "~mods", "Mods", "mods"):
                cand = chosen / rel.replace("/", os.sep)
                if cand.is_dir():
                    chosen = cand.resolve()
                    break
        g["mod_dir"] = str(chosen)
        self._save_games(games)
        return {
            "ok": True,
            "dir": g["mod_dir"],
            "auto": requested != g["mod_dir"],
            "requested": requested,
        }

    def suggest_mod_dirs(self, game_id: str):
        """根据游戏本体路径推断常见的 mod 目录，供用户一键选择"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        exe = g.get("exe_path", "")
        items = []
        if exe and Path(exe).exists():
            root = Path(exe).parent
            # 虚幻引擎游戏：找到 Content/Paks 后推荐其下的 ~mods（存在则列出）
            paks = self._find_paks_dir(root)
            if paks is not None:
                mods_sub = paks / "~mods"
                if mods_sub.is_dir() and str(mods_sub.resolve()) not in items:
                    items.append(str(mods_sub.resolve()))
                if str(paks.resolve()) not in items:
                    items.append(str(paks.resolve()))
            # 通用目录
            for rel in ("~mods", "mods", "Mods"):
                p = root / rel.replace("/", os.sep)
                if p.is_dir():
                    rp = str(p.resolve())
                    if rp not in items:
                        items.append(rp)
        return {"ok": True, "items": items}

    def get_game_mod_dir(self, game_id: str):
        """返回当前 mod 目录 + 自动推断的候选"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        d = g.get("mod_dir", "")
        return {
            "ok": True,
            "dir": d,
            "exists": bool(d and Path(d).is_dir()),
            "suggestions": self.suggest_mod_dirs(game_id).get("items", []),
        }

    def remove_game(self, game_id: str):
        """删除游戏实体及其下所有修改器记录 / mod 记录（本地文件保留）"""
        games = [x for x in self._load_games() if x.get("id") != game_id]
        self._save_games(games)
        lib = [x for x in self._load_library() if x.get("game_id") != game_id]
        self._save_library(lib)
        mf = DATA / ("mods_%s.json" % game_id)
        if mf.exists():
            mf.unlink()
        return {"ok": True}

    def _run_process(self, exe_path: str, args=None):
        """启动 exe；若程序要求管理员权限（WinError 740），自动弹 UAC 提权。
        args: 附加启动参数列表，如 ['-fileopenlog']。"""
        exe = str(exe_path)
        cwd = str(Path(exe).parent)
        args = [str(a) for a in (args or [])]
        cmd = [exe] + args
        params = " ".join(args)
        if os.name == "nt":
            try:
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                subprocess.Popen(cmd, cwd=cwd, creationflags=flags, close_fds=True)
                return {"ok": True}
            except OSError as e:
                if getattr(e, "winerror", None) != 740:
                    raise
                import ctypes
                ret = ctypes.windll.shell32.ShellExecuteW(
                    0, "runas", exe, params, cwd, 1)
                if int(ret) <= 32:
                    return {"ok": False,
                            "error": "已取消管理员授权，该程序需要管理员权限才能启动"}
                return {"ok": True, "elevated": True}
        subprocess.Popen(cmd, cwd=cwd, close_fds=True)
        return {"ok": True}

    def launch_game(self, game_id: str):
        """启动游戏本体 exe"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        exe = g.get("exe_path", "")
        if not exe or not Path(exe).exists():
            return {"ok": False, "error": "未设置游戏本体路径或文件不存在"}
        # 虚幻引擎游戏（如黑神话悟空）的 pak mod 放在 ~mods 时，
        # 需要 -fileopenlog 启动参数才会加载，自动附加，省去手动填启动项。
        args = []
        mod_dir = g.get("mod_dir", "")
        if mod_dir and Path(mod_dir).name.lower() == "~mods":
            args.append("-fileopenlog")
        try:
            res = self._run_process(exe, args)
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error", "启动失败")}
            g["last_launch"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._save_games(games)
            return {"ok": True, "name": g.get("name", ""),
                    "elevated": bool(res.get("elevated")),
                    "args": args}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def scan_directory(self, folder: str):
        """扫描目录（含子目录一层）下的 exe，返回候选游戏列表供用户选择添加"""
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            return {"ok": False, "error": "目录不存在"}
        candidates = []
        seen = set()
        try:
            for p in list(folder.glob("*.exe")) + list(folder.glob("*/*.exe")):
                try:
                    size = p.stat().st_size
                except Exception:
                    continue
                if size < 1024 * 512:  # 跳过小于 512KB 的（多为修改器 / 小工具）
                    continue
                low = p.stem.lower()
                if any(k in low for k in ("trainer", "fling", "crack", "setup", "installer", "unins")):
                    continue
                if p.resolve() in seen:
                    continue
                seen.add(p.resolve())
                # 用所在文件夹名或 exe 名做候选游戏名
                name = p.parent.name if p.parent.name.lower() not in (folder.name.lower(), "game", "games") else p.stem
                candidates.append({
                    "name": name or p.stem,
                    "exe_path": str(p.resolve()),
                    "size": size,
                })
        except Exception as e:
            return {"ok": False, "error": str(e)}
        candidates.sort(key=lambda x: x["size"], reverse=True)
        return {"ok": True, "items": candidates[:40]}

    # ---------- 配置 ----------
    def _default_config(self):
        return {
            "trainer_dir": str(TRAINERS_DIR),
            "auto_check_update": False,
            "confirm_before_launch": True,
            "last_search": "",
            "safety_acknowledged": False,   # 首次启动确认
            "last_update_check": "",         # 上次检查更新时间
        }

    def get_config(self):
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text("utf-8"))
                base = self._default_config()
                base.update(cfg)
                return base
            except Exception:
                pass
        return self._default_config()

    def save_config(self, cfg: dict):
        try:
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- 本地库 ----------
    def _fill_added(self, item, fallback_path=""):
        """旧条目若缺 added，用本地文件（链接型 mod 用记录文件）创建时间兜底。"""
        if item.get("added"):
            return item
        p = Path(item.get("path", "") or fallback_path)
        try:
            if p.exists():
                item["added"] = datetime.fromtimestamp(
                    p.stat().st_ctime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        return item

    def _load_library(self):
        if LIBRARY_FILE.exists():
            try:
                data = json.loads(LIBRARY_FILE.read_text("utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def _save_library(self, lib):
        LIBRARY_FILE.write_text(json.dumps(lib, ensure_ascii=False, indent=2), "utf-8")

    def get_library(self):
        lib = self._load_library()
        # 清理失效记录（文件不存在）
        valid = [x for x in lib if Path(x.get("path", "")).exists()]
        if len(valid) != len(lib):
            self._save_library(valid)
        for x in valid:
            self._fill_added(x)
        valid.sort(key=lambda x: x.get("added", ""), reverse=True)
        return valid

    def _detect_version(self, filename: str) -> str:
        m = re.search(r"v?(\d+\.\d+(?:\.\d+)*)", filename)
        return "v" + m.group(1) if m else "-"

    def _norm_game_name(self, name: str) -> str:
        """归一化游戏名用于去重匹配：中文转英文 + 去 Trainer/版本/标点"""
        s = (name or "").strip().lower()
        en, _ = _translate_query(s)
        if en:
            s = en.lower()
        s = re.sub(r"\s*(trainer|fling|plus)\b.*$", "", s, flags=re.I)
        s = re.sub(r"\s*v?\d[\d.].*$", "", s)
        s = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", s)
        return s

    def _find_or_create_game(self, name: str, source_url: str = ""):
        """找到已有游戏则归入，否则新建。用官网 slug + 中英文归一化匹配，避免重复游戏。"""
        games = self._load_games()
        # 1) 官网 trainer slug 匹配（同一页面 = 同一游戏）
        if source_url and "/trainer/" in source_url:
            m = re.search(r"/trainer/([^/]+)", source_url)
            if m:
                slug = m.group(1).lower()
                for t in self._load_library():
                    ts = t.get("source_url", "")
                    tm = re.search(r"/trainer/([^/]+)", ts) if "/trainer/" in ts else None
                    if tm and tm.group(1).lower() == slug:
                        gid = t.get("game_id")
                        g = next((x for x in games if x.get("id") == gid), None)
                        if g:
                            return {"ok": True, "game_id": gid, "created": False, "name": g["name"]}
        # 2) 名字归一化匹配（精确）
        norm = self._norm_game_name(name)
        if norm:
            for g in games:
                if self._norm_game_name(g.get("name", "")) == norm:
                    return {"ok": True, "game_id": g["id"], "created": False, "name": g["name"]}
            # 2b) 宽松匹配：剥离结尾的续作序号再比一次
            # 官网标题常带 "2"（Red Dead Redemption 2 Trainer），而用户库里是"荒野大镖客"
            # 归一化后 reddeadredemption2 vs reddeadredemption，精确匹配会漏，导致重复游戏
            loose = re.sub(r"\d+$", "", norm)
            if loose and loose != norm:
                for g in games:
                    gnorm = self._norm_game_name(g.get("name", ""))
                    if gnorm == loose or re.sub(r"\d+$", "", gnorm) == loose:
                        return {"ok": True, "game_id": g["id"], "created": False, "name": g["name"]}
        # 3) 新建游戏
        display = self._game_name_from_trainer(name, "") or _safe_name(name or "游戏")
        game = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f") + str(len(games)),
            "name": display, "exe_path": "",
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"), "last_launch": "",
        }
        games.append(game)
        self._save_games(games)
        return {"ok": True, "game_id": game["id"], "created": True, "name": display}

    def _register_file(self, file_path: Path, game_id: str, name=None,
                       source_url="", options=0, version=""):
        """把一个 exe 注册进库（同路径去重，归属到 game_id）"""
        lib = self._load_library()
        sp = str(file_path.resolve())
        for item in lib:
            if item.get("path") == sp:
                return {"ok": False, "msg": "该修改器已在库中", "item": item}
        entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "game_id": game_id,
            "name": name or _safe_name(file_path.stem),
            "version": version or self._detect_version(file_path.stem),
            "options": options,
            "source_url": source_url,
            "path": sp,
            "filename": file_path.name,
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_checked": "",
            "remote_updated": "",
        }
        lib.append(entry)
        self._save_library(lib)
        return {"ok": True, "item": entry}

    def import_trainer(self, file_paths, game_id=""):
        """导入修改器到指定游戏（未传 game_id 时按文件名推断并归入/新建游戏）"""
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        results = []
        for src in file_paths:
            src = Path(src)
            if not src.exists():
                continue
            gid = game_id or self._find_or_create_game(
                self._game_name_from_trainer(src.stem, src.name))["game_id"]
            if src.suffix.lower() == ".zip":
                try:
                    dest_dir = TRAINERS_DIR / _safe_name(src.stem)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(src, "r") as z:
                        # 防目录穿越
                        for member in z.namelist():
                            if member.endswith("/"):
                                continue
                            target = (dest_dir / member).resolve()
                            if dest_dir.resolve() not in target.parents:
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(member) as fsrc, open(target, "wb") as fdst:
                                shutil.copyfileobj(fsrc, fdst)
                    exes = [p for p in dest_dir.rglob("*") if p.suffix.lower() == ".exe"]
                    if exes:
                        main_exe = max(exes, key=lambda p: p.stat().st_size)
                        results.append(self._register_file(main_exe, gid, name=_safe_name(src.stem)))
                    else:
                        results.append({"ok": False, "msg": "压缩包内没有 exe"})
                except Exception as e:
                    results.append({"ok": False, "msg": "解压失败: %s" % e})
            elif src.suffix.lower() == ".exe":
                dest = TRAINERS_DIR / _safe_name(src.name)
                if src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
                results.append(self._register_file(dest, gid))
            else:
                results.append({"ok": False, "msg": "不支持的文件类型"})
        return results

    def add_imported_exe(self, path: str, name="", version="", options=0,
                         source_url="", game_id=""):
        """供已下载文件直接入库"""
        p = Path(path)
        gid = game_id or self._find_or_create_game(name or p.stem, source_url)["game_id"]
        return self._register_file(p, gid, name=name, version=version,
                                   options=options, source_url=source_url)

    def remove_trainer(self, trainer_id: str, delete_file=False):
        lib = self._load_library()
        target = next((x for x in lib if x.get("id") == trainer_id), None)
        if not target:
            return {"ok": False, "error": "未找到"}
        if delete_file:
            try:
                p = Path(target["path"])
                if p.exists() and TRAINERS_DIR.resolve() in p.resolve().parents:
                    p.unlink()
            except Exception as e:
                return {"ok": False, "error": str(e)}
        lib = [x for x in lib if x.get("id") != trainer_id]
        self._save_library(lib)
        return {"ok": True}

    def launch_trainer(self, trainer_id: str):
        lib = self._load_library()
        target = next((x for x in lib if x.get("id") == trainer_id), None)
        if not target:
            return {"ok": False, "error": "未找到"}
        p = Path(target["path"])
        if not p.exists():
            return {"ok": False, "error": "文件不存在，可能已被移动或删除"}
        try:
            res = self._run_process(str(p))
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error", "启动失败")}
            target["last_launch"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._save_library(lib)
            return {"ok": True, "name": target.get("name"), "last_launch": target["last_launch"],
                    "elevated": bool(res.get("elevated"))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_trainer_folder(self):
        try:
            os.startfile(str(TRAINERS_DIR))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- 在线搜索 ----------
    def search_games(self, query: str):
        query = (query or "").strip()
        if not query:
            return {"ok": True, "items": []}

        en, hit_cn = _translate_query(query)
        # 查询词序列：英文转换词优先，原词兜底（官网偶尔也有中文标题）
        terms = []
        if en:
            terms.append(en)
        if query not in terms:
            terms.append(query)

        items = []
        seen = set()
        last_err = None
        try:
            for term in terms:
                r = requests.get(SITE + "/wp-json/wp/v2/search",
                                 params={"search": term, "per_page": 20},
                                 headers=HEADERS, timeout=20)
                r.raise_for_status()
                for it in r.json():
                    url = it.get("url", "")
                    if url in seen:
                        continue
                    seen.add(url)
                    items.append({
                        "id": it.get("id"),
                        "title": html_mod.unescape(it.get("title", "")),
                        "url": url,
                    })
            cfg = self.get_config()
            cfg["last_search"] = query
            self.save_config(cfg)
            return {
                "ok": True,
                "items": items,
                "translated": bool(en),
                "hit_cn": hit_cn or "",
                "en_term": en or "",
            }
        except Exception as e:
            # 搜索失败时，若英文转换词已拿到结果则仍返回（不因原词报错而全盘失败）
            if items:
                return {"ok": True, "items": items, "translated": bool(en),
                        "hit_cn": hit_cn or "", "en_term": en or ""}
            last_err = e
            return {"ok": False, "error": "搜索失败: %s" % last_err}

    def get_game_detail(self, url: str):
        """抓取修改器详情页：版本、更新时间、功能数、下载列表"""
        if not url.startswith(SITE):
            return {"ok": False, "error": "非法链接"}
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            raw = r.text

            downloads = []
            # 官网下载表格结构：<tr> 内含 attachment-date/size/downloads 三个 td
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.S | re.I):
                m = re.search(
                    r'href="([^"]*(?:downloads/|download\.php)[^"]*)"[^>]*title="([^"]*)"',
                    row, re.I)
                if not m:
                    continue
                link = html_mod.unescape(m.group(1).strip())
                fname = html_mod.unescape(m.group(2).strip())
                if not link.startswith("http"):
                    link = SITE + (link if link.startswith("/") else "/" + link)
                dm = re.search(r'attachment-date">\s*([^<]*?)\s*<', row)
                sm = re.search(r'attachment-size">\s*([^<]*?)\s*<', row)
                nm = re.search(r'attachment-downloads">\s*([^<]*?)\s*<', row)
                date = html_mod.unescape(dm.group(1).strip()) if dm else ""
                size = html_mod.unescape(sm.group(1).strip()) if sm else ""
                dl = html_mod.unescape(nm.group(1).strip()) if nm else ""
                is_auto = "download.php" in link or "LatestVersion" in fname
                downloads.append({
                    "filename": fname or "下载",
                    "link": link,
                    "date": date,
                    "size": size,
                    "downloads": dl,
                    "type": "自动更新版" if is_auto else "独立版",
                })

            # 元信息
            text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", html_mod.unescape(text))
            mm = re.search(r"(\d+)\s*Options", text)
            options = int(mm.group(1)) if mm else 0
            mv = re.search(r"Game Version:\s*(\S+)", text)
            version = mv.group(1) if mv else ""
            mu = re.search(r"Last Updated:\s*(\S+)", text)
            updated = mu.group(1) if mu else ""

            title_m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.S | re.I)
            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
            if not title:
                title = url.rstrip("/").split("/")[-1].replace("-", " ").title()

            return {
                "ok": True,
                "title": title,
                "version": version,
                "updated": updated,
                "options": options,
                "url": url,
                "downloads": downloads,
            }
        except Exception as e:
            return {"ok": False, "error": "获取详情失败: %s" % e}

    def get_download_state(self):
        return dict(self._download_state)

    def download_trainer(self, url: str, filename: str, game_name="", options=0,
                         version="", detail_url="", game_id=""):
        """下载修改器，归入指定游戏（game_id）或按游戏名智能归入/新建"""
        self._download_state = {"active": True, "percent": 0, "filename": filename,
                                "done": False, "error": ""}
        # 下载前先确定归属游戏
        src = detail_url or (SITE + "/" if url.startswith(SITE) else "")
        gid = game_id or self._find_or_create_game(game_name or filename, src)["game_id"]
        try:
            safe = _safe_name(filename)
            if not safe.lower().endswith((".exe", ".zip")):
                safe += ".exe"
            dest = TRAINERS_DIR / safe
            with requests.get(url, headers=HEADERS, stream=True, timeout=180) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                got = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            got += len(chunk)
                            if total:
                                self._download_state["percent"] = min(99, int(got * 100 / total))
            self._download_state["percent"] = 100

            # 若解压后是 zip，自动解压并注册 exe
            if dest.suffix.lower() == ".zip":
                try:
                    ddir = TRAINERS_DIR / _safe_name(Path(safe).stem)
                    ddir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(dest, "r") as z:
                        for member in z.namelist():
                            if member.endswith("/"):
                                continue
                            target = (ddir / member).resolve()
                            if ddir.resolve() not in target.parents:
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(member) as fs, open(target, "wb") as fd:
                                shutil.copyfileobj(fs, fd)
                    exes = [p for p in ddir.rglob("*") if p.suffix.lower() == ".exe"]
                    reg_target = max(exes, key=lambda p: p.stat().st_size) if exes else dest
                except Exception:
                    reg_target = dest
            else:
                reg_target = dest

            res = self._register_file(
                reg_target,
                game_id=gid,
                name=game_name or _safe_name(Path(safe).stem),
                source_url=detail_url or SITE,
                options=options,
                version=version,
            )
            self._download_state.update({"active": False, "done": True, "percent": 100})
            return {"ok": True, "result": res, "path": str(reg_target)}
        except Exception as e:
            self._download_state.update({"active": False, "error": str(e)})
            return {"ok": False, "error": str(e)}

    # ---------- 更新检测 ----------
    def check_updates(self):
        """对每个有来源的修改器，重新抓详情页比对 Last Updated"""
        lib = self._load_library()
        updated = []
        for item in lib:
            url = item.get("source_url", "")
            if not url.startswith(SITE) or "/trainer/" not in url:
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                text = re.sub(r"(?s)<[^>]+>", " ", r.text)
                text = re.sub(r"\s+", " ", html_mod.unescape(text))
                m = re.search(r"Last Updated:\s*(\S+)", text)
                if m:
                    remote = m.group(1)
                    item["remote_updated"] = remote
                    item["last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if item.get("added", "")[:10].replace("-", ".") < remote:
                        updated.append(item["id"])
            except Exception:
                pass
        self._save_library(lib)
        cfg = self.get_config()
        cfg["last_update_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save_config(cfg)
        return {"ok": True, "has_update": updated, "library": self.get_library()}

    # ---------- Mod 管理 ----------
    def _mods_file(self, trainer_id: str):
        return DATA / ("mods_%s.json" % trainer_id)

    def _load_mods(self, trainer_id: str):
        f = self._mods_file(trainer_id)
        if f.exists():
            try:
                data = json.loads(f.read_text("utf-8"))
                if not isinstance(data, list):
                    return []
                # installed 只由 install_names 决定；顺便兜底纠正历史脏数据
                dirty = False
                for m in data:
                    if not isinstance(m, dict):
                        continue
                    want = bool(m.get("install_names"))
                    if bool(m.get("installed")) != want:
                        m["installed"] = want
                        dirty = True
                if dirty:
                    self._save_mods(trainer_id, data)
                return data
            except Exception:
                return []
        return []

    def _migrate_mod_installed_flags(self):
        """启动时一次性归一所有 mods_*.json：installed = bool(install_names)。"""
        try:
            for f in DATA.glob("mods_*.json"):
                try:
                    data = json.loads(f.read_text("utf-8"))
                    if not isinstance(data, list):
                        continue
                    dirty = False
                    for m in data:
                        if not isinstance(m, dict):
                            continue
                        want = bool(m.get("install_names"))
                        if bool(m.get("installed")) != want:
                            m["installed"] = want
                            dirty = True
                    if dirty:
                        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
                except Exception:
                    continue
        except Exception:
            pass

    def _save_mods(self, trainer_id: str, mods):
        self._mods_file(trainer_id).write_text(
            json.dumps(mods, ensure_ascii=False, indent=2), "utf-8")

    def mod_search_links(self, game_name: str):
        """生成三个 mod 站的搜索直达链接（在浏览器打开，不依赖站内 API）"""
        q = (game_name or "").strip()
        if not q:
            return []
        enc = urllib.parse.quote_plus(q)
        return [
            {"site": "GameBanana", "url": "https://gamebanana.com/mods/search?game=%s" % enc,
             "note": "社区 mod 库，资源最多"},
            {"site": "Nexus Mods", "url": "https://www.nexusmods.com/search/games?gkey=%s" % enc,
             "note": "老牌 mod 站，需自行确认游戏条目"},
            {"site": "Steam 创意工坊", "url": "https://steamcommunity.com/workshop/browse/?searchtext=%s" % enc,
             "note": "Steam 游戏 mod，需选对应游戏"},
        ]

    def get_mods(self, trainer_id: str):
        items = self._load_mods(trainer_id)
        for m in items:
            self._fill_added(m, str(self._mods_file(trainer_id)))
        return {"ok": True, "items": items}

    def get_all_mods(self):
        """汇总每个游戏实体的 mod，供 Mod 管理页一次加载"""
        out = []
        for g in self._load_games():
            mods = self._load_mods(g["id"])
            for m in mods:
                self._fill_added(m, str(self._mods_file(g["id"])))
            out.append({
                "id": g["id"],
                "name": g.get("name", ""),
                "added": g.get("added", ""),
                "trainer_count": len(mods),
                "mods": mods,
            })
        return {"ok": True, "items": out}

    def get_game_hub(self):
        """按游戏实体聚合：游戏信息 + 其下所有修改器 + mod 列表，一次返回供游戏库页使用"""
        lib = self._load_library()
        out = []
        for g in self._load_games():
            trainers = []
            for t in lib:
                if t.get("game_id") != g["id"]:
                    continue
                self._fill_added(t)
                trainers.append({
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "version": t.get("version", ""),
                    "filename": t.get("filename", ""),
                    "path": t.get("path", ""),
                    "source_url": t.get("source_url", ""),
                    "options": t.get("options", 0),
                    "size": t.get("size", 0),
                    "added": t.get("added", ""),
                    "last_launch": t.get("last_launch", ""),
                })
            trainers.sort(key=lambda x: x.get("added", ""), reverse=True)
            mods = self._load_mods(g["id"])
            for m in mods:
                self._fill_added(m, str(self._mods_file(g["id"])))
            out.append({
                "id": g["id"],
                "name": g.get("name", ""),
                "exe_path": g.get("exe_path", ""),
                "mod_dir": g.get("mod_dir", ""),
                "added": g.get("added", ""),
                "last_launch": g.get("last_launch", "") or max(
                    [t.get("last_launch", "") for t in trainers] or [""]),
                "trainers": trainers,
                "mods": mods,
            })
        out.sort(key=lambda x: x.get("added", ""), reverse=True)
        return {"ok": True, "items": out}

    # ---------- Mod 安装到游戏目录 / 安全卸载 ----------
    def is_game_running(self, game_id: str):
        """检测游戏本体进程是否在运行（删除 mod 前的安全检查）"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        exe = g.get("exe_path", "") if g else ""
        if not exe:
            return {"ok": True, "running": False, "process": ""}
        name = Path(exe).name
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq %s" % name],
                capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            running = name.lower() in (out.stdout or "").lower()
            return {"ok": True, "running": running, "process": name}
        except Exception:
            return {"ok": True, "running": False, "process": name}

    def _uninstall_files(self, game_id: str, mod_entry: dict):
        """只移除本工具记录安装的文件 / 目录，带路径逃逸校验。返回已移除的名称。"""
        md_s = mod_entry.get("install_dir", "")
        if not md_s:
            games = self._load_games()
            g = next((x for x in games if x.get("id") == game_id), None)
            md_s = g.get("mod_dir", "") if g else ""
        if not md_s or not Path(md_s).is_dir():
            return []
        try:
            md = Path(md_s).resolve()
        except Exception:
            return []
        removed = []
        for name in mod_entry.get("install_names", []):
            # 只接受纯文件或目录名，拒绝任何路径分隔符 / 相对路径
            if not isinstance(name, str) or not name or name in (".", ".."):
                continue
            if "/" in name or "\\" in name:
                continue
            p = md / name
            try:
                rp = p.resolve()
            except Exception:
                continue
            if rp == md or md not in rp.parents:   # 必须在 mod 目录内部
                continue
            try:
                if rp.is_dir():
                    shutil.rmtree(str(rp))
                elif rp.is_file():
                    rp.unlink()
                else:
                    continue
                removed.append(name)
            except Exception:
                pass
        return removed

    def _safe_install_name(self, mod_dir: Path, filename: str, mod_id: str):
        """生成不覆盖已有文件的安装名"""
        candidate = _safe_name(filename)
        if not (mod_dir / candidate).exists():
            return candidate
        stem, ext = os.path.splitext(candidate)
        return "%s_TH%s%s" % (stem, mod_id[-6:], ext)

    def install_mod(self, game_id: str, mod_id: str):
        """把 mod 的本地文件安装到游戏 mod 目录；已安装则先卸载旧文件。"""
        games = self._load_games()
        g = next((x for x in games if x.get("id") == game_id), None)
        if not g:
            return {"ok": False, "error": "未找到游戏"}
        mod_dir = g.get("mod_dir", "")
        if not mod_dir or not Path(mod_dir).is_dir():
            return {"ok": False, "error": "请先设置该游戏的 Mod 安装目录"}
        mods = self._load_mods(game_id)
        m = next((x for x in mods if x.get("id") == mod_id), None)
        if not m:
            return {"ok": False, "error": "未找到 Mod"}
        if m.get("source") == "link" or not m.get("path"):
            return {"ok": False, "error": "该 Mod 只有链接，没有本地文件，请先下载或导入文件"}
        src = Path(m.get("path", ""))
        if not src.exists():
            return {"ok": False, "error": "本地文件不存在"}
        # 先清掉旧安装，避免重复堆积
        self._uninstall_files(game_id, m)
        md = Path(mod_dir).resolve()
        names = []
        mode = "file"
        subdir = "_TH_%s" % mod_id[-8:]
        try:
            if src.is_dir() or (src.suffix.lower() == ".zip"):
                # zip / 解压目录统一装进独立子目录，卸载时可整块移除
                dest = md / subdir
                if dest.exists():
                    shutil.rmtree(str(dest))
                dest.mkdir(parents=True, exist_ok=True)
                if src.suffix.lower() == ".zip":
                    with zipfile.ZipFile(str(src), "r") as z:
                        for member in z.namelist():
                            if member.endswith("/"):
                                continue
                            leaf = _safe_name(Path(member).name)
                            if not leaf:
                                continue
                            target = (dest / leaf).resolve()
                            if dest.resolve() not in target.parents:
                                continue
                            with z.open(member) as fs, open(str(target), "wb") as fd:
                                shutil.copyfileobj(fs, fd)
                else:
                    for p in src.rglob("*"):
                        if not p.is_file():
                            continue
                        target = (dest / _safe_name(p.name)).resolve()
                        if dest.resolve() not in target.parents:
                            continue
                        shutil.copy2(str(p), str(target))
                names = [subdir]
                mode = "folder"
            else:
                name = self._safe_install_name(md, src.name, mod_id)
                shutil.copy2(str(src), str(md / name))
                names = [name]
        except Exception as e:
            return {"ok": False, "error": "安装失败: %s" % e}
        m["install_names"] = names
        m["install_dir"] = str(md)
        m["install_mode"] = mode
        m["installed"] = True
        m["install_error"] = ""
        self._save_mods(game_id, mods)
        return {"ok": True, "names": names, "dir": str(md), "mode": mode}

    def uninstall_mod(self, game_id: str, mod_id: str):
        """从游戏目录移除该 mod，但保留列表记录"""
        mods = self._load_mods(game_id)
        m = next((x for x in mods if x.get("id") == mod_id), None)
        if not m:
            return {"ok": False, "error": "未找到 Mod"}
        if not m.get("install_names"):
            return {"ok": True, "removed": [], "msg": "该 Mod 未安装到游戏目录"}
        removed = self._uninstall_files(game_id, m)
        m["install_names"] = []
        m["install_dir"] = ""
        m["installed"] = False
        self._save_mods(game_id, mods)
        return {"ok": True, "removed": removed}

    def add_mod_link(self, trainer_id: str, name: str, url: str, note=""):
        """添加一个 mod 条目（来源链接，不自动下载）"""
        mods = self._load_mods(trainer_id)
        entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": _safe_name(name or "mod"),
            "url": url,
            "note": note,
            "source": "link",
            "path": "",
            "installed": False,
            "install_names": [],
            "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        mods.append(entry)
        self._save_mods(trainer_id, mods)
        return {"ok": True, "item": entry}

    def import_mod_files(self, trainer_id: str, file_paths):
        """把本地 mod 文件复制到 data/mods/<trainer_id>/ 并登记"""
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        dest_dir = MODS_DIR / trainer_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        mods = self._load_mods(trainer_id)
        added = []
        for src in file_paths:
            src = Path(src)
            if not src.exists():
                continue
            dest = dest_dir / _safe_name(src.name)
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            entry = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f") + str(len(added)),
                "name": dest.name,
                "url": "",
                "note": "",
                "source": "local",
                "path": str(dest.resolve()),
                "size": dest.stat().st_size,
                "installed": False,
                "install_names": [],
                "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            mods.append(entry)
            added.append(entry)
        self._save_mods(trainer_id, mods)
        # 若该游戏设置了 mod 目录，自动安装到游戏目录使其生效
        game = next((x for x in self._load_games() if x.get("id") == trainer_id), None)
        if game and game.get("mod_dir") and Path(game["mod_dir"]).is_dir():
            for entry in added:
                try:
                    res = self.install_mod(trainer_id, entry["id"])
                    entry["installed"] = bool(res.get("ok"))
                    entry["install_error"] = res.get("error", "")
                    if res.get("ok"):
                        entry["install_names"] = res.get("names", [])
                        entry["install_dir"] = res.get("dir", "")
                        entry["install_mode"] = res.get("mode", "")
                except Exception as e:
                    entry["installed"] = False
                    entry["install_error"] = str(e)
            self._save_mods(trainer_id, mods)
        return {"ok": True, "items": added}

    def get_mod_download_state(self):
        return dict(self._mod_download_state)

    def download_mod(self, trainer_id: str, url: str, name: str, note=""):
        """下载 mod 直链到 data/mods/<trainer_id>/ 并登记。zip 自动解压。"""
        if not url.startswith("http"):
            return {"ok": False, "error": "仅支持 http(s) 直链"}
        self._mod_download_state = {"active": True, "percent": 0,
                                    "filename": name, "done": False, "error": ""}
        try:
            dest_dir = MODS_DIR / trainer_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            safe = _safe_name(name)
            if not re.search(r"\.(zip|rar|7z|exe|dll|lua|asi|pak|txt|json)$", safe, re.I):
                safe += ".zip"
            dest = dest_dir / safe
            with requests.get(url, headers=HEADERS, stream=True, timeout=180) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                got = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            got += len(chunk)
                            if total:
                                self._mod_download_state["percent"] = min(99, int(got * 100 / total))
            final = dest
            if dest.suffix.lower() == ".zip":
                try:
                    ddir = dest_dir / _safe_name(dest.stem)
                    ddir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(dest, "r") as z:
                        for member in z.namelist():
                            if member.endswith("/"):
                                continue
                            target = (ddir / member).resolve()
                            if ddir.resolve() not in target.parents:
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(member) as fs, open(target, "wb") as fd:
                                shutil.copyfileobj(fs, fd)
                    final = ddir
                except Exception:
                    pass  # 非标准 zip 保留原文件
            mods = self._load_mods(trainer_id)
            entry = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "name": _safe_name(name),
                "url": url,
                "note": note,
                "source": "download",
                "path": str(final.resolve()),
                "size": (final.stat().st_size if final.is_file() else 0),
                "installed": False,
                "install_names": [],
                "added": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            mods.append(entry)
            self._save_mods(trainer_id, mods)
            # 自动安装到游戏目录
            game = next((x for x in self._load_games() if x.get("id") == trainer_id), None)
            if game and game.get("mod_dir") and Path(game["mod_dir"]).is_dir():
                try:
                    res = self.install_mod(trainer_id, entry["id"])
                    entry["installed"] = bool(res.get("ok"))
                    entry["install_error"] = res.get("error", "")
                    if res.get("ok"):
                        entry["install_names"] = res.get("names", [])
                        entry["install_dir"] = res.get("dir", "")
                        entry["install_mode"] = res.get("mode", "")
                except Exception as e:
                    entry["installed"] = False
                    entry["install_error"] = str(e)
                self._save_mods(trainer_id, mods)
            self._mod_download_state.update({"active": False, "done": True, "percent": 100})
            return {"ok": True, "item": entry}
        except Exception as e:
            self._mod_download_state.update({"active": False, "error": str(e)})
            return {"ok": False, "error": str(e)}

    def rename_mod(self, trainer_id: str, mod_id: str, name: str):
        """重命名 Mod 的显示名称。只改记录里的 name，不改实际文件名、
        path 与 install_names——避免破坏游戏目录里的安装和工具内备份引用。"""
        name = (name or "").strip()[:120]
        if not name:
            return {"ok": False, "error": "名称不能为空"}
        mods = self._load_mods(trainer_id)
        m = next((x for x in mods if x.get("id") == mod_id), None)
        if not m:
            return {"ok": False, "error": "未找到 Mod"}
        old = m.get("name", "")
        m["name"] = name
        self._save_mods(trainer_id, mods)
        return {"ok": True, "name": name, "old_name": old}

    def remove_mod(self, trainer_id: str, mod_id: str, force=False):
        """删除 Mod 记录；若已安装到游戏目录，先安全移除游戏目录里的文件。
        默认在游戏本体运行时拒绝删除（避免影响游戏体验），force=True 可跳过。"""
        mods = self._load_mods(trainer_id)
        m = next((x for x in mods if x.get("id") == mod_id), None)
        if not m:
            return {"ok": False, "error": "未找到 Mod"}
        uninstalled = []
        if m.get("install_names"):
            if not force:
                running = self.is_game_running(trainer_id)
                if running.get("running"):
                    return {"ok": False,
                            "error": "游戏正在运行，请先关闭游戏再删除 Mod（避免影响游戏体验）"}
            uninstalled = self._uninstall_files(trainer_id, m)
        mods = [x for x in mods if x.get("id") != mod_id]
        self._save_mods(trainer_id, mods)
        return {"ok": True, "uninstalled": uninstalled}

    def cleanup_orphan_backups(self, game_id: str):
        """清理工具内已无记录引用的 mod 备份文件（例如删除记录后残留的副本）。
        只删 data/mods/<game_id> 下没有被任何 mod 条目 path 引用的文件，
        绝不碰游戏目录。"""
        base = MODS_DIR / game_id
        if not base.is_dir():
            return {"ok": True, "removed": [], "msg": "没有备份目录"}
        referenced = set()
        for m in self._load_mods(game_id):
            p = m.get("path", "")
            if p:
                try:
                    referenced.add(str(Path(p).resolve()))
                except Exception:
                    pass
        removed = []
        for item in base.iterdir():
            try:
                rp = str(item.resolve())
            except Exception:
                continue
            if rp in referenced:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(str(item))
                elif item.is_file():
                    item.unlink()
                else:
                    continue
                removed.append(item.name)
            except Exception:
                pass
        return {"ok": True, "removed": removed}

    def open_mod_path(self, trainer_id: str, mod_id: str):
        """打开 mod 文件所在目录；mod_id='__dir__' 时打开游戏 mod 安装目录"""
        if mod_id == "__dir__":
            games = self._load_games()
            g = next((x for x in games if x.get("id") == trainer_id), None)
            target = Path(g.get("mod_dir", "")) if g and g.get("mod_dir") else MODS_DIR / trainer_id
            try:
                os.startfile(str(target))
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        mod = next((m for m in self._load_mods(trainer_id) if m.get("id") == mod_id), None)
        if not mod:
            return {"ok": False, "error": "未找到"}
        p = Path(mod.get("path", "")) if mod.get("path") else MODS_DIR / trainer_id
        if p.is_file():
            p = p.parent
        try:
            os.startfile(str(p))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def file_sha256(self, path: str):
        """计算文件 SHA-256，供用户核对第三方文件"""
        import hashlib
        try:
            p = Path(path)
            if not p.exists():
                return {"ok": False, "error": "文件不存在"}
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return {"ok": True, "hash": h.hexdigest()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_url(self, url: str):
        try:
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_app_info(self):
        return {
            "version": "1.6.1",
            "trainer_dir": str(TRAINERS_DIR),
            "library_count": len(self._load_library()),
        }
