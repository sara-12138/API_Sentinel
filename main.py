from fastapi import FastAPI, Body, Query
import uuid

app = FastAPI(title="我的 API 审计实验")
#健康检查
@app.get("/health")
def health():
    return {"status": "ok"}

#电表读数
@app.get("/api/v1/meter/{month}/{meter_id}")
def meter_reading(month: str, meter_id: str):
    return {
        "meterId": meter_id,
        "month": month,
        "kwh": 128.4 #返回用电量
    }

#电表查询
@app.post("/api/v1/meter/query") #添加post请求接口，接收json数据
def meter_query(payload: dict = Body(...)):
    return {
        "total": 1,
        "items": [payload]
    }

# 客户资料接口：通过客户编号查询模拟资料
@app.get("/api/v1/customers/{cid}/profile")
def customer_profile(cid: int):
    return {
        "customerId": cid,
        "name": "张*",
        "phone": "138****0000"
    }


# 账单接口：通过账单编号查询模拟金额
@app.get("/api/v2/bills/{bid}")
def bill(bid: str):
    return {
        "billId": bid,
        "amount": 233.5
    }


# 负荷曲线接口：从查询参数中读取测点编号和日期
@app.get("/api/v1/load-curve")
def load_curve(point_id: str = Query(...), day: str = Query(...)):
    return {
        "pointId": point_id,
        "day": day,
        "points": [0.1] * 96
    }


# 故障上报接口：接收 JSON，返回模拟工单编号
@app.post("/api/v1/outage/report")
def outage(payload: dict = Body(...)):
    return {
        "ticket": "WO" + uuid.uuid4().hex[:8].upper()
    }


# 调度接口：故意省略鉴权，供后续审计实验使用
@app.post("/api/v1/schedule/command/dispatch")
def dispatch(payload: dict = Body(...)):
    return {
        "accepted": True
    }

# 模拟遗漏登记的旧版报表接口
@app.get("/api/v0/report/export")
def legacy_report():
    return {
        "report": "legacy-report",
        "rows": 12
    }
