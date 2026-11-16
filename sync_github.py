"""把本地 git 历史同步到 GitHub 仓库（gulipiaoge/TrainerHub-open）。

为什么不用 git push：
  本地环境有 HTTPS 中间人代理，git 的 schannel 证书验证会报
  CRYPT_E_NO_REVOCATION_CHECK，直接 push 不通。改用 GitHub REST API。

同步方式：
  走 git 数据库 API（blob → tree → commit），把**本地完整的提交链**
  映射到远端。内容相同的 blob/tree 天然 sha 相同，GitHub 会自动复用，
  因此每次只需上传真正变化的对象。

  好处：远端提交历史与本地 git 严格一致，sha 相同，
        回滚、对比、"在 GitHub 上看某个版本"全都对得上。

用法：
  .venv/Scripts/python.exe sync_github.py ["提交说明"]

  不带参数时只同步当前已有历史（不新建提交）。
  先在本地 git commit 完成改动，再运行本脚本。

凭证：从 ~/.git-credentials 读取 token（不在脚本里明文保存）。
"""
import base64
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
OWNER = "gulipiaoge"
REPO = "TrainerHub-open"
BRANCH = "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/git"

# 需要纳入同步的路径（与 .gitignore 对应；data/ .venv/ 等不入库）
TRACKED = None  # None = 用 git ls-tree 自动取全部被跟踪文件


def read_token():
    cred = os.path.join(os.path.expanduser("~"), ".git-credentials")
    with open(cred, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "github.com" in line and "@" in line:
                # 形如 https://user:token@github.com
                return line.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1]
    raise RuntimeError("未在 ~/.git-credentials 找到 github.com 凭证")


TOKEN = read_token()
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def api(path, method="GET", data=None):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "token " + TOKEN,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "TrainerHub-Backup",
    })
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise RuntimeError(f"GitHub API {method} {path} -> HTTP {e.code}\n{detail}") from None


def git(*args, binary=False):
    r = subprocess.run(["git"] + list(args), cwd=REPO_ROOT,
                       capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def push_blob(local_sha):
    data = git("cat-file", "blob", local_sha, binary=True)
    return api("/blobs", "POST", {
        "content": base64.b64encode(data).decode(), "encoding": "base64"})["sha"]


def push_tree(local_tree):
    raw = git("ls-tree", "-z", local_tree, binary=True)
    entries = []
    for e in raw.split(b"\x00"):
        if not e:
            continue
        meta, path = e.split(b"\t", 1)
        mode, typ, sha = meta.decode().split()
        if typ == "blob":
            remote_sha = push_blob(sha)
        elif typ == "tree":
            remote_sha = push_tree(sha)
        else:
            continue
        entries.append({"path": path.decode("utf-8"), "mode": mode,
                        "type": typ, "sha": remote_sha})
    return api("/trees", "POST", {"tree": entries})["sha"]


def push_commit(local_sha, parent_remote_sha):
    tree = git("rev-parse", f"{local_sha}^{{tree}}")
    remote_tree = push_tree(tree)
    raw = git("show", "-s", "--format=%an%x00%ae%x00%aI%x00%B", local_sha)
    an, ae, ad, msg = raw.split("\x00", 3)
    payload = {
        "message": msg, "tree": remote_tree,
        "author": {"name": an, "email": ae, "date": ad},
        "committer": {"name": an, "email": ae, "date": ad},
    }
    if parent_remote_sha:
        payload["parents"] = [parent_remote_sha]
    return api("/commits", "POST", payload)["sha"]


def ensure_ref(sha):
    """创建或强制更新 main 引用。"""
    try:
        api(f"/refs/heads/{BRANCH}", "PATCH", {"sha": sha, "force": True})
        return "updated"
    except RuntimeError as e:
        if "Reference does not exist" in str(e):
            api(f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs", "POST",
                {"ref": f"refs/heads/{BRANCH}", "sha": sha})
            return "created"
        raise


def main():
    if len(sys.argv) > 1 and sys.argv[1]:
        print("提示：提交信息由本地 git commit 决定，本脚本只做镜像同步。")
        print("      请用 git commit -m \"说明\" 提交后再运行本脚本。\n")

    shas = [s for s in git("rev-list", "--reverse", "main").split("\n") if s.strip()]
    print(f"本地 main 共 {len(shas)} 个提交，开始映射到 {OWNER}/{REPO}")

    parent = None
    for sha in shas:
        parent = push_commit(sha, parent)
        subj = git("show", "-s", "--format=%s", sha)
        same = "（sha 一致）" if parent == sha else f"（远端 {parent[:10]}）"
        print(f"  {sha[:10]} -> {parent[:10]} {same}  {subj}")

    action = ensure_ref(parent)
    print(f"\n远端 {BRANCH} 引用已{action} -> {parent[:10]}")
    print(f"仓库地址: https://github.com/{OWNER}/{REPO}")


if __name__ == "__main__":
    main()
