"""安全巡检业务规则：巡检计划生成任务、任务状态流转与计划回写都收在这里。

数据约定：inspection 表同时存放「计划」与「任务」两种记录（用记录类型区分）。
任务由计划生成，隐患整改完成后回写任务与计划，保证计划、任务、统计三处口径一致。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "inspection"
PLAN_STATUSES = ["计划中", "执行中", "已闭环"]
TASK_STATUS_ORDER = ["待巡检", "巡检中", "待整改", "已闭环", "已归档"]
CLOSED_TASK_STATUSES = ("已闭环", "已归档")
REQUIRED_PLAN_FIELDS = ["巡检区域", "巡检人员", "计划巡检日"]

TASK_ACTION_RULES = {"开始巡检": "巡检中", "巡检完成": "已闭环", "整改闭环": "已闭环", "归档": "已归档"}
PLAN_ACTIONS = {"生成巡检任务"}


def today_str() -> str:
    return date.today().isoformat()


def next_code(rows: list[dict[str, Any]], key: str, prefix: str) -> str:
    """按既有编号的最大序号生成下一个编号，保证刷新或重启编号规则后也不重复。"""
    max_no = 0
    for row in rows:
        code = str(row.get(key, ""))
        if code.startswith(prefix):
            try:
                max_no = max(max_no, int(code[len(prefix):]))
            except ValueError:
                continue
    return f"{prefix}{max_no + 1:04d}"


def find_task(task_no: str) -> dict[str, Any] | None:
    """按任务编号找任务行；隐患模块登记隐患、整改回写时都走这里。"""
    for row in store.rows(MODULE):
        if row.get("记录类型") == "任务" and row.get("任务编号") == task_no:
            return row
    return None


def refresh_task_flags(task: dict[str, Any]) -> None:
    """把展示状态与看板标记重新对齐到当前状态，避免流转后残留旧值。"""
    task["当前状态"] = str(task.get("status", ""))
    task["pending"] = task.get("status") not in CLOSED_TASK_STATUSES
    task["abnormal"] = int(task.get("已整改数量", 0)) < int(task.get("隐患数量", 0))


def sync_plan(plan_no: str) -> None:
    """把任务与隐患的完成情况回写到计划行：计划、任务、统计三处由此保持一致。"""
    if not plan_no:
        return
    rows = store.rows(MODULE)
    plan = next((row for row in rows if row.get("记录类型") == "计划" and row.get("计划编号") == plan_no), None)
    if plan is None:
        return
    tasks = [row for row in rows if row.get("记录类型") == "任务" and row.get("关联计划") == plan_no]
    closed = [task for task in tasks if task.get("status") in CLOSED_TASK_STATUSES]
    plan["任务总数"] = len(tasks)
    plan["已完成任务数"] = len(closed)
    plan["隐患数量"] = sum(int(task.get("隐患数量", 0)) for task in tasks)
    plan["已整改数量"] = sum(int(task.get("已整改数量", 0)) for task in tasks)
    if tasks and len(closed) == len(tasks):
        plan["status"] = "已闭环"
        if not plan.get("完成日期"):
            plan["完成日期"] = today_str()
    elif tasks:
        plan["status"] = "执行中"
        plan["完成日期"] = ""
    else:
        plan["status"] = "计划中"
        plan["完成日期"] = ""
    plan["当前状态"] = plan["status"]
    plan["pending"] = plan["status"] != "已闭环"
    plan["abnormal"] = int(plan["已整改数量"]) < int(plan["隐患数量"])


class InspectionService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("计划编号", "")) or keyword in str(row.get("任务编号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: (0 if row.get("记录类型") == "计划" else 1, int(row.get("id", 0))))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_PLAN_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        plan = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "记录类型": "计划",
            "计划编号": next_code(rows, "计划编号", "PLAN-"),
            "任务编号": "",
            "关联计划": "",
            "巡检区域": str(values["巡检区域"]).strip(),
            "巡检人员": str(values["巡检人员"]).strip(),
            "计划巡检日": str(values["计划巡检日"]).strip(),
            "任务总数": 0,
            "已完成任务数": 0,
            "隐患数量": 0,
            "已整改数量": 0,
            "完成日期": "",
            "status": "计划中",
        }
        plan["当前状态"] = plan["status"]
        plan["pending"] = True
        plan["abnormal"] = False
        rows.append(plan)
        return plan, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡检记录 {entry_id} 不存在或已归档"
        if entry.get("记录类型") == "计划":
            return self._run_plan_action(entry, action)
        return self._run_task_action(entry, action)

    def _run_plan_action(self, plan: dict[str, Any], action: str) -> tuple[dict[str, Any] | None, str]:
        if action not in PLAN_ACTIONS:
            return None, f"动作「{action}」不属于巡检计划可执行范围"
        if plan.get("status") == "已闭环":
            return None, f"计划 {plan['计划编号']} 已闭环，不能再生成巡检任务"
        rows = store.rows(MODULE)
        task = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "记录类型": "任务",
            "计划编号": plan["计划编号"],
            "任务编号": next_code(rows, "任务编号", "INS-"),
            "关联计划": plan["计划编号"],
            "巡检区域": plan["巡检区域"],
            "巡检人员": plan["巡检人员"],
            "计划巡检日": plan["计划巡检日"],
            "任务总数": 0,
            "已完成任务数": 0,
            "隐患数量": 0,
            "已整改数量": 0,
            "完成日期": "",
            "status": "待巡检",
        }
        refresh_task_flags(task)
        rows.append(task)
        sync_plan(str(plan["计划编号"]))
        return task, f"已按计划 {plan['计划编号']} 生成巡检任务 {task['任务编号']}"

    def _run_task_action(self, task: dict[str, Any], action: str) -> tuple[dict[str, Any] | None, str]:
        if action not in TASK_ACTION_RULES:
            return None, f"动作「{action}」不属于巡检任务可执行范围"
        status = str(task.get("status", ""))
        task_no = str(task.get("任务编号", ""))
        if action == "开始巡检":
            if status != "待巡检":
                return None, f"任务 {task_no} 当前为「{status}」，只有待巡检任务才能开始巡检"
        elif action == "巡检完成":
            if status != "巡检中":
                return None, f"任务 {task_no} 当前为「{status}」，只有巡检中的任务才能直接完成"
            if int(task.get("隐患数量", 0)) > 0:
                return None, f"任务 {task_no} 已登记隐患，需完成整改后闭环"
            task["完成日期"] = today_str()
        elif action == "整改闭环":
            if status != "待整改":
                return None, f"任务 {task_no} 当前为「{status}」，只有待整改任务才能整改闭环"
            open_count = sum(
                1
                for hazard in store.rows("hazard")
                if hazard.get("关联任务") == task_no and hazard.get("status") in ("待整改", "整改中")
            )
            if open_count:
                return None, f"任务 {task_no} 还有 {open_count} 条隐患未闭环，不能闭环"
            task["完成日期"] = today_str()
        elif action == "归档":
            if status != "已闭环":
                return None, f"任务 {task_no} 未闭环，不能直接归档"
        task["status"] = TASK_ACTION_RULES[action]
        refresh_task_flags(task)
        sync_plan(str(task.get("关联计划", "")))
        return task, f"巡检任务已{action}"

    def stats_cards(self) -> list[dict[str, Any]]:
        """统计卡片口径：计划、任务、隐患都从同一份数据里数，各页面刷出来才一致。"""
        rows = store.rows(MODULE)
        hazards = store.rows("hazard")
        plans = [row for row in rows if row.get("记录类型") == "计划"]
        open_tasks = [
            row
            for row in rows
            if row.get("记录类型") == "任务" and row.get("status") not in CLOSED_TASK_STATUSES
        ]
        open_hazards = [row for row in hazards if row.get("status") in ("待整改", "整改中")]
        closed_hazards = [row for row in hazards if row.get("status") in ("已闭环", "已归档")]
        return [
            {"label": "巡检计划", "value": len(plans)},
            {"label": "未闭环任务", "value": len(open_tasks)},
            {"label": "待整改隐患", "value": len(open_hazards)},
            {"label": "已闭环隐患", "value": len(closed_hazards)},
        ]
