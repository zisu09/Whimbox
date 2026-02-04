from typing import Any, Dict, Optional, Type

from whimbox.common.cvars import current_session_id, current_stop_flag
from whimbox.task.task_template import TaskResult, TaskTemplate


class TaskAdapter:
    @staticmethod
    def run(
        task_cls: Type[TaskTemplate],
        session_id: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        stop_event = context.get("stop_event")

        task = task_cls(**input_data)
        if stop_event is not None:
            task.stop_flag = stop_event
            current_stop_flag.set(stop_event)

        current_session_id.set(session_id or "default")

        result = task.task_run()
        if isinstance(result, TaskResult):
            return result.to_dict()
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return {"status": "success", "message": str(result), "session_id": session_id}
