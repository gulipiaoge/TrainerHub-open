"""把本地代码同步到 GitHub 私有仓库（gulipiaoge/TrainerHub）。

为什么不用 git push：
  本地环境有 HTTPS 中间人代理，git 的 schannel 证书验证会报
  CRYPT_E_NO_REVOCATION_CHECK，直接 push 不通。改用 GitHub REST API，
  只比对有变化的文件再上传，稳定可靠。

用法：
  .venv/Scripts/python.exe sync_github.py ["提交说明"]

凭证：从 ~/.git-credentials 读取 token（不在脚本里明文保存）。
"""
import sys
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
import ssl

OWNER = "gulipiaoge"
REPO = "TrainerHub"
BRANCH = "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/"

# 需要同步的文件（与 .gitignore 对应；data/ .venv/ 等不入库）
FILES = [
    ".gitignore",
    "app.py",
    "backend.py",
    "icon.ico",
    "launch.bat",
    "sync_github.py",
    "web/app.js",
    "web/index.html",
    "web/style.css",
    "启动器.bat",
]


def read_token():
    """从 git 凭证文件读取 github.com 的 token。"""
    import os
    cred = os.path.join(os.path.expanduser("~"), ".git-credentials")
    with open(cred, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "github.com" in line and "@" in line:
                # 形如 https://user:token@github.com
                return line.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1]
    raise RuntimeError("未在 ~/.git-credentials 找到 github.com 凭证")


def make_ctx():
    """本地代理做中间人，跳过证书验证（仅用于此内部同步脚本）。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def request(url, token, ctx, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": "token " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "TrainerHub-Backup",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "同步 TrainerHub 代码"
    token = read_token()
    ctx = make_ctx()

    changed = 0
    for path in FILES:
        try:
            local = open(path, "rb").read()
        except FileNotFoundError:
            print("跳过（本地不存在）:", path)
            continue

        remote_sha = None
        try:
            info = request(API + urllib.parse.quote(path), token, ctx)
            remote_content = base64.b64decode(info.get("content", ""))
            if remote_content == local:
                print("unchanged", path)
                continue
            remote_sha = info.get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

        payload = {
            "message": msg,
            "content": base64.b64encode(local).decode(),
            "branch": BRANCH,
        }
        if remote_sha:
            payload["sha"] = remote_sha
        request(API + urllib.parse.quote(path), token, ctx, "PUT", payload)
        print("uploaded ", path, f"({len(local)} bytes)")
        changed += 1

    print(f"\n同步完成：{changed} 个文件有更新 / 共 {len(FILES)} 个")


if __name__ == "__main__":
    main()
