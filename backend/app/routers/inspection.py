"""安全巡检接口：巡检计划生成巡检任务，任务按待巡检、巡检中、待整改、已闭环流转。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inspection import PLAN_STATUSES, TASK_STATUS_ORDER, InspectionService

router = APIRouter(prefix="/api/inspection", tags=["安全巡检"])

service = InspectionService()

LIST_FIELDS = ["记录类型", "计划编号", "任务编号", "巡检区域", "巡检人员", "计划巡检日", "隐患数量", "已整改数量", "完成日期", "当前状态"]
STATUSES = PLAN_STATUSES + TASK_STATUS_ORDER


@router.get("/stats")
def inspection_stats() -> dict[str, Any]:
    """统计卡片：计划、未闭环任务、待整改隐患、已闭环隐患，各页面共用同一口径。"""
    return {"cards": service.stats_cards()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安全巡检清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inspection", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计划编号或任务编号检索"),
    status: str | None = Query(default=None, description="计划中、执行中、待巡检、巡检中、待整改、已闭环、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号与状态过滤安全巡检列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条巡检记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"巡检记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记巡检计划，计划编号自动生成避免重复；缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_plan(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"巡检计划 {entry['计划编号']} 已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条巡检记录执行生成巡检任务、开始巡检、巡检完成、整改闭环、归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
