"""Export RPG dialogue into a human-readable review packet.

The packet is generated from production source so writers can review wording
without editing gameplay code. Re-run this tool after dialogue changes.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ROOT / "frontend" / "rpg" / "narrative.py",
    ROOT / "frontend" / "rpg" / "window.py",
    ROOT / "frontend" / "rpg" / "level_one.py",
)
OUTPUT = ROOT / "docs" / "RPG_DIALOGUE_REVIEW_PACKET.md"


def expression_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append("{" + ast.unparse(value.value) + "}")
        return "".join(parts)
    return None


def looks_like_speaker(value: str) -> bool:
    upper = value.upper()
    markers = (
        "MARA", "LAST CLERK", "ARCHIVIST", "THE ", "ARCHIVE", "VAULT",
        "VOICE", "MIMIC", "WRAITH", "PENDING", "DOCKET", "REGISTRY",
        "CHRONOMETER", "HALL", "CHEST", "CODEX", "ORIN", "RECORD",
        "ACCOUNT", "SHARDS", "SEAL", "LEDGER", "INDEX",
    )
    letters = [character for character in value if character.isalpha()]
    is_display_label = bool(letters) and all(character.isupper() for character in letters)
    return len(value) <= 70 and is_display_label and any(marker in upper for marker in markers)


class DialogueVisitor(ast.NodeVisitor):
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.function = "module"
        self.lines: list[tuple[int, str, str, str]] = []
        self.pools: list[tuple[int, str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function
        self.function = node.name
        self.generic_visit(node)
        self.function = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._capture_dialogue_tuple(node)
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self._capture_dialogue_tuple(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if self.function in {"_open_mara_conversation", "_handle_mara_choice"} and names & {
            "greeting", "responses", "line", "text"
        }:
            for text in self._strings_in(node.value):
                if len(text) >= 18 and not looks_like_speaker(text):
                    self.pools.append((node.lineno, self.function, text))
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self.function == "_mara_guidance_alternatives" and node.value:
            for text in self._strings_in(node.value):
                if len(text) >= 18:
                    self.pools.append((node.lineno, self.function, text))
        self.generic_visit(node)

    def _capture_dialogue_tuple(self, node: ast.Tuple | ast.List) -> None:
        values = node.elts
        candidates = ((0, 1), (2, 3))
        for speaker_index, text_index in candidates:
            if len(values) <= text_index:
                continue
            speaker = expression_text(values[speaker_index])
            text = expression_text(values[text_index])
            if speaker and text and looks_like_speaker(speaker):
                self.lines.append((node.lineno, self.function, speaker, text))
                return

    @staticmethod
    def _strings_in(node: ast.AST) -> list[str]:
        value = expression_text(node)
        if value:
            return [value]
        strings: list[str] = []
        for child in ast.iter_child_nodes(node):
            strings.extend(DialogueVisitor._strings_in(child))
        return strings


def export_packet() -> None:
    dialogue_by_section: dict[tuple[str, str], list[tuple[int, str, str]]] = defaultdict(list)
    pools: list[tuple[str, int, str, str]] = []

    for path in SOURCES:
        source = path.read_text(encoding="utf-8")
        visitor = DialogueVisitor(path.name)
        visitor.visit(ast.parse(source, filename=str(path)))
        for line, function, speaker, text in visitor.lines:
            dialogue_by_section[(path.name, function)].append((line, speaker, text))
        for line, function, text in visitor.pools:
            pools.append((path.name, line, function, text))

    output = [
        "# Out of Spec: Dialogue Review Packet",
        "",
        "Generated from the current production source. This is a review copy; send revisions back for application to the runtime files.",
        "",
        "## Authored Scenes and Interactions",
        "",
    ]
    seen: set[tuple[str, int, str, str]] = set()
    for (source_name, function), rows in sorted(dialogue_by_section.items()):
        output.extend((f"### {source_name} / {function}", ""))
        for line, speaker, text in sorted(rows):
            key = (source_name, line, speaker, text)
            if key in seen:
                continue
            seen.add(key)
            output.append(f"- **{speaker}:** {text}")
        output.append("")

    output.extend(("## Mara's Repeatable Conversation Pools", ""))
    seen_pool: set[tuple[str, str]] = set()
    for source_name, line, function, text in sorted(pools):
        key = (function, text)
        if key in seen_pool:
            continue
        seen_pool.add(key)
        output.append(f"- **{function}** (`{source_name}:{line}`): {text}")
    output.append("")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(output), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    export_packet()
