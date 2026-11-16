# API Sentinel

基于访问日志与资产台账的 API 审计学习项目。使用 FastAPI 提供本地接口、Nginx 记录 JSON 访问日志，Python 脚本匹配台账并导出需要核查的线索。

## 当前能力

- 按请求方法与台账路径模板匹配接口，统计调用次数、HTTP 成功响应与调用方标记。
- 汇总未登记路径的活跃日期、首次及最后出现时间。
- 根据实验规则筛选疑似影子 API、疑似僵尸 API、未知路径访问与疑似异常暴露。
- 导出 `api_inventory.csv`、`unregistered_paths.csv` 和 `findings.csv`。

当前是教学原型。FastAPI 源码中的接口返回模拟业务结果，调度接口为本地学习故意省略鉴权，应仅在本机运行。仓库不包含测试数据、访问日志、测试结果、虚拟环境或 Nginx 可执行程序。

## 文件结构

```text
main.py                 本地 FastAPI 接口源码
api_audit.py            标准库离线审计脚本
nginx/conf/nginx.conf   JSON 日志与代理配置
templates/ledger.csv    资产台账空模板（仅表头）
templates/callers.csv   调用方安全区空模板（仅表头）
requirements.txt       API 服务依赖
```

## 启动本地接口（Windows PowerShell）

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

接口文档：`http://127.0.0.1:8000/docs`。保持此终端运行。

从 [Nginx 官方下载页](https://nginx.org/en/download.html) 下载 Windows 发行版并解压到单独目录。将仓库中的 `nginx/conf/nginx.conf` 复制到发行版的 `conf/nginx.conf`，保留发行版的其他文件。在发行版目录执行：

```powershell
.\nginx.exe -t
Get-Process nginx -ErrorAction SilentlyContinue
```

检查成功且没有运行中的 Nginx 时启动：

```powershell
Start-Process -FilePath ".\nginx.exe" -WindowStyle Hidden
```

已有进程时不重复启动；修改配置后用 `.\nginx.exe -s reload` 加载。通过 `http://127.0.0.1:8080/docs` 发起请求，日志写在该发行版的 `logs/api_access.log`。直接访问 8000 不经过 Nginx。

## 准备分析输入

复制 `templates` 中的两个空模板到自行创建的 `data` 目录，填写实际登记信息；CSV 使用 UTF-8 编码。`data` 已被忽略，不会提交本地业务数据。

资产台账列：`api_id`（唯一编号）、`template`（路径模板）、`method`、`biz`、`zone`、`status`。当前生命周期规则使用“已下线”状态值。模板用 `{参数名}` 表示单个路径段。

调用方映射列：`appid`、`zone`。当前实验禁止方向为“互联网区 → 管理区”，定义在 `forbidden_zone_pairs`；接入其他业务前应按正式授权策略调整。

日志为 JSON Lines，每行一个 JSON 对象，至少含：`time`（带时区的 ISO 时间）、`method`、`path`、`status`（整数）；可含 `appid`。Nginx 配置另记录来源 IP、耗时、响应大小及 User-Agent。

## 运行审计

审计脚本只依赖 Python 标准库，可分析已经保存的日志，无需同时运行 API 服务。以下路径需替换为本地实际文件：

```powershell
python .\api_audit.py --log "C:\path\to\api_access.log" --ledger .\data\ledger.csv --callers .\data\callers.csv --output .\outputs
```

```powershell
python .\api_audit.py --help
```

未指定路径时，默认读取脚本目录的 `ledger.csv`、`callers.csv` 和 `nginx/logs/api_access.log`。`--demo` 是原本的本地学习开关，默认引用本地 `ledger_demo.csv` 和 `demo_access.jsonl`；这些文件不在仓库中，克隆后不能直接执行演示。请使用上述显式输入参数。

每次运行覆盖对应输出 CSV，写入前请关闭 Excel/WPS 中打开的结果文件。`api_inventory.csv` 只包含已登记资产；`findings.csv` 是需要核查的线索，问题记录条数不等于去重后的受影响接口数。

## 判定边界与后续接入

- 影子规则要求未登记、至少一次 2xx、至少三个活跃日期且只有一个非空 App-ID；不要求日期连续，也不保证每天成功。
- 僵尸规则筛选台账已下线却存在成功响应的接口；尚未结合正式下线时间，因此只是疑点。
- 全部返回 404 的路径不能据此认定为真实接口或恶意扫描。
- 异常暴露依赖调用方映射与实验禁止方向；来源未知时跳过此规则，不表示安全。请求者填写的 App-ID 不是可信认证身份，HTTP 2xx 不证明业务动作执行成功。
- 当前读取输入文件全部记录，尚无滚动时间窗、完整字段校验、combined 格式解析、多服务资产隔离或未知路径通用归一化。

接入真实数据时，先取授权导出的少量日志样本，明确采集范围、时区、代理层级和字段含义；新增格式适配与字段拒收统计，再补观测时间窗、可信主体、服务/环境维度、正式策略及下线时间。保留原始证据并由业务负责人复核结果，不根据脚本输出自动下线或阻断。
