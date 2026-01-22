from typing import Any, Dict


def hello(session_id: str, input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    name = input.get("name", "friend")
    return {"message": f"hello, {name}", "session_id": session_id}


TOOL_FUNCS = {
    "demo.hello": hello
}

