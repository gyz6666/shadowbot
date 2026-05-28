#!/usr/bin/env python3
"""
文件上传脚本 — 将本地文件上传到公网临时托管服务，返回可直接下载的 URL。
供影刀等 RPA 自动化流程使用。

用法:
  python upload_file.py <file_path> [--service tmpfiles|fileio] [--json] [--quiet]

输出:
  --json: JSON 格式 {"ok": true, "url": "...", "service": "..."}
  --quiet: 仅输出 URL（成功时）
  默认: 友好文本
"""

import argparse, json, os, ssl, sys, urllib.request, urllib.error

TMPFILES_API = "https://tmpfiles.org/api/v1/upload"
FILEIO_API = "https://file.io"
TIMEOUT = 60


def _mk_body(file_path):
    boundary = "----FormBoundary" + os.urandom(16).hex()
    with open(file_path, "rb") as f:
        file_data = f.read()
    filename = os.path.basename(file_path)
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += file_data
    body += f"\r\n--{boundary}--\r\n".encode()
    return body, boundary


def upload_tmpfiles(file_path):
    body, boundary = _mk_body(file_path)
    req = urllib.request.Request(
        TMPFILES_API,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as resp:
            raw_body = resp.read().decode()
            result = json.loads(raw_body)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "service": "tmpfiles"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"网络错误: {e.reason}", "service": "tmpfiles"}
    except json.JSONDecodeError:
        return {"ok": False, "error": "服务返回了非 JSON 响应", "service": "tmpfiles"}

    if result.get("status") == "success":
        raw = result["data"]["url"]
        dl = raw.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/", 1)
        return {"ok": True, "url": dl, "service": "tmpfiles", "raw_url": raw}
    return {"ok": False, "error": result.get("message", "未知错误"), "service": "tmpfiles"}


def upload_fileio(file_path):
    body, boundary = _mk_body(file_path)
    req = urllib.request.Request(
        FILEIO_API,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as resp:
            raw_body = resp.read().decode()
            result = json.loads(raw_body)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "service": "fileio"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"网络错误: {e.reason}", "service": "fileio"}
    except json.JSONDecodeError:
        return {"ok": False, "error": "服务返回了非 JSON 响应", "service": "fileio"}

    if result.get("success") and result.get("link"):
        return {"ok": True, "url": result["link"], "service": "fileio"}
    return {"ok": False, "error": result.get("message", "未知错误"), "service": "fileio"}


def main():
    parser = argparse.ArgumentParser(description="上传文件到公网获取 URL")
    parser.add_argument("file", help="本地文件路径")
    parser.add_argument("--service", choices=["tmpfiles", "fileio"], default="tmpfiles")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        result = {"ok": False, "error": f"文件不存在: {args.file}"}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"[ERROR] {result['error']}", file=sys.stderr)
        sys.exit(1)

    uploaders = {"tmpfiles": upload_tmpfiles, "fileio": upload_fileio}
    result = uploaders[args.service](args.file)

    if args.quiet and result["ok"]:
        print(result["url"])
        return
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(f"[OK] 上传成功")
        print(f"  服务: {result['service']}")
        print(f"  URL:  {result['url']}")
    else:
        print(f"[FAIL] {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
