"""Generate TASKS.md from apps_config.json."""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(BASE_DIR)
APPS_CONFIG_PATH = os.path.join(BASE_DIR, "apps_config.json")
TASKS_MD_PATH = os.path.join(SKILL_DIR, "TASKS.md")

DEPT_ORDER = ["运营部", "财务部", "站外部", "开发部", "智能开发部", "通用/未分类"]


def split_depts(dept):
    if isinstance(dept, list):
        return [str(d).strip() for d in dept if str(d).strip()]
    if not dept:
        return ["通用/未分类"]
    normalized = str(dept).replace("，", "、").replace(",", "、").replace("/", "、")
    return [d.strip() for d in normalized.split("、") if d.strip()] or ["通用/未分类"]


def trigger_text(info):
    if info.get("direct", True) is True:
        return "脚本直接触发"
    return info.get("trigger_desc") or "该任务不支持脚本直接触发，请按任务说明使用对应触发方式。"


def params_text(info):
    params = info.get("params") or []
    if params:
        parts = []
        for p in params:
            name = p.get("name")
            label = p.get("label")
            ptype = p.get("type", "text")
            display = label or name or ""
            if ptype == "file_url":
                display += "（文件→公网URL）"
            elif name and label and name != label:
                display = f"{name}（{label}）"
            # enum
            enum_vals = p.get("enum")
            if enum_vals:
                display += f" [{" / ".join(enum_vals)}]"
            parts.append(display)
        return "、".join(parts)
    if info.get("direct", True) is True:
        return "无额外参数"
    return "按触发方式填写"


def aliases_text(info):
    aliases = info.get("aliases") or []
    return "、".join(aliases) if aliases else "-"


def render(apps):
    by_dept = {}
    for name, info in apps.items():
        for dept in split_depts(info.get("dept")):
            by_dept.setdefault(dept, []).append((name, info))

    ordered_depts = [d for d in DEPT_ORDER if d in by_dept]
    ordered_depts.extend(d for d in by_dept if d not in ordered_depts)

    lines = [
        "# 影刀自动化任务清单",
        "",
        "<!-- 本文件由 scripts/generate_tasks_md.py 根据 scripts/apps_config.json 生成。新增或修改任务时，请先改 apps_config.json，再重新生成本文档。 -->",
        "",
        "当用户询问「影刀可以做什么」「我们有哪些自动化任务」「某个部门能用什么自动化」时，优先依据本文档回答，不需要调用脚本查询。",
        "",
        "回答时只展示任务名、适用部门、用途、所需信息和触发方式。不要展示 UUID、机器人账号、API Key、job_uuid 等内部信息。",
        "",
        "## 按部门查看",
        "",
    ]

    for dept in ordered_depts:
        lines.extend(
            [
                f"### {dept}",
                "",
                "| 任务名 | 常用叫法 | 用途 | 所需信息 | 触发方式 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for name, info in by_dept[dept]:
            desc = info.get("desc") or "暂无描述"
            lines.append(
                f"| {name} | {aliases_text(info)} | {desc} | {params_text(info)} | {trigger_text(info)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 完整任务索引",
            "",
            "| 任务名 | 适用部门 | 常用叫法 | 触发方式 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for name, info in apps.items():
        lines.append(
            f"| {name} | {'、'.join(split_depts(info.get('dept')))} | {aliases_text(info)} | {trigger_text(info)} |"
        )

    lines.extend(
        [
            "",
            "## 回答口径",
            "",
            "- 用户问某个部门有什么自动化时，只回答该部门下的任务；多部门任务要出现在每个适用部门里。",
            f"- 用户没有说明部门时，先问用户想看哪个部门，或简短说明可按{'、'.join([d for d in DEPT_ORDER if d != '通用/未分类'])}查询。",
            "- 用户想启动任务时，必须使用完整任务名或常用叫法，并按「所需信息」收集参数。",
            "- 只有「脚本直接触发」的任务才调用 `start`；其他触发方式按文档说明引导用户，不要调用 `start`。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    with open(APPS_CONFIG_PATH, "r", encoding="utf-8") as f:
        apps = json.load(f)
    with open(TASKS_MD_PATH, "w", encoding="utf-8") as f:
        f.write(render(apps))


if __name__ == "__main__":
    main()
