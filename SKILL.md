---
name: 影刀
description: "影刀 RPA 调度技能。通过 TASKS.md 回答自动化能力清单；通过 python scripts/rpa.py 启动任务、查询进度、停止任务、查看运行记录。当用户需要了解自动化能力、启动影刀任务、查看运行状态、停止自动化任务时使用。"
---

# 影刀 RPA 自动化技能


**执行约定**

- 自动化能力问答优先读取 `TASKS.md`，不要为了回答「可以做什么」调用脚本。
- 启动、查询、停止、查看历史、查看机器人状态时，所有命令在技能根目录下执行。
- 脚本参数为**单行 JSON**，必须包含 `"action"` 字段。

### 跨平台调用方式

| 方式 | 命令 | 适用平台 |
|------|------|----------|
| 直接传参 | `python scripts/rpa.py '{"action":"robots"}'` | Linux / macOS (bash/zsh) |
| **文件传参** ⭐ | `python scripts/rpa.py --file tmp.json` | **Windows / 所有平台** |

> **macOS/Linux 注意**: 若系统默认没有 `python` 命令，使用 `python3` 替代。脚本本身不依赖特定 Python 版本名。
| stdin 传参 | `echo '...' \| python scripts/rpa.py --stdin` | 所有平台 |

**Windows (PowerShell) 必须使用文件传参或 stdin。** PowerShell 会自动剥离命令行中的 JSON 双引号，导致 `parse_argv_json()` 收到乱码。正确做法：

1. 将 JSON 写入临时文件（UTF-8 **不带 BOM**）：
   ```powershell
   $json = '{"action":"start","task_name":"发票报销","biz_params":{"金额":"100"}}'
   $utf8nobom = New-Object System.Text.UTF8Encoding $false
   [System.IO.File]::WriteAllText("tmp_rpa.json", $json, $utf8nobom)
   python scripts/rpa.py --file tmp_rpa.json
   ```

2. 或使用 --stdin：
   ```powershell
   '{"action":"robots"}' | python scripts/rpa.py --stdin
   ```

### 能力清单 `TASKS.md`

当用户询问「影刀可以做什么」「有哪些自动化」「我们部门能用什么」时，直接依据 `TASKS.md` 回答。

- `TASKS.md` 由 `scripts/generate_tasks_md.py` 根据 `scripts/apps_config.json` 生成；新增或修改任务时，先改 `apps_config.json`，再重新生成 `TASKS.md`。
- 多部门任务会在每个适用部门下重复出现，例如「下载报表+做应收表」同时属于运营部、财务部。
- 用户没有说明部门时，先询问部门，或提示可按运营部、财务部、站外部、开发部、智能开发部查询。
- 回答时不要展示 UUID、机器人账号、API Key、`job_uuid` 等内部标识。

### 任务配置 `scripts/apps_config.json`

`start` 依赖此文件。每项以**完整任务名**为键，需填写：

| 字段 | 说明 |
|------|------|
| `uuid` | 影刀应用 UUID（客户端应用详情或调度中心） |
| `dept` | 所属部门，供配置和历史记录使用 |
| `aliases` | 任务常用叫法；用户说别名时，脚本会解析到完整任务名 |
| `direct` | 是否支持脚本直接触发；`true` 才允许调用 `start`，`false` 时按任务配置里的触发说明回复用户 |
| `trigger_desc` | 非脚本直接触发任务的触发方式说明；通常直接写给用户看的说明文字 |
| `trigger_url` | 非脚本直接触发任务的触发链接，例如影刀表单链接 |
| `desc` | 任务说明 |
| `robot_config.target_robots` | 可执行该任务的机器人名称列表（与影刀客户端中名称一致） |
| `params` | 参数列表：`name`（传给影刀）、`label`（参数含义，AI 展示用）、`type`（参数类型，AI 收集行为的提示）、`enum`（可选枚举值列表，限定用户只能从列表中选一个）、`required` |

**params 可选字段：**

| 字段 | 说明 |
|------|------|
| `name` | 传给影刀 API 的参数名 |
| `label` | 参数含义，AI 向用户解释时用 |
| `type` | `text`：普通文本；`file_url`：文件上传转 URL |
| `enum` | 可选，限定值列表。用户输入必须从列表中**精确匹配**一个值，不允许增删改字 |
| `required` | 是否必填 |

结构参考 `scripts/apps_config.example.json`。填好 `uuid` 与机器人名称后 `start` 才能成功。新增或修改任务后执行 `python scripts/generate_tasks_md.py`，保证用户看到的能力清单与实际配置一致。

### 文件上传 `scripts/upload_file.py`

当任务参数含有 `type: "file_url"` 时，使用此脚本将用户提供的本地文件转为公网下载 URL：

```bash
# 上传并获取 URL（默认 tmpfiles.org，约数周有效）
python scripts/upload_file.py "<文件路径>" --quiet

# JSON 输出
python scripts/upload_file.py "<文件路径>" --json

# 备用服务 file.io
python scripts/upload_file.py "<文件路径>" --service fileio
```

纯标准库，无外部依赖。

### 机器人清单 `scripts/robots_config.json`

`robots` 动作用这个文件查看全部机器人状态。文件内容是机器人 `accountName` 数组，例如：

```json
[
  "BotA@linenchic",
  "BotB@linenchic"
]
```

如果该文件不存在或为空，脚本会回退到 `apps_config.json` 中各任务的 `robot_config.target_robots` 汇总。启动任务时仍以任务自己的 `robot_config.target_robots` 为准，不使用全局清单放宽可执行范围。

---

## 全局规则

1. **对用户**：解释或确认参数时参考 `label`，不要使用 `name` 等技术字段名。
2. **对用户**：不要展示 API Key、应用 UUID、`job_uuid` 等内部标识。
3. **任务名称**：使用 `apps_config.json` 中的**完整任务名**。
4. **全公司共用历史**：仅提供任务名且存在多条记录时，脚本会列出候选启动时间，**必须让用户确认启动时间**后再查询/停止。
5. **启动时间**：启动成功时脚本会输出「启动时间」；查询/停止时优先让用户提供该时间（`started_at`）。
6. **机器人状态**：启动任务时直接调用 `start`，脚本会自动选择空闲机器人、提示排队或返回离线；用户单独询问机器人在线情况时，调用 `robots`。

---

## action 速查

| action | 用途 | 示例参数 |
|--------|------|----------|
| `start` | 启动任务（按机器人状态选机派发） | `{"action":"start","task_name":"发票报销","biz_params":{...}}` |
| `query` | 查询运行结果 | `{"action":"query","task_name":"发票报销","started_at":"2026年05月19日 14:30:25"}` |
| `stop` | 停止任务 | `{"action":"stop","task_name":"发票报销","started_at":"..."}` |
| `history` | 近期运行记录 | `{"action":"history","task_name":"..."}` 或 `{"action":"history","dept":"财务部"}` |
| `robots` | 查看全部机器人状态 | `{"action":"robots"}` |

---

## 场景 1：查看自动化能力清单

**触发**：用户问「你能做什么」「有哪些自动化」「我们部门能用什么」等。

1. **确认部门**；未说明则先向用户确认，不要直接罗列全量任务。
2. 读取 `TASKS.md` 中对应部门的任务清单。
3. 整理输出回复用户（任务名、常用叫法、用途、所需信息、触发方式）。
4. 多部门任务要出现在每个适用部门中；例如财务部和运营部都应包含「下载报表+做应收表」。
5. 引导用户说出完整任务名即可启动。

---

## 场景 2：启动自动化任务

**流程（不可跳步）**

### A. 明确任务名（完整任务名或常用叫法）

### B. 查询参数并确认

1. 根据 `apps_config.json` 查看任务的完整 `params` 定义。
2. 按参数逐项向用户确认（使用 `label` 字段解释含义，不要使用 `name`）。
3. 参数类型处理：
   - **`type: "text"`**：直接向用户询问，收集字符串值。
     - 如有 `enum` 字段：向用户展示可选项列表，用户输入必须与 `enum` 中某个值**逐字完全一致**，不能多字少字或改字。不匹配时拒绝并提示重新选择。
   - **`type: "file_url"`**：告诉用户需要上传文件；请用户发送文件后，执行 `python scripts/upload_file.py "<文件路径>" --quiet` 获取公网 URL；将 URL 作为该参数的值。
     - 入站文件路径因平台不同：
       - **Windows**: `C:\Users\Administrator\.openclaw\media\inbound\`
       - **macOS/Linux**: `~/.openclaw/media/inbound/`
     - 如果默认路径找不到，用全局搜索（`Get-ChildItem -Recurse` 或 `find`）。
4. 只有 `apps_config.json` 中 `direct: true` 的任务才调用 `start`；其他任务按 `trigger_desc` 引导用户，不要调用 `start`。
5. 必填参数齐全前**禁止**调用 `start`。

### C. 确认机器人状态

不需要先单独查询机器人状态。调用 `start` 后，脚本会自动选择空闲机器人、提示排队，或在负责该任务的机器人全部离线时拒绝启动并提醒用户开启对应电脑。

### D. 启动

**Linux/macOS：**
`python scripts/rpa.py '{"action":"start","task_name":"{{task_name}}","biz_params":{{biz_params}}}'`

**Windows (PowerShell)：**
```powershell
$json = '{"action":"start","task_name":"{{task_name}}","biz_params":{{biz_params}}}'
$utf8nobom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("tmp_rpa.json", $json, $utf8nobom)
python scripts/rpa.py --file tmp_rpa.json
```

成功时转述状态并**明确告知启动时间与运行机器人**，不要念出内部 ID。

---

## 场景 3：查询任务运行状态

1. 确认 `task_name`；必要时 `dept`、`started_at`。
2. 不确定哪一次时：`python scripts/rpa.py '{"action":"history","task_name":"..."}'`
3. 查询：`python scripts/rpa.py '{"action":"query","task_name":"...","started_at":"..."}'`
4. 多条候选时展示列表，请用户确认启动时间后重试。

---

## 场景 4：停止自动化任务

1. 确认任务名与启动时间（规则同场景 3）。
2. `python scripts/rpa.py '{"action":"stop","task_name":"...","started_at":"..."}'`
3. 多条同名记录时**必须**带 `started_at`。

---

## 场景 5：查看机器人在线情况

**触发**：用户问「机器人在线吗」「有哪些电脑空闲」「全部机器人状态」等。

执行：`python scripts/rpa.py '{"action":"robots"}'`

只转述机器人名称和在线/空闲/运行状态，不启动任何任务。
