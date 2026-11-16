import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
import argparse

# 找到脚本自身所在的文件夹
BASE_DIR = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description="API 资产审计")
parser.add_argument(
    "--demo",
    action="store_true",
    help="使用独立的模拟日志"
)
parser.add_argument("--log", type=Path, help="访问日志路径，每行一个 JSON 对象")
parser.add_argument("--ledger", type=Path, help="接口台账 CSV 路径")
parser.add_argument("--callers", type=Path, help="调用方安全区 CSV 路径")
parser.add_argument("--output", type=Path, help="输出目录")
args = parser.parse_args()

# 显式路径相对于终端当前目录；未指定时沿用本地学习项目的默认位置。
default_ledger = "ledger_demo.csv" if args.demo else "ledger.csv"
default_log = (
    BASE_DIR / "demo_access.jsonl"
    if args.demo else BASE_DIR / "nginx" / "logs" / "api_access.log"
)
ledger_path = args.ledger or BASE_DIR / default_ledger
log_path = args.log or default_log
callers_path = args.callers or BASE_DIR / "callers.csv"
for input_path in (ledger_path, log_path, callers_path):
    if not input_path.is_file():
        parser.error(
            f"输入文件不存在：{input_path}。请提供 --log、--ledger、--callers；"
            "仓库不附带本地日志或测试数据。"
        )

# 拼出资产台账的完整路径

# 读取 CSV，每一行转换为一个字典
with ledger_path.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as file:
    ledger = list(csv.DictReader(file))

print(f"台账共登记 {len(ledger)} 个接口")

for api in ledger:
    print(
        f"{api['api_id']} | "
        f"{api['method']:4} | "
        f"{api['template']} | "
        f"{api['status']}"
    )

if args.demo:
    print("\n【模拟模式】当前分析的是人为构造的日志")
else:
    print("\n【日志分析模式】当前分析的是指定的访问日志")

records = []
failed = 0

with log_path.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        line = line.strip() #去掉首尾空格和换行符

        # 空行不参与统计
        if not line:
            continue

        try:
            record = json.loads(line)#把 JSON 字符串转换为 Python 字典，把记录的数据
        except json.JSONDecodeError as error:   #呈现成字典
            failed += 1
            print(f"第 {line_number} 行 JSON 格式错误：{error}")
            continue

        records.append(record)

total = len(records) + failed

print("\n--- 日志读取结果 ---")
print(f"成功读取：{len(records)} 条")
print(f"JSON 解析失败：{failed} 条")

if total > 0:
    success_rate = len(records) / total * 100
    print(f"JSON 解析成功率：{success_rate:.1f}%")
else:
    print("日志中没有非空记录")

print("\n--- 最近 5 条请求 ---")

for record in records[-5:]:
    caller = record.get("appid") or "未提供 App-ID"

    print(
        f"{record['method']:4} | "
        f"{record['path']} | "
        f"状态码 {record['status']} | "
        f"调用方 {caller}"
    )

def path_matches(path, template):
    path_parts = path.split("/")       #路径分割
    template_parts = template.split("/")  #模板分割

    # 路径段数量不同，就不匹配
    if len(path_parts) != len(template_parts):
        return False

    for actual, expected in zip(path_parts, template_parts): #每一段进行配对
        # 花括号中的部分是参数，可以匹配任意一个非空路径段
        if expected.startswith("{") and expected.endswith("}"):
            if not actual:
                return False
        elif actual != expected:
            return False

    return True

# 参数少的模板优先，避免宽泛模板抢先匹配固定路径
ordered_ledger = sorted(
    ledger,
    key=lambda api: api["template"].count("{")
)

matched_count = 0
unmatched_count = 0

for record in records:
    path = urlsplit(record["path"]).path
    method = record["method"].upper()

    # 默认先认为没有匹配到
    record["api_id"] = None
    record["template"] = None

    for api in ordered_ledger:
        if (
            method == api["method"].upper()
            and path_matches(path, api["template"])
        ):
            record["api_id"] = api["api_id"]
            record["template"] = api["template"]
            break

    if record["api_id"] is not None:
        matched_count += 1
    else:
        unmatched_count += 1

print("\n--- 台账匹配结果 ---")
print(f"匹配到台账的请求：{matched_count} 条")
print(f"未匹配到台账的请求：{unmatched_count} 条")

print("\n--- 最近 5 条请求的匹配情况 ---")

for record in records[-5:]:
    result = record["template"] or "未匹配台账"

    print(
        f"{record['method']:4} | "
        f"{record['path']} | "
        f"{record['status']} | "
        f"{result}"
    )
# 用“请求方法 + 路径模板”作为统计的唯一标识
inventory = {}

# 先把台账中的接口放进清单，调用次数初始为零
for api in ledger:
    key = (api["method"].upper(), api["template"])

    inventory[key] = {
        "api_id": api["api_id"],
        "method": api["method"].upper(),
        "template": api["template"],
        "status": api["status"],
        "calls": 0,
        "success_calls": 0,
        "callers": set()#用于保存不重复的调用
    }

# 把已匹配到台账的日志累加到对应接口
for record in records:
    if record["api_id"] is None:
        continue

    key = (record["method"].upper(), record["template"])
    item = inventory[key]

    item["calls"] += 1

    if 200 <= record["status"] < 300:
        item["success_calls"] += 1

    caller = record.get("appid") or "未提供 App-ID"
    item["callers"].add(caller)#给集合中添加调用方，集合会自动去重

print("\n--- 已登记接口的调用统计 ---")

for item in inventory.values():
    callers_text = ", ".join(sorted(item["callers"])) or "无调用"

    print(
        f"{item['api_id']} | "
        f"{item['method']:4} | "
        f"调用 {item['calls']} 次 | "
        f"成功 {item['success_calls']} 次 | "
        f"{item['template']} | "
        f"调用方：{callers_text}"
    )
# 创建输出目录；如果已经存在，就继续使用
output_dir = args.output or BASE_DIR / ("outputs_demo" if args.demo else "outputs")
output_dir.mkdir(exist_ok=True)

output_path = output_dir / "api_inventory.csv"

# 定义 CSV 的列名和排列顺序
fieldnames = [
    "api_id",
    "method",
    "template",
    "status",
    "calls",
    "success_calls",
    "callers"
]

with output_path.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)

    # 写入第一行列名
    writer.writeheader()

    for item in inventory.values():
        # 将集合转换成文本，方便保存到一个单元格
        callers_text = "; ".join(sorted(item["callers"]))

        writer.writerow({
            "api_id": item["api_id"],
            "method": item["method"],
            "template": item["template"],
            "status": item["status"],
            "calls": item["calls"],
            "success_calls": item["success_calls"],
            "callers": callers_text
        })

print(f"\n资产清单已保存到：{output_path}")

# 本地实验中已知的文档入口，不参与未登记业务接口判断
EXCLUDED_ENDPOINTS = {
    ("GET", "/docs"),
    ("GET", "/openapi.json")
}

# 汇总未匹配台账的请求
unregistered = {}

for record in records:
    # 已经匹配台账的请求，跳过
    if record["api_id"] is not None:
        continue

    method = record["method"].upper()
    path = urlsplit(record["path"]).path
    key = (method, path)
    if key in EXCLUDED_ENDPOINTS:
        continue

    # 第一次遇到这个“方法 + 路径”，创建统计记录
    if key not in unregistered:
        unregistered[key] = {
            "method": method,
            "path": path,
            "calls": 0,
            "success_calls": 0,
            "not_found_calls": 0,
            "callers": set(),
            "active_dates": set(),
            "first_seen": None,
            "last_seen": None
        }

    item = unregistered[key]
    item["calls"] += 1

        # 将日志时间转换成时间对象，并统一到北京时间
    event_time = datetime.fromisoformat(record["time"])
    event_time = event_time.astimezone(
        datetime.fromisoformat("2000-01-01T00:00:00+08:00").tzinfo
    )

    # 同一个日期重复添加，集合仍只保留一份
    item["active_dates"].add(event_time.date())

    if item["first_seen"] is None or event_time < item["first_seen"]:
        item["first_seen"] = event_time

    if item["last_seen"] is None or event_time > item["last_seen"]:
        item["last_seen"] = event_time

    if 200 <= record["status"] < 300:
        item["success_calls"] += 1

    if record["status"] == 404:
        item["not_found_calls"] += 1

    caller = record.get("appid") or "未提供 App-ID"
    item["callers"].add(caller)

# 导出未登记路径清单
unregistered_path = output_dir / "unregistered_paths.csv"

columns = [
    "method",
    "path",
    "calls",
    "success_calls",
    "not_found_calls",
    "callers",
    "active_days",
    "first_seen",
    "last_seen",
    "assessment"
]

with unregistered_path.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as file:
    writer = csv.DictWriter(file, fieldnames=columns)
    writer.writeheader()

    for item in unregistered.values():
        active_days = len(item["active_dates"])

        # 实验中用“仅有一个非空 App-ID”作为调用方稳定的初步信号
        single_known_caller = (
            len(item["callers"]) == 1
            and "未提供 App-ID" not in item["callers"]
        )

        if (
            item["success_calls"] > 0
            and active_days >= 3
            and single_known_caller
        ):
            assessment = "疑似影子 API，需确认业务依赖及登记情况"

        elif item["success_calls"] > 0:
            assessment = "未登记路径存在成功响应，需继续观察"

        elif item["not_found_calls"] == item["calls"]:
            assessment = "全部返回404，尚不能证明接口存在"

        else:
            assessment = "存在其他状态码，需结合原始日志核查"

        writer.writerow({
            "method": item["method"],
            "path": item["path"],
            "calls": item["calls"],
            "success_calls": item["success_calls"],
            "not_found_calls": item["not_found_calls"],
            "callers": "; ".join(sorted(item["callers"])),
            "active_days": len(item["active_dates"]),
            "first_seen": item["first_seen"].isoformat(),
            "last_seen": item["last_seen"].isoformat(),
            "assessment": assessment
        })

print(f"\n未匹配台账的方法与路径组合：{len(unregistered)} 个")
print(f"未登记路径清单已保存到：{unregistered_path}")

# 查找“台账已下线，但存在成功调用”的接口
zombie_candidates = []

for item in inventory.values():
    if item["status"] == "已下线" and item["success_calls"] > 0:
        zombie_candidates.append(item)

print("\n--- 疑似僵尸 API ---")

if not zombie_candidates:
    print("未发现“已下线但存在成功调用”的接口")

for item in zombie_candidates:
    print(
        f"{item['api_id']} | "
        f"{item['method']} {item['template']} | "
        f"台账状态：{item['status']} | "
        f"成功调用：{item['success_calls']} 次 | "
        f"需核对下线时间及实际部署状态"
    )
# 读取调用方安全区映射
with callers_path.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as file:
    caller_rows = list(csv.DictReader(file))

caller_zones = {}

for row in caller_rows:
    caller_zones[row["appid"]] = row["zone"]

# 按接口编号建立索引，方便查找接口的安全区
apis_by_id = {}

for api in ledger:
    apis_by_id[api["api_id"]] = api

# 实验策略：禁止互联网区直接访问管理区
forbidden_zone_pairs = {
    ("互联网区", "管理区")
}

exposure_candidates = []

for record in records:
    # 没匹配台账，就暂时不知道接口所属安全区
    if record["api_id"] is None:
        continue

    # 这条规则只筛选成功响应
    if not 200 <= record["status"] < 300:
        continue

    appid = record.get("appid", "")
    source_zone = caller_zones.get(appid)

    api = apis_by_id[record["api_id"]]
    target_zone = api["zone"]

    # 来源区未知时不猜测，暂不使用这条跨区规则判断
    if source_zone is None:
        continue

    if (source_zone, target_zone) in forbidden_zone_pairs:
        exposure_candidates.append({
            "time": record["time"],
            "appid": appid,
            "source_zone": source_zone,
            "target_zone": target_zone,
            "method": record["method"],
            "path": record["path"],
            "status": record["status"]
        })

print("\n--- 疑似异常暴露：命中实验禁止策略的成功请求 ---")

if not exposure_candidates:
    print("未发现命中这条策略的成功请求")

for finding in exposure_candidates:
    print(
        f"{finding['time']} | "
        f"{finding['appid']} | "
        f"{finding['source_zone']} → {finding['target_zone']} | "
        f"{finding['method']} {finding['path']} | "
        f"HTTP {finding['status']}"
    )

# 汇总需要核查的问题；每条记录使用相同的五个字段
findings = []

# 一、复用此前导出的未登记路径判断结果
with unregistered_path.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as file:
    unregistered_rows = list(csv.DictReader(file))

for row in unregistered_rows:
    assessment = row["assessment"]

    if assessment.startswith("疑似影子 API"):
        category = "疑似影子 API"
    elif int(row["not_found_calls"]) == int(row["calls"]):
        category = "未知路径访问"
    else:
        category = "未登记路径待核查"

    findings.append({
        "category": category,
        "method": row["method"],
        "path": row["path"],
        "evidence": (
            f"调用{row['calls']}次；"
            f"成功{row['success_calls']}次；"
            f"404响应{row['not_found_calls']}次；"
            f"活跃{row['active_days']}天；"
            f"调用方：{row['callers'] or '未提供 App-ID'}"
        ),
        "assessment": assessment
    })

# 二、汇总疑似僵尸接口
for item in zombie_candidates:
    findings.append({
        "category": "疑似僵尸 API",
        "method": item["method"],
        "path": item["template"],
        "evidence": (
            f"接口编号：{item['api_id']}；"
            f"台账状态：{item['status']}；"
            f"成功调用{item['success_calls']}次"
        ),
        "assessment": "需核对调用是否发生在下线之后，以及实际部署状态"
    })

# 三、汇总疑似异常暴露请求（每条命中请求保留一条记录）
for item in exposure_candidates:
    findings.append({
        "category": "疑似异常暴露",
        "method": item["method"],
        "path": item["path"],
        "evidence": (
            f"时间：{item['time']}；"
            f"App-ID：{item['appid']}；"
            f"{item['source_zone']}→{item['target_zone']}；"
            f"HTTP {item['status']}"
        ),
        "assessment": "命中实验禁止策略，需核实调用身份及实际授权"
    })

# 四、沿用当前模式的输出目录，导出统一问题清单
findings_path = output_dir / "findings.csv"

with findings_path.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=["category", "method", "path", "evidence", "assessment"]
    )
    writer.writeheader()
    writer.writerows(findings)

print(f"\n问题清单共 {len(findings)} 条")
print(f"已保存到：{findings_path}")
