"""隐患整改业务规则：隐患登记去重合并、整改流转、归档把关与计划回写都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services import inspection as inspection_svc
from app.store import store

MODULE = "hazard"
STATUS_ORDER = ["待整改", "整改中", "已闭环", "已归档"]
OPEN_STATUSES = ("待整改", "整改中")
REQUIRED_FIELDS = ["关联任务", "隐患位置", "隐患描述"]
ACTION_RULES = {"开始整改": "整改中", "整改完成": "已闭环", "归档": "已归档"}


def _refresh_flags(entry: dict[str, Any]) -> None:
    """把展示状态与看板标记重新对齐到当前状态。"""
    entry["当前状态"] = str(entry.get("status", ""))
    entry["pending"] = entry.get("status") in OPEN_STATUSES
    entry["abnormal"] = entry.get("status") in OPEN_STATUSES


class HazardService:
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
                if keyword in str(row.get("隐患编号", "")) or keyword in str(row.get("隐患位置", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        """登记隐患：同一隐患重复登记时合并到已有整改单，不重复建单。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        task_no = str(values["关联任务"]).strip()
        task = inspection_svc.find_task(task_no)
        if task is None:
            return None, [], f"关联任务 {task_no} 不存在，请先从巡检计划生成巡检任务"
        if task.get("status") not in ("巡检中", "待整改"):
            return None, [], f"任务 {task_no} 当前为「{task.get('status')}」，不在巡检中，不能登记隐患"
        location = str(values["隐患位置"]).strip()
        desc = str(values["隐患描述"]).strip()
        for row in store.rows(MODULE):
            same_hazard = str(row.get("隐患位置", "")) == location and str(row.get("隐患描述", "")) == desc
            if same_hazard and row.get("status") in OPEN_STATUSES:
                row["登记次数"] = int(row.get("登记次数", 1)) + 1
                if str(values.get("整改责任人") or "").strip():
                    row["整改责任人"] = str(values["整改责任人"]).strip()
                if str(values.get("整改期限") or "").strip():
                    row["整改期限"] = str(values["整改期限"]).strip()
                return row, [], f"同一隐患重复登记，已合并到整改单 {row['隐患编号']}（第 {row['登记次数']} 次登记）"
        rows = store.rows(MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "隐患编号": inspection_svc.next_code(rows, "隐患编号", "HAZ-"),
            "关联任务": task_no,
            "关联计划": str(task.get("关联计划", "")),
            "隐患位置": location,
            "隐患描述": desc,
            "整改责任人": str(values.get("整改责任人") or "").strip(),
            "整改期限": str(values.get("整改期限") or "").strip(),
            "登记次数": 1,
            "完成日期": "",
            "status": "待整改",
        }
        _refresh_flags(entry)
        rows.append(entry)
        task["隐患数量"] = int(task.get("隐患数量", 0)) + 1
        if task.get("status") == "巡检中":
            task["status"] = "待整改"
        inspection_svc.refresh_task_flags(task)
        inspection_svc.sync_plan(str(task.get("关联计划", "")))
        return entry, [], f"隐患已登记，整改单 {entry['隐患编号']} 已生成"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"隐患记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于隐患整改可执行范围"
        status = str(entry.get("status", ""))
        hazard_no = str(entry.get("隐患编号", ""))
        if action == "开始整改" and status != "待整改":
            return None, f"隐患 {hazard_no} 当前为「{status}」，只有待整改隐患才能开始整改"
        if action == "整改完成" and status != "整改中":
            return None, f"隐患 {hazard_no} 当前为「{status}」，请先开始整改"
        if action == "归档" and status != "已闭环":
            return None, f"隐患 {hazard_no} 未闭环，不能直接归档"
        entry["status"] = ACTION_RULES[action]
        if action == "整改完成":
            entry["完成日期"] = inspection_svc.today_str()
        _refresh_flags(entry)
        if action == "整改完成":
            self._write_back(entry)
        return entry, f"隐患已{action}"

    def _write_back(self, hazard: dict[str, Any]) -> None:
        """整改完成后回写巡检任务与计划：任务闭环、计划完成情况同步更新。"""
        task = inspection_svc.find_task(str(hazard.get("关联任务", "")))
        if task is None:
            return
        task["已整改数量"] = int(task.get("已整改数量", 0)) + 1
        if task.get("status") == "待整改" and int(task["已整改数量"]) >= int(task.get("隐患数量", 0)):
            task["status"] = "已闭环"
            task["完成日期"] = inspection_svc.today_str()
        inspection_svc.refresh_task_flags(task)
        inspection_svc.sync_plan(str(task.get("关联计划", "")))
