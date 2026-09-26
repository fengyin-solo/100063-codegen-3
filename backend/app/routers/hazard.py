"""隐患整改接口：登记巡检发现的隐患并跟踪整改，同一隐患重复登记时合并到已有整改单。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.hazard import STATUS_ORDER, HazardService

router = APIRouter(prefix="/api/hazard", tags=["隐患整改"])

service = HazardService()

LIST_FIELDS = ["隐患编号", "关联任务", "隐患位置", "隐患描述", "整改责任人", "整改期限", "登记次数", "当前状态"]
STATUSES = STATUS_ORDER


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出隐患整改清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "hazard", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按隐患编号或隐患位置检索"),
    status: str | None = Query(default=None, description="待整改、整改中、已闭环、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号、位置与状态过滤隐患列表；没有隐患时返回空页，前端据此展示空态说明。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条隐患记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"隐患记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记隐患并生成整改单；同一隐患重复登记时合并到已有整改单，不重复建单。"""
    entry, missing, message = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条隐患执行开始整改、整改完成、归档；未闭环的隐患不能直接归档。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
