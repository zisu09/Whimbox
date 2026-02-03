from typing import Any, Dict


def test(session_id: str, input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "message": "Plugin is running", "data": {}}


TOOL_FUNCS = {
    "demo.test": test
}

