"""安全巡检业务规则：巡检计划生成任务、隐患登记/合并、整改跟踪与闭环回写。

数据落在三张内存表上，互为唯一事实来源：
- inspection_plan：巡检计划（周期、责任人、计划巡检日），承接闭环完成情况回写；
- inspection_task：按计划生成的巡检任务，状态在 待巡检/巡检中/待整改/已闭环 间流转；
- inspection_hazard：巡检发现的隐患整改单，同任务下重复登记合并到已有单据。

所有派生字段（隐患计数、完成情况文案、pending/abnormal 标记）都在读取时重算，
保证刷新或重新进入后，巡检计划、隐患列表、统计卡片三处状态始终一致。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

PLAN_MODULE = "inspection_plan"
TASK_MODULE = "inspection_task"
HAZARD_MODULE = "inspection_hazard"

PLAN_REQUIRED = ["巡检区域", "巡检频次", "责任人", "计划巡检日"]
HAZARD_REQUIRED = ["隐患位置", "隐患描述"]
RECTIFY_REQUIRED = ["整改措施", "整改人"]

TASK_STATUSES = ["待巡检", "巡检中", "待整改", "已闭环"]
HAZARD_STATUSES = ["待整改", "已整改", "已闭环"]


def _today() -> str:
    return date.today().isoformat()


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _text(values: dict[str, Any], key: str) -> str:
    return str(values.get(key) or "").strip()


class InspectionService:
    # ------------------------------------------------------------------ 读取
    def list_plans(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._sync_plan(dict(row)) for row in store.rows(PLAN_MODULE)]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("计划编号", "")) or keyword in str(row.get("巡检区域", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_tasks(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._sync_task(dict(row)) for row in store.rows(TASK_MODULE)]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("任务编号", "")) or keyword in str(row.get("巡检区域", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_hazards(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._sync_hazard(dict(row)) for row in store.rows(HAZARD_MODULE)]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("隐患编号", ""))
                or keyword in str(row.get("隐患位置", ""))
                or keyword in str(row.get("隐患描述", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        task = store.find(TASK_MODULE, task_id)
        return self._sync_task(task) if task else None

    def stats(self) -> dict[str, Any]:
        """统计卡片：全部从三张表现算，任何状态流转后立刻反映到卡片上。"""
        plans = store.rows(PLAN_MODULE)
        tasks = [self._sync_task(dict(row)) for row in store.rows(TASK_MODULE)]
        hazards = [self._sync_hazard(dict(row)) for row in store.rows(HAZARD_MODULE)]
        total_hazards = len(hazards)
        closed_hazards = sum(1 for row in hazards if row.get("status") == "已闭环")
        return {
            "巡检计划总数": len(plans),
            "进行中任务": sum(1 for row in tasks if row.get("pending")),
            "待整改隐患": sum(1 for row in hazards if row.get("status") == "待整改"),
            "已闭环隐患": closed_hazards,
            "隐患总数": total_hazards,
            "闭环率": round(closed_hazards / total_hazards * 100) if total_hazards else None,
        }

    # ------------------------------------------------------------------ 计划
    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in PLAN_REQUIRED if not _text(values, field)]
        if missing:
            return None, missing
        rows = store.rows(PLAN_MODULE)
        plan_id = _next_id(rows)
        plan: dict[str, Any] = {
            "id": plan_id,
            "计划编号": f"PLAN-{plan_id:04d}",
            "巡检区域": _text(values, "巡检区域"),
            "巡检频次": _text(values, "巡检频次"),
            "责任人": _text(values, "责任人"),
            "计划巡检日": _text(values, "计划巡检日"),
            "status": "待巡检",
            "巡检状态": "待巡检",
            "pending": True,
            "abnormal": False,
            "最近任务编号": "",
            "隐患总数": 0,
            "待整改数": 0,
            "已闭环数": 0,
            "验收人": "",
            "闭环时间": "",
            "完成情况": "尚未生成巡检任务",
        }
        rows.append(plan)
        return plan, []

    def generate_task(
        self, plan_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """按巡检计划生成巡检任务；同一计划存在未闭环任务时不允许重复生成。"""
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        active = [
            row for row in store.rows(TASK_MODULE)
            if row.get("计划编号") == plan["计划编号"]
            and not row.get("已归档")
            and row.get("status") != "已闭环"
        ]
        if active:
            return None, f"计划下巡检任务 {active[-1]['任务编号']} 尚未闭环，不能重复生成任务"
        task_rows = store.rows(TASK_MODULE)
        task_id = _next_id(task_rows)
        task: dict[str, Any] = {
            "id": task_id,
            "任务编号": f"TASK-{task_id:04d}",
            "计划编号": plan["计划编号"],
            "巡检区域": plan["巡检区域"],
            "巡检人员": _text(values, "巡检人员") or plan["责任人"],
            "计划巡检日": plan["计划巡检日"],
            "开始时间": "",
            "验收人": "",
            "验收意见": "",
            "闭环时间": "",
            "归档时间": "",
            "已归档": False,
            "status": "待巡检",
            "任务状态": "待巡检",
            "pending": True,
            "abnormal": False,
            "隐患总数": 0,
            "待整改数": 0,
            "已整改数": 0,
            "已闭环数": 0,
            "完成情况": "任务已生成，等待开始巡检",
        }
        task_rows.append(task)
        self._sync_plan(plan)
        return task, f"已按巡检计划 {plan['计划编号']} 生成巡检任务 {task['任务编号']}"

    # ------------------------------------------------------------------ 任务
    def start_task(self, task_id: int) -> tuple[dict[str, Any] | None, str]:
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return None, f"巡检任务 {task_id} 不存在"
        if task.get("已归档"):
            return None, "任务已归档，不能再执行巡检"
        if task["status"] != "待巡检":
            return None, f"任务当前为「{task['status']}」，只有待巡检任务可以开始巡检"
        task["status"] = task["任务状态"] = "巡检中"
        task["开始时间"] = task.get("开始时间") or _today()
        self._sync_task(task)
        self._sync_plan_by_code(str(task["计划编号"]))
        return task, "巡检已开始，可登记巡检发现的问题"

    def finish_clean_task(
        self, task_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """巡检中且未发现隐患：登记验收人后直接闭环。"""
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return None, f"巡检任务 {task_id} 不存在"
        if task.get("已归档"):
            return None, "任务已归档"
        if task["status"] != "巡检中":
            return None, f"任务当前为「{task['status']}」，无隐患闭环只适用于巡检中的任务"
        hazards = self._task_hazards(str(task["任务编号"]))
        if hazards:
            return None, "本次巡检已登记隐患，请走整改验收闭环，不能按无隐患闭环"
        verifier = _text(values, "验收人")
        if not verifier:
            return None, "闭环验证必须登记验收人"
        self._close_task(task, verifier, _text(values, "验收意见"))
        return task, "本次巡检未发现隐患，任务已闭环；完成情况已回写巡检计划"

    def close_task(
        self, task_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """整改验收通过后闭环：待整改的隐患一项都不能留，闭环后回写计划与隐患单。"""
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return None, f"巡检任务 {task_id} 不存在"
        if task.get("已归档"):
            return None, "任务已归档"
        if task["status"] != "待整改":
            return None, f"任务当前为「{task['status']}」，只有待整改（待验收）任务可以闭环"
        hazards = self._task_hazards(str(task["任务编号"]))
        unfinished = [h for h in hazards if h.get("status") == "待整改"]
        if unfinished:
            return None, f"还有 {len(unfinished)} 项隐患未完成整改，不能闭环"
        verifier = _text(values, "验收人")
        if not verifier:
            return None, "闭环验证必须登记验收人"
        self._close_task(task, verifier, _text(values, "验收意见"))
        return task, "整改已通过验收，任务与隐患整改单已闭环，完成情况已回写巡检计划"

    def archive_task(self, task_id: int) -> tuple[dict[str, Any] | None, str]:
        """归档：已闭环才允许；未闭环的任务（含未闭环隐患）一律拦下。"""
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return None, f"巡检任务 {task_id} 不存在"
        if task.get("已归档"):
            return None, "该任务已归档，无需重复操作"
        self._sync_task(task)
        if task["status"] != "已闭环":
            return None, "任务尚有未闭环的巡检或隐患，未闭环前不能归档"
        open_hazards = [
            h for h in self._task_hazards(str(task["任务编号"])) if h.get("status") != "已闭环"
        ]
        if open_hazards:
            return None, f"还有 {len(open_hazards)} 项隐患未闭环，不能归档"
        task["已归档"] = True
        task["归档时间"] = _today()
        task["pending"] = False
        task["abnormal"] = False
        self._sync_plan_by_code(str(task["计划编号"]))
        return task, "巡检任务已归档"

    # ------------------------------------------------------------------ 隐患
    def register_hazard(
        self, task_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """登记巡检发现的问题；同任务下位置与描述相同且未闭环的，合并到已有整改单。"""
        task = store.find(TASK_MODULE, task_id)
        if task is None:
            return None, f"巡检任务 {task_id} 不存在"
        if task.get("已归档"):
            return None, "任务已归档，不能再登记隐患"
        if task["status"] not in ("巡检中", "待整改"):
            return None, f"任务当前为「{task['status']}」，只有巡检中、待整改的任务可以登记隐患"
        missing = [field for field in HAZARD_REQUIRED if not _text(values, field)]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        location = _text(values, "隐患位置")
        description = _text(values, "隐患描述")
        task_code = str(task["任务编号"])
        duplicate = next(
            (
                h for h in self._task_hazards(task_code)
                if str(h.get("隐患位置", "")).strip() == location
                and str(h.get("隐患描述", "")).strip() == description
                and h.get("status") != "已闭环"
            ),
            None,
        )
        if duplicate is not None:
            # 重复登记只累加次数与备注，绝不各记一条；原单已整改待验收的，重新打开。
            duplicate["重复登记次数"] = int(duplicate.get("重复登记次数", 1)) + 1
            note = f"{_today()} {_text(values, '登记人') or task.get('巡检人员', '')} 重复登记，已合并到本整改单"
            duplicate["登记备注"] = "\n".join(
                part for part in [str(duplicate.get("登记备注", "")).strip(), note] if part
            )
            reopened = ""
            if duplicate["status"] == "已整改":
                duplicate["status"] = duplicate["隐患状态"] = "待整改"
                reopened = "，原整改单已重新打开待整改"
            self._sync_hazard(duplicate)
            if task["status"] == "巡检中":
                task["status"] = task["任务状态"] = "待整改"
            self._sync_task(task)
            self._sync_plan_by_code(str(task["计划编号"]))
            return duplicate, f"该隐患已存在，已合并到整改单 {duplicate['隐患编号']}，未重复建单{reopened}"

        rows = store.rows(HAZARD_MODULE)
        hazard_id = _next_id(rows)
        hazard: dict[str, Any] = {
            "id": hazard_id,
            "隐患编号": f"HAZ-{hazard_id:04d}",
            "任务编号": task_code,
            "计划编号": task["计划编号"],
            "隐患位置": location,
            "隐患描述": description,
            "隐患级别": _text(values, "隐患级别") or "一般",
            "登记人": _text(values, "登记人") or task.get("巡检人员", ""),
            "登记时间": _today(),
            "整改措施": "",
            "整改人": "",
            "整改时间": "",
            "验收人": "",
            "闭环时间": "",
            "登记备注": "",
            "重复登记次数": 1,
            "status": "待整改",
            "隐患状态": "待整改",
            "pending": True,
            "abnormal": True,
        }
        rows.append(hazard)
        if task["status"] == "巡检中":
            task["status"] = task["任务状态"] = "待整改"
        self._sync_task(task)
        self._sync_hazard(hazard)
        self._sync_plan_by_code(str(task["计划编号"]))
        return hazard, f"隐患 {hazard['隐患编号']} 已登记并生成整改单，任务进入待整改"

    def rectify_hazard(
        self, hazard_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """登记整改情况；隐患转为已整改（待验收），任务仍停留在待整改直到闭环验证。"""
        hazard = store.find(HAZARD_MODULE, hazard_id)
        if hazard is None:
            return None, f"隐患 {hazard_id} 不存在"
        if hazard["status"] == "已闭环":
            return None, "该隐患已闭环，不能再登记整改"
        if hazard["status"] == "已整改":
            return None, "整改情况已登记，等待闭环验证，请勿重复提交"
        missing = [field for field in RECTIFY_REQUIRED if not _text(values, field)]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        hazard["整改措施"] = _text(values, "整改措施")
        hazard["整改人"] = _text(values, "整改人")
        hazard["整改时间"] = _today()
        hazard["status"] = hazard["隐患状态"] = "已整改"
        self._sync_hazard(hazard)
        task = self._task_by_code(str(hazard["任务编号"]))
        if task is not None:
            self._sync_task(task)
            self._sync_plan_by_code(str(task["计划编号"]))
        return hazard, "整改情况已登记，等待闭环验收"

    # ------------------------------------------------------------------ 内部
    def _task_hazards(self, task_code: str) -> list[dict[str, Any]]:
        return [row for row in store.rows(HAZARD_MODULE) if row.get("任务编号") == task_code]

    def _task_by_code(self, task_code: str) -> dict[str, Any] | None:
        return next(
            (row for row in store.rows(TASK_MODULE) if row.get("任务编号") == task_code), None
        )

    def _close_task(self, task: dict[str, Any], verifier: str, opinion: str) -> None:
        task_code = str(task["任务编号"])
        closed_at = _today()
        task["status"] = task["任务状态"] = "已闭环"
        task["验收人"] = verifier
        task["验收意见"] = opinion or "验收合格"
        task["闭环时间"] = closed_at
        for hazard in self._task_hazards(task_code):
            if hazard.get("status") != "已闭环":
                hazard["status"] = hazard["隐患状态"] = "已闭环"
                hazard["验收人"] = verifier
                hazard["闭环时间"] = closed_at
                self._sync_hazard(hazard)
        self._sync_task(task)
        self._sync_plan_by_code(str(task["计划编号"]))

    def _sync_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """重算任务上的隐患计数、完成情况文案与流程标记。"""
        hazards = self._task_hazards(str(task.get("任务编号", "")))
        total = len(hazards)
        pending_rectify = sum(1 for h in hazards if h.get("status") == "待整改")
        rectified = sum(1 for h in hazards if h.get("status") == "已整改")
        closed = sum(1 for h in hazards if h.get("status") == "已闭环")
        task["隐患总数"] = total
        task["待整改数"] = pending_rectify
        task["已整改数"] = rectified
        task["已闭环数"] = closed

        status = str(task.get("status", "待巡检"))
        if status == "待巡检":
            text = "任务已生成，等待开始巡检"
        elif status == "巡检中":
            text = "巡检进行中，暂未登记隐患" if total == 0 else f"巡检进行中，已登记隐患 {total} 项"
        elif status == "待整改":
            text = (
                f"发现隐患 {total} 项：待整改 {pending_rectify} 项、"
                f"已整改待验收 {rectified} 项、已闭环 {closed} 项"
            )
        else:
            if total == 0:
                text = f"巡检已闭环：本次未发现隐患；验收人 {task.get('验收人') or '—'}；闭环时间 {task.get('闭环时间') or '—'}"
            else:
                text = (
                    f"巡检已闭环：隐患 {total} 项全部整改验收合格；"
                    f"验收人 {task.get('验收人') or '—'}；闭环时间 {task.get('闭环时间') or '—'}"
                )
        task["完成情况"] = text
        task["任务状态"] = status
        task["pending"] = (not task.get("已归档", False)) and status != "已闭环"
        task["abnormal"] = status == "待整改" and (pending_rectify + rectified) > 0
        return task

    def _sync_plan_by_code(self, plan_code: str) -> dict[str, Any] | None:
        plan = next(
            (row for row in store.rows(PLAN_MODULE) if row.get("计划编号") == plan_code), None
        )
        if plan is not None:
            self._sync_plan(plan)
        return plan

    def _sync_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """把最近一次巡检任务的状态与整改完成情况回写到巡检计划。"""
        tasks = [
            row for row in store.rows(TASK_MODULE) if row.get("计划编号") == plan.get("计划编号")
        ]
        active = [row for row in tasks if not row.get("已归档") and row.get("status") != "已闭环"]
        source = self._sync_task(active[-1]) if active else (self._sync_task(tasks[-1]) if tasks else None)

        if source is None:
            plan["status"] = plan.get("status", "待巡检")
            plan.update({
                "最近任务编号": "",
                "隐患总数": 0,
                "待整改数": 0,
                "已闭环数": 0,
                "验收人": "",
                "闭环时间": "",
                "完成情况": "尚未生成巡检任务",
            })
        else:
            plan["status"] = source["status"]
            plan["最近任务编号"] = source["任务编号"]
            plan["隐患总数"] = source["隐患总数"]
            plan["待整改数"] = source["待整改数"]
            plan["已闭环数"] = source["已闭环数"]
            plan["验收人"] = source.get("验收人", "")
            plan["闭环时间"] = source.get("闭环时间", "")
            plan["完成情况"] = f"{source['任务编号']}：{source['完成情况']}"
        plan["巡检状态"] = plan["status"]
        plan["pending"] = plan["status"] != "已闭环"
        plan["abnormal"] = plan["status"] == "待整改"
        return plan

    def _sync_hazard(self, hazard: dict[str, Any]) -> dict[str, Any]:
        """把所属巡检任务的最新状态带到隐患列表，保证列表与任务、计划一致。"""
        status = str(hazard.get("status", "待整改"))
        hazard["status"] = status
        hazard["隐患状态"] = status
        task = self._task_by_code(str(hazard.get("任务编号", "")))
        hazard["任务状态"] = task.get("status", "") if task else ""
        hazard["pending"] = status != "已闭环"
        hazard["abnormal"] = status == "待整改"
        return hazard
