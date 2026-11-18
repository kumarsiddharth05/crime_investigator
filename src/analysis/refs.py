"""Reference resolution against case_context nodes."""

from typing import Any


def resolve_ref(case_context: dict[str, Any], ref: str) -> Any:
    """Resolve a dotted ref against case_context.

    Supports:
      - Direct dict key descent (e.g. "case")
      - List-member lookup by ref field
        (e.g. "photos.P1.d3" walks photos[*] for ref=="photos.P1",
         then that node's "detections"[*] for ref=="photos.P1.d3")
    Returns the resolved node, or None if any segment fails.
    """
    if not isinstance(case_context, dict) or not isinstance(ref, str):
        return None

    if ref == "case":
        return case_context.get("case")

    parts = ref.split(".")
    current: Any = case_context
    prefix_parts: list[str] = []

    for p in parts:
        prefix_parts.append(p)
        current_prefix = ".".join(prefix_parts)

        if isinstance(current, dict):
            if p in current:
                current = current[p]
            else:
                found: Any = None
                for val in current.values():
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict) and item.get("ref") == current_prefix:
                                found = item
                                break
                        if found is not None:
                            break
                if found is not None:
                    current = found
                else:
                    return None
        elif isinstance(current, list):
            found = None
            for item in current:
                if isinstance(item, dict) and item.get("ref") == current_prefix:
                    found = item
                    break
            if found is not None:
                current = found
            else:
                return None
        else:
            return None

    return current
