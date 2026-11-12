"""Narrow reference recognition; only backend results can supply an indexed ID."""

from dataclasses import dataclass
import re

from services.conversations import ReferenceSet


@dataclass(frozen=True)
class ResolvedReference:
    file_id: int
    operation: str | None


@dataclass(frozen=True)
class Resolution:
    reference: ResolvedReference | None = None
    clarification: str | None = None


ORDINALS = {
    word: i
    for i, word in enumerate(
        (
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
        ),
        1,
    )
}
REFERENCE = re.compile(
    r"\b(?:the\s+)?(" + "|".join(ORDINALS) + r"|last)\s+(?:one|file)\b"
    r"|(?<!indexed )\b(?:number|file)\s+(\d{1,9})\b"
    r"|\b(?:that|this)\s+file\b|\b(?:open|show|reveal|rename|move)\s+it\b",
    re.I,
)


def resolve_reference(message: str, references: ReferenceSet | None) -> Resolution:
    matches = list(REFERENCE.finditer(message))
    if not matches:
        return Resolution()
    # Compound references are deliberately unsupported rather than guessed.
    if len(matches) != 1:
        return Resolution(
            clarification="Please select one file and one operation at a time."
        )
    if re.search(r"\b(earlier|previous|before|from)\b", message, re.I):
        return Resolution(
            clarification="Only the latest verified result set is available. Please search again for the intended files."
        )
    if not references or not references.files:
        return Resolution(
            clarification="No verified file results are available in this conversation. Please search again or specify the file."
        )
    match = matches[0]
    ordinal, number = match.group(1), match.group(2)
    if ordinal:
        index = (
            len(references.files)
            if ordinal.lower() == "last"
            else ORDINALS[ordinal.lower()]
        )
    elif number:
        index = int(number)
    elif references.total == 1 and len(references.files) == 1:
        index = 1
    else:
        return Resolution(
            clarification="Multiple files match. Please specify a result number or search more narrowly."
        )
    if index < 1 or index > len(references.files):
        return Resolution(
            clarification="That result number is unavailable. Please select a displayed result or search again."
        )
    opening = bool(re.search(r"\bopen\b", message, re.I))
    revealing = bool(
        re.search(r"\breveal\b", message, re.I)
        or (
            re.search(r"\bshow\b", message, re.I)
            and re.search(r"\b(folder|explorer)\b", message, re.I)
        )
    )
    renaming = bool(re.search(r"\brename\b", message, re.I))
    moving = bool(re.search(r"\bmove\b", message, re.I))
    if sum((opening, revealing, renaming, moving)) > 1:
        return Resolution(clarification="Please request one file operation at a time.")
    operation = "open_file" if opening else "show_in_folder" if revealing else None
    operation = "rename_file" if renaming else "move_file" if moving else operation
    return Resolution(ResolvedReference(references.files[index - 1].file_id, operation))
