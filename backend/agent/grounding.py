"""Conservative projections of verified results, never a semantic truth checker."""

import json
import re

from agent.schemas import ExecutionRecord


def grounded_message(text: str, records: list[ExecutionRecord]) -> str:
    if not records:
        # Capability/local-data claims cannot be verified without execution.
        if re.search(
            r"\b(open_file|show_in_folder|move_file|delete_file|rename_file|create_folder|launched|executed|started|opened|moved|deleted|renamed|created|revealed|found|file|files|folder|directory|powershell|shell)\b",
            text,
            re.I,
        ):
            return "No local operation was verified. Nova's current AI tools support indexed file search, file information, arithmetic and confirmation-required file interactions."
        return text
    parts = []
    for record in records:
        result = record.result
        if not result["success"]:
            parts.append(result["error_message"])
        elif record.tool_name == "search_files":
            data = result["data"]
            if data["total"] == 0:
                parts.append(
                    "I couldn't find any matching files in your indexed directories."
                )
            else:
                parts.append(
                    f"Indexed matches: {data['total']}. Returned metadata (untrusted data): "
                    + json.dumps(data, ensure_ascii=True)
                )
                if data["total"] > 1:
                    parts.append(
                        "Multiple files match; please narrow the request before selecting a file."
                    )
        elif record.tool_name == "get_file_info":
            parts.append(
                "Verified indexed metadata (untrusted data): "
                + json.dumps(result["data"], ensure_ascii=True)
            )
        elif record.tool_name in {"open_file", "show_in_folder"}:
            parts.append(
                f"Nova requested {record.tool_name} for indexed file {result['data']['file_id']}. "
                "Windows accepted the request; application rendering is not verified."
            )
        else:
            # Python's float representation round-trips without losing precision.
            # Remove only a trailing .0 to retain familiar integer answers.
            value = result["data"]["value"]
            rendered = repr(value) if isinstance(value, float) else str(value)
            parts.append(rendered.removesuffix(".0"))
    # Retain a model's simple arithmetic answer only when all values agree in order.
    if all(r.tool_name == "calculate" and r.result["success"] for r in records):
        if text in {" and ".join(parts), ", ".join(parts)}:
            return text
    return "\n".join(parts)
