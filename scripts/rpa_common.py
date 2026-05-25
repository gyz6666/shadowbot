"""影刀 RPA 核心库：鉴权、机器人、任务派发、历史记录、能力清单"""
import json
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests

# --- 路径与配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_CONFIG_PATH = os.path.join(BASE_DIR, "apps_config.json")
ROBOTS_CONFIG_PATH = os.path.join(BASE_DIR, "robots_config.json")
HISTORY_PATH = os.path.join(BASE_DIR, "task_history.json")
HISTORY_MAX_ENTRIES = 500

AK_ID = os.environ.get("YINGDAO_AK_ID", "V0Gt9upU2ERCNceh@platform")
AK_SECRET = os.environ.get("YINGDAO_AK_SECRET", "4QTdYBfNujgAM30DZ5RE6yeUqnSb9F12")

TOKEN_URL = "https://api.yingdao.com/oapi/token/v2/token/create"
CLIENT_QUERY_URL = "https://api.yingdao.com/oapi/dispatch/v2/client/query"
START_URL = "https://api.yingdao.com/oapi/dispatch/v2/job/start"
JOB_QUERY_URL = "https://api.yingdao.com/oapi/dispatch/v2/job/query"
JOB_STOP_URL = "https://api.yingdao.com/oapi/dispatch/v2/job/stop"


def ensure_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def parse_argv_json():
    if len(sys.argv) < 2:
        return {}
    raw = sys.argv[1].strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


# --- 影刀 API ---
def get_token(timeout=10):
    try:
        res = requests.post(
            TOKEN_URL,
            data={"accessKeyId": AK_ID, "accessKeySecret": AK_SECRET},
            timeout=timeout,
        ).json()
        if res.get("code") == 200:
            return res["data"]["accessToken"]
    except Exception:
        pass
    return None


def api_post(url, token, payload=None, timeout=15):
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        return requests.post(url, json=payload, headers=headers, timeout=timeout).json()
    return requests.post(url, json={}, headers=headers, timeout=timeout).json()


def _collect_configured_robot_names():
    """优先从 robots_config 读取机器人清单，缺省时从 apps_config 汇总。"""
    robots = load_robots_config()
    if robots:
        return robots

    apps = load_apps_config() or {}
    names = []
    for info in apps.values():
        names.extend(info.get("robot_config", {}).get("target_robots", []))
    return list(dict.fromkeys(n for n in names if n))


def query_client_by_account(token, account_name, timeout=10):
    """
    按 accountName 查询单台机器人状态。
    accountName 与 apps_config 中 target_robots 名称一致。
    返回 {"robotName": str, "status": str} 或 None（查询失败/未找到）。
    """
    if not token or not account_name:
        return None
    try:
        res = api_post(
            CLIENT_QUERY_URL,
            token,
            {"accountName": account_name},
            timeout=timeout,
        )
        if res.get("code") != 200:
            return None
        data = res.get("data")
        if not isinstance(data, dict):
            return None
        return {
            "robotName": data.get("robotClientName") or account_name,
            "status": (data.get("status") or "offline").lower(),
        }
    except Exception:
        return None


def get_robots_status_dict(token, robot_names=None):
    """返回 {机器人名称: status}。未指定名称时从 apps_config 汇总。"""
    if not token:
        return {}
    names = robot_names if robot_names is not None else _collect_configured_robot_names()
    result = {}
    for name in names:
        info = query_client_by_account(token, name)
        result[name] = info["status"] if info else "offline"
    return result


def select_robot(token, allowed_robots):
    """按空闲优先、忙碌可排队、全离线则失败，返回 (robot_name, message)。"""
    if not allowed_robots:
        return None, "⚠️ 该任务未配置执行机器人，请联系管理员。"
    try:
        eligible = []
        for name in allowed_robots:
            info = query_client_by_account(token, name)
            if info:
                eligible.append(info)

        if not eligible:
            return None, "⚠️ 负责该任务的机器人目前全部【离线】，请先开启对应电脑并登录影刀客户端。"

        idle = [r for r in eligible if r.get("status") in ("idle", "connected")]
        if idle:
            name = idle[0]["robotName"]
            return name, f"✅ 已在空闲电脑【{name}】上启动，任务将立即执行。"

        busy = [r for r in eligible if r.get("status") in ("running", "allocated")]
        if busy:
            name = busy[0]["robotName"]
            return (
                name,
                f"⏳ 执行电脑【{name}】当前忙碌，任务已提交并将排队，空闲后自动开始。",
            )

        return None, "⚠️ 目标机器人目前均处于离线状态，请先开启对应电脑。"
    except Exception:
        return None, "⚠️ 查询机器人状态异常，请稍后再试。"


def start_application(token, app_info, biz_params, robot_name):
    params = []
    for name, value in biz_params.items():
        params.append({
            "name": name,
            "value": value,
            "type": "str"
        })
    payload = {
        "accountName": robot_name,
        "robotUuid": app_info["uuid"],
        "waitTimeout": "2h",
        "params": params,
    }
    return api_post(START_URL, token, payload, timeout=30)


def query_job(token, job_uuid):
    return api_post(JOB_QUERY_URL, token, {"jobUuid": job_uuid})


def stop_job(token, job_uuid):
    return api_post(JOB_STOP_URL, token, {"jobUuid": job_uuid})


# --- 任务配置 ---
def load_apps_config():
    if not os.path.exists(APPS_CONFIG_PATH):
        return None
    with open(APPS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_robots_config():
    if not os.path.exists(ROBOTS_CONFIG_PATH):
        return []
    try:
        with open(ROBOTS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return list(dict.fromkeys(str(name).strip() for name in data if str(name).strip()))
        if isinstance(data, dict):
            robots = data.get("robots", [])
            if isinstance(robots, list):
                return list(dict.fromkeys(str(name).strip() for name in robots if str(name).strip()))
    except Exception:
        pass
    return []


def resolve_task(config, task_name):
    if not config or not task_name:
        return None, None
    task_name = task_name.strip()
    if task_name in config:
        return task_name, config[task_name]
    normalized_task_name = task_name.lower()
    for official_name, details in config.items():
        aliases = details.get("aliases", [])
        if any(normalized_task_name == str(alias).strip().lower() for alias in aliases):
            return official_name, details
    return None, None


def split_depts(dept):
    """把配置中的部门字符串拆成部门列表，兼容 '运营部、财务部' 和数组写法。"""
    if isinstance(dept, list):
        return [str(d).strip() for d in dept if str(d).strip()]
    if not dept:
        return ["通用/未分类"]
    normalized = str(dept).replace("，", "、").replace(",", "、").replace("/", "、")
    return [d.strip() for d in normalized.split("、") if d.strip()] or ["通用/未分类"]


def is_direct_trigger(app_info):
    return app_info.get("direct", True) is True


def format_trigger_desc(app_info):
    if is_direct_trigger(app_info):
        return "脚本直接触发"
    return app_info.get("trigger_desc") or "该任务不支持脚本直接触发，请按任务说明使用对应触发方式。"


def format_param_label(param):
    req = "必填" if param.get("required") else "选填"
    display = param.get("label") or param.get("name") or "?"
    return f"{display}({req})"


def format_robot_status(status_code):
    status_map = {
        "idle": "🟢 空闲",
        "connected": "🟢 已连接",
        "running": "🟡 运行中",
        "allocated": "🟡 已分配",
        "offline": "🔴 离线",
    }
    return status_map.get((status_code or "offline").lower(), "🔴 未知状态")


def validate_biz_params(app_info, biz_params):
    missing = []
    invalid = []
    for p in app_info.get("params", []):
        name = p["name"]
        val = biz_params.get(name)
        if p.get("required") and (val is None or (isinstance(val, str) and not val.strip())):
            missing.append(format_param_label(p))
            continue
        # enum 校验
        enum_vals = p.get("enum")
        if enum_vals and val is not None:
            if str(val) not in enum_vals:
                invalid.append(
                    f"{format_param_label(p)} 值「{val}」不在允许范围 [{' / '.join(enum_vals)}]"
                )
    if missing:
        return False, f"❌ 缺少必填参数：{'、'.join(missing)}"
    if invalid:
        return False, f"❌ 参数值不合法：{'；'.join(invalid)}"
    return True, None


# --- 运行历史 ---
def load_history_list():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
        if isinstance(history, list):
            return history
        if isinstance(history, dict):
            migrated = []
            for name, val in history.items():
                if isinstance(val, str):
                    migrated.append({"task_name": name, "job_uuid": val, "dept": "未分类"})
                elif isinstance(val, dict):
                    migrated.append(
                        {
                            "task_name": name,
                            "job_uuid": val.get("job_uuid"),
                            "dept": val.get("dept", "未分类"),
                            "robot": val.get("robot", "未知"),
                            "time": val.get("time"),
                            "started_at": val.get("started_at"),
                        }
                    )
            return migrated
    except Exception:
        pass
    return []


def _record_matches_time(record, time_query):
    if not time_query:
        return True
    tq = time_query.strip().replace(" ", "")
    for key in ("started_at", "time"):
        val = (record.get(key) or "").replace(" ", "")
        if tq in val or time_query.strip() in (record.get(key) or ""):
            return True
    return False


def format_history_ambiguity(candidates, action="查询或停止"):
    lines = [
        f"🔍 找到多条运行记录，请补充**启动时间**（复制下方整行时间）后再{action}：",
        "",
    ]
    for i, r in enumerate(candidates[:15], 1):
        lines.append(
            f"  {i}. 【{r.get('task_name')}】| 启动：{r.get('time') or r.get('started_at', '未知')} "
            f"| 机器人：{r.get('robot', '未知')}"
        )
    lines.append("")
    lines.append('示例：{"action": "query", "task_name": "发票报销", "started_at": "2026年05月19日 14:30:25"}')
    return "\n".join(lines)


def resolve_job_record(task_name=None, dept=None, started_at=None):
    records = load_history_list()
    if not records:
        return None, "暂无任务运行历史。"

    candidates = list(reversed(records))
    if task_name:
        task_name = task_name.strip()
        candidates = [r for r in candidates if r.get("task_name") == task_name]
    if dept:
        dept = dept.strip()
        candidates = [r for r in candidates if dept in split_depts(r.get("dept"))]
    if started_at:
        started_at = started_at.strip()
        candidates = [r for r in candidates if _record_matches_time(r, started_at)]

    if not candidates:
        return None, None
    if started_at or len(candidates) == 1:
        return candidates[0], None
    return None, format_history_ambiguity(candidates)


def list_recent_history(dept=None, task_name=None, limit=15):
    records = list(reversed(load_history_list()))
    if dept:
        records = [r for r in records if dept in split_depts(r.get("dept"))]
    if task_name:
        records = [r for r in records if r.get("task_name") == task_name.strip()]
    records = records[:limit]
    if not records:
        return "📋 暂无匹配的运行记录。"
    lines = ["📋 近期任务运行记录（新 → 旧）：", ""]
    for i, r in enumerate(records, 1):
        lines.append(
            f"  {i}. 【{r.get('task_name')}】| {r.get('time') or r.get('started_at', '未知')} "
            f"| 机器人：{r.get('robot', '未知')}"
        )
    lines.append("")
    lines.append("查询/停止时请提供 task_name；多条同名记录请同时提供 started_at。")
    return "\n".join(lines)


def save_task_history(task_name, job_uuid, dept=None, robot=None):
    now = datetime.now()
    record = {
        "task_name": task_name,
        "dept": "、".join(split_depts(dept)),
        "robot": robot or "未知",
        "job_uuid": job_uuid,
        "started_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "time": now.strftime("%Y年%m月%d日 %H:%M:%S"),
    }
    history = load_history_list()
    history.append(record)
    if len(history) > HISTORY_MAX_ENTRIES:
        history = history[-HISTORY_MAX_ENTRIES:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)
    return record


def format_job_status(status_code, remark=""):
    status_map = {
        "created": "🆕 任务已创建，正在排入执行队列。",
        "waiting": "⏳ 任务等待调度中，机器人就绪后将立即开始。",
        "running": "⚙️ 机器人正在执行自动化任务，请稍候…",
        "finish": "✅ 任务已完成！",
        "stopping": "🛑 正在停止任务…",
        "stopped": "⏹️ 任务已停止。",
        "error": f"❌ 任务运行异常。{remark}",
        "skipped": "⏩ 任务已被跳过。",
        "cancel": "🚫 任务已被取消。",
    }
    return status_map.get((status_code or "").lower(), f"当前状态：{status_code}")
