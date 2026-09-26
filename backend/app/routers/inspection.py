"""安全巡检接口：巡检计划、巡检任务、隐患整改单的登记、流转与闭环回写。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inspection import (
    HAZARD_STATUSES,
    TASK_STATUSES,
    InspectionService,
)

router = APIRouter(prefix="/api/inspection", tags=["安全巡检"])

service = InspectionService()

PLAN_FIELDS = ["计划编号", "巡检区域", "巡检频次", "责任人", "计划巡检日", "巡检状态", "隐患总数", "待整改数", "已闭环数", "验收人", "闭环时间", "完成情况"]
TASK_FIELDS = ["任务编号", "计划编号", "巡检区域", "巡检人员", "计划巡检日", "开始时间", "任务状态", "隐患总数", "待整改数", "已整改数", "已闭环数", "验收人", "闭环时间", "完成情况"]
HAZARD_FIELDS = ["隐患编号", "任务编号", "隐患位置", "隐患描述", "隐患级别", "登记人", "登记时间", "重复登记次数", "整改措施", "整改人", "整改时间", "隐患状态", "任务状态", "验收人", "闭环时间"]


def _page_limit(size: int) -> None:
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")


@router.get("/stats")
def inspection_stats() -> dict[str, Any]:
    """统计卡片：与计划、隐患列表同一数据源实时计算。"""
    return service.stats()


# ---------------------------------------------------------------------- 计划
@router.get("/plans", response_model=PageResult[dict])
def list_plans(
    keyword: str | None = Query(default=None, description="按计划编号或巡检区域检索"),
    status: str | None = Query(default=None, description=f"{'、'.join(TASK_STATUSES)}"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """巡检计划列表；完成情况由最近一次巡检任务实时回写。"""
    _page_limit(size)
    items, total = service.list_plans(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/plans", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """登记一条巡检计划。"""
    plan, missing = service.create_plan(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="巡检计划已登记", entry=plan)


@router.post("/plans/{plan_id}/tasks", response_model=ActionResult)
def generate_task(plan_id: int, payload: EntryPayload) -> ActionResult:
    """按巡检计划生成巡检任务；计划下存在未闭环任务时拒绝重复生成。"""
    task, message = service.generate_task(plan_id, payload.values)
    if task is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=task)


# ---------------------------------------------------------------------- 任务
@router.get("/tasks", response_model=PageResult[dict])
def list_tasks(
    keyword: str | None = Query(default=None, description="按任务编号或巡检区域检索"),
    status: str | None = Query(default=None, description=f"{'、'.join(TASK_STATUSES)}"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """巡检任务列表，状态只在 待巡检/巡检中/待整改/已闭环 之间流转。"""
    _page_limit(size)
    items, total = service.list_tasks(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/tasks/{task_id}", response_model=dict)
def get_task(task_id: int) -> dict:
    task = service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"巡检任务 {task_id} 不存在")
    return task


@router.post("/tasks/{task_id}/start", response_model=ActionResult)
def start_task(task_id: int) -> ActionResult:
    """待巡检 → 巡检中。"""
    task, message = service.start_task(task_id)
    if task is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=task)


@router.post("/tasks/{task_id}/close", response_model=ActionResult)
def close_task(task_id: int, payload: EntryPayload) -> ActionResult:
    """待整改 → 已闭环：全部隐患整改完成并验收通过后执行。"""
    task, message = service.close_task(task_id, payload.values)
    if task is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=task)


@router.post("/tasks/{task_id}/close-clean", response_model=ActionResult)
def close_clean_task(task_id: int, payload: EntryPayload) -> ActionResult:
    """巡检中且无隐患登记 → 直接闭环。"""
    task, message = service.finish_clean_task(task_id, payload.values)
    if task is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=task)


@router.post("/tasks/{task_id}/archive", response_model=ActionResult)
def archive_task(task_id: int) -> ActionResult:
    """归档已闭环任务；未闭环（含未闭环隐患）的任务一律拒绝。"""
    task, message = service.archive_task(task_id)
    if task is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=task)


# ---------------------------------------------------------------------- 隐患
@router.get("/hazards", response_model=PageResult[dict])
def list_hazards(
    keyword: str | None = Query(default=None, description="按隐患编号、位置或描述检索"),
    status: str | None = Query(default=None, description=f"{'、'.join(HAZARD_STATUSES)}"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """隐患整改单列表；无隐患时返回空页，由前端展示空态说明。"""
    _page_limit(size)
    items, total = service.list_hazards(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/tasks/{task_id}/hazards", response_model=ActionResult)
def register_hazard(task_id: int, payload: EntryPayload) -> ActionResult:
    """登记巡检发现的问题；同一隐患重复登记时合并到已有整改单。"""
    hazard, message = service.register_hazard(task_id, payload.values)
    if hazard is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=hazard)


@router.post("/hazards/{hazard_id}/rectify", response_model=ActionResult)
def rectify_hazard(hazard_id: int, payload: EntryPayload) -> ActionResult:
    """登记整改措施与整改人：待整改 → 已整改（待验收）。"""
    hazard, message = service.rectify_hazard(hazard_id, payload.values)
    if hazard is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=hazard)
