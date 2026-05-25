"""
影刀 RPA 统一入口

用法：python scripts/rpa.py '<单行 JSON>'

action 说明：
  start    - 启动任务（按机器人状态选机派发）
  query    - 查询运行结果（依赖历史记录中的 job_uuid）
  stop     - 停止任务
  history  - 列出近期运行记录
  robots   - 查看全部机器人状态
"""
from rpa_common import (
    ensure_utf8_stdio,
    format_trigger_desc,
    format_job_status,
    get_robots_status_dict,
    get_token,
    is_direct_trigger,
    list_recent_history,
    load_apps_config,
    parse_argv_json,
    resolve_job_record,
    resolve_task,
    save_task_history,
    select_robot,
    start_application,
    query_job,
    stop_job,
    validate_biz_params,
    format_robot_status,
)


def cmd_robots(_args):
    token = get_token()
    if not token:
        print("⚠️ 影刀授权失败，请联系管理员。")
        return
    status_dict = get_robots_status_dict(token)
    if not status_dict:
        print("📡 暂无机器人信息，或接口暂不可用。")
        return
    print("📡 机器人状态：")
    for name, code in sorted(status_dict.items()):
        print(f"  - {name}: {format_robot_status(code)}")


def cmd_history(args):
    dept = (args.get("dept") or "").strip() or None
    task_name = (args.get("task_name") or "").strip() or None
    limit = int(args.get("limit") or 15)
    print(list_recent_history(dept=dept, task_name=task_name, limit=limit))


def cmd_start(args):
    task_name = (args.get("task_name") or "").strip()
    biz_params = dict(args.get("biz_params") or {})

    if not task_name:
        print('❌ 请提供 task_name。示例：{"action":"start","task_name":"发票报销","biz_params":{...}}')
        return

    config = load_apps_config()
    if config is None:
        print("⚠️ 尚未配置自动化任务。")
        return

    official_name, app_info = resolve_task(config, task_name)
    if not app_info:
        print(f"❌ 未找到任务【{task_name}】，请使用能力清单中的完整任务名称。")
        return

    if not is_direct_trigger(app_info):
        msg = f"ℹ️ 【{official_name}】不能通过当前脚本直接启动。\n{format_trigger_desc(app_info)}"
        print(msg)
        return

    ok, err = validate_biz_params(app_info, biz_params)
    if not ok:
        print(err)
        return

    token = get_token()
    if not token:
        print("⚠️ 影刀授权失败，请联系管理员。")
        return

    target_robots = app_info.get("robot_config", {}).get("target_robots", [])
    robot_name, status_msg = select_robot(token, target_robots)
    if not robot_name:
        print(status_msg)
        return

    res = start_application(token, app_info, biz_params, robot_name)
    if res.get("code") == 200:
        job_uuid = res["data"]["jobUuid"]
        dept = app_info.get("dept", "未分类")
        hist = save_task_history(official_name, job_uuid, dept=dept, robot=robot_name)
        print(
            f"🚀 【{official_name}】已成功提交。\n"
            f"🕐 启动时间：{hist['time']}\n"
            f"💻 运行机器人：{hist['robot']}\n"
            f"💡 查询或停止时若有多人同时跑过该任务，请说明上述启动时间。\n"
            f"{status_msg}"
        )
    else:
        print(f"❌ 启动失败：{res.get('msg', '未知错误')}")


def _resolve_record_or_print(args, action_label):
    task_name = (args.get("task_name") or "").strip() or None
    dept = (args.get("dept") or "").strip() or None
    started_at = (args.get("started_at") or "").strip() or None

    if task_name:
        config = load_apps_config()
        official_name, _app_info = resolve_task(config, task_name)
        if official_name:
            task_name = official_name

    if not task_name and not dept and not started_at:
        print(list_recent_history(limit=15))
        if action_label == "stop":
            print("\n请根据上表选择要停止的任务，并提供 task_name 与 started_at。")
        return None

    record, hint = resolve_job_record(task_name=task_name, dept=dept, started_at=started_at)
    if hint:
        print(hint)
        return None
    if not record or not record.get("job_uuid"):
        print(
            f"🔍 未找到匹配的运行记录。"
            f'可先执行：python scripts/rpa.py \'{{"action":"history","task_name":"{task_name or ""}"}}\''
        )
        return None
    return record


def cmd_query(args):
    record = _resolve_record_or_print(args, "query")
    if not record:
        return

    token = get_token()
    if not token:
        print("⚠️ 影刀授权失败，请联系管理员。")
        return

    res = query_job(token, record["job_uuid"])
    if res.get("code") != 200:
        print(f"❌ 查询失败：{res.get('msg', '未知错误')}")
        return

    data = res["data"]
    status = data.get("status")
    remark = data.get("remark", "无")
    run_time = record.get("time") or record.get("started_at")

    print(
        f"关于【{record.get('task_name')}】（{record.get('dept', '未分类')}，启动于 {run_time}）："
    )
    print(format_job_status(status, remark))
    if status and status.lower() == "finish" and data.get("bizResult"):
        print(f"📊 自动化执行结果：{data['bizResult']}")


def cmd_stop(args):
    record = _resolve_record_or_print(args, "stop")
    if not record:
        return

    token = get_token()
    if not token:
        print("⚠️ 影刀授权失败，请稍后再试。")
        return

    res = stop_job(token, record["job_uuid"])
    run_time = record.get("time") or record.get("started_at")
    name = record.get("task_name")

    if res.get("code") == 200:
        print(
            f"🛑 已向【{name}】发送停止指令（{record.get('dept', '未分类')}，"
            f"启动于 {run_time}），正在结束运行…"
        )
    elif "not running" in (res.get("msg") or "").lower():
        print(f"ℹ️ 【{name}】（启动于 {run_time}）当前未在运行，可能已完成或此前已停止。")
    else:
        print(f"❌ 停止失败：{res.get('msg', '未知错误')}")


ACTIONS = {
    "start": cmd_start,
    "query": cmd_query,
    "stop": cmd_stop,
    "history": cmd_history,
    "robots": cmd_robots,
}


def main():
    args = parse_argv_json()
    action = (args.get("action") or "").strip().lower()

    if not action:
        print(
            "❌ 请指定 action：start | query | stop | history | robots\n"
            '示例：python scripts/rpa.py \'{"action":"robots"}\''
        )
        return

    handler = ACTIONS.get(action)
    if not handler:
        print(f"❌ 未知 action：{action}，可选：{', '.join(ACTIONS)}")
        return

    handler(args)


if __name__ == "__main__":
    ensure_utf8_stdio()
    main()
