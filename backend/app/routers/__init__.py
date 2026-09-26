"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import sample as router_sample
from app.routers import client as router_client
from app.routers import project as router_project
from app.routers import task as router_task
from app.routers import execute as router_execute
from app.routers import result as router_result
from app.routers import review as router_review
from app.routers import instrument as router_instrument
from app.routers import calibration as router_calibration
from app.routers import reagent as router_reagent
from app.routers import consume as router_consume
from app.routers import environment as router_environment
from app.routers import inspection as router_inspection
from app.routers import report as router_report
from app.routers import issue as router_issue
from app.routers import qc as router_qc
from app.routers import complaint as router_complaint
from app.routers import stockin as router_stockin
from app.routers import settlement as router_settlement

ROUTERS = [router_sample, router_client, router_project, router_task, router_execute, router_result, router_review, router_instrument, router_calibration, router_reagent, router_consume, router_environment, router_inspection, router_report, router_issue, router_qc, router_complaint, router_stockin, router_settlement]
