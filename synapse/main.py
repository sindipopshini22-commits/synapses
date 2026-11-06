from __future__ import annotations

import argparse
import json
import random
import select
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class AtlasError(Exception):
    pass


@dataclass
class Pipe:
    name: str
    size: str
    comes_from: List[str]
    line_no: int


@dataclass
class Area:
    name: str
    fed_by: List[str]
    symptoms: List[str]
    description: str
    line_no: int


@dataclass
class Atlas:
    pipes: Dict[str, Pipe] = field(default_factory=dict)
    areas: Dict[str, Area] = field(default_factory=dict)

    def children_of(self, pipe_name: str) -> List[str]:
        return sorted(p.name for p in self.pipes.values() if pipe_name in p.comes_from)

    def areas_fed_by(self, pipe_name: str) -> List[str]:
        return sorted(area.name for area in self.areas.values() if pipe_name in area.fed_by)

    def find_areas_by_keyword(self, keyword: str) -> List[Area]:
        needle = keyword.lower()
        matches: List[Area] = []
        for area in self.areas.values():
            haystacks = [area.name, area.description, *area.symptoms]
            if any(needle in item.lower() for item in haystacks):
                matches.append(area)
        return sorted(matches, key=lambda a: a.name)

    def show_pipe(self, name: str) -> str:
        pipe = self.pipes[name]
        branches = self.children_of(name)
        fed = self.areas_fed_by(name)
        return "\n".join([
            f"Pipe: {pipe.name}",
            f"Size:           {pipe.size}",
            f"Comes from:     {', '.join(pipe.comes_from) if pipe.comes_from else '-'}",
            f"Branches into:  {', '.join(branches) if branches else 'none'}",
            f"Feeds areas:    {', '.join(fed) if fed else 'none directly'}",
        ])

    def show_area(self, name: str) -> str:
        area = self.areas[name]
        return "\n".join([
            f"Area: {area.name}",
            f"What it does:   {area.description}",
            f"Fed by:         {', '.join(area.fed_by) if area.fed_by else 'none'}",
            f"If it stops:    {', '.join(area.symptoms) if area.symptoms else 'none'}",
        ])

    def ancestors_of_pipe(self, pipe_name: str) -> List[List[str]]:
        if pipe_name == "heart":
            return [["heart"]]
        if pipe_name not in self.pipes:
            return []
        routes: List[List[str]] = []
        for parent in self.pipes[pipe_name].comes_from:
            if parent == "-":
                routes.append(["heart", pipe_name])
            else:
                for prefix in self.ancestors_of_pipe(parent):
                    routes.append(prefix + [pipe_name])
        return routes

    def routes_to_area(self, area_name: str) -> List[List[str]]:
        if area_name not in self.areas:
            return []
        routes: List[List[str]] = []
        for feeder in self.areas[area_name].fed_by:
            for route in self.ancestors_of_pipe(feeder):
                routes.append(route + [area_name])
        unique: List[List[str]] = []
        seen: Set[Tuple[str, ...]] = set()
        for route in routes:
            key = tuple(route)
            if key not in seen:
                seen.add(key)
                unique.append(route)
        return unique

    def tree_lines(self) -> List[str]:
        lines: List[str] = []
        seen: Set[str] = set()

        def walk(pipe_name: str, depth: int) -> None:
            if pipe_name in seen:
                return
            seen.add(pipe_name)
            lines.append("  " * depth + pipe_name)
            for child in self.children_of(pipe_name):
                walk(child, depth + 1)
            for area_name in self.areas_fed_by(pipe_name):
                lines.append("  " * (depth + 1) + f"[{area_name}]")

        if "heart" in self.pipes:
            walk("heart", 0)
        return lines


# ============================================================================
# Mission 6: Recovery Clinic — data models and norms
# ============================================================================

@dataclass
class Visit:
    day: int
    reactionMs: int
    memoryDigits: int
    colorWordSeconds: float


@dataclass
class Case:
    id: str
    name: str
    age: int
    likelyPipe: str
    visits: List[Visit] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "likelyPipe": self.likelyPipe,
            "visits": [
                {
                    "day": v.day,
                    "reactionMs": v.reactionMs,
                    "memoryDigits": v.memoryDigits,
                    "colorWordSeconds": v.colorWordSeconds,
                }
                for v in self.visits
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Case":
        return cls(
            id=data["id"],
            name=data["name"],
            age=int(data["age"]),
            likelyPipe=data.get("likelyPipe", "unknown"),
            visits=[
                Visit(
                    day=v["day"],
                    reactionMs=v["reactionMs"],
                    memoryDigits=v["memoryDigits"],
                    colorWordSeconds=v["colorWordSeconds"],
                )
                for v in data.get("visits", [])
            ],
        )


class ClinicNorms:
    """Loads and queries normal values from data/norms.txt."""

    def __init__(self, path: str = "data/norms.txt") -> None:
        self.path = path
        self.by_test: Dict[str, List[dict]] = {}
        self._load_from_file(path)

    def _normalise_test(self, name: str) -> str:
        value = (name or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        aliases = {
            "reaction": "reaction",
            "reactiontime": "reaction",
            "memory": "memory",
            "memoryspan": "memory",
            "colorword": "colorword",
            "colourword": "colorword",
            "colorwords": "colorword",
            "colourwords": "colorword",
        }
        return aliases.get(value, value)

    def _load_from_file(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise ValueError(f'ERROR: File not found: {p}')

        self.by_test = {}
        with open(p, "r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [part.strip() for part in line.split("|")]
                if len(parts) != 6 or parts[0].upper() != "NORM":
                    continue
                test_name = self._normalise_test(parts[1])
                try:
                    low = int(parts[2])
                    high = int(parts[3])
                except ValueError:
                    raise ValueError(f'ERROR: {p.name}, line {line_no}: ages must be whole numbers.')
                try:
                    average = float(parts[4])
                    spread = float(parts[5])
                except ValueError:
                    raise ValueError(f'ERROR: {p.name}, line {line_no}: average and spread must be numeric.')
                if low > high:
                    raise ValueError(f'ERROR: {p.name}, line {line_no}: ages {low} to {high} are backwards.')
                records = self.by_test.setdefault(test_name, [])
                for previous in records:
                    if not (high < previous["from_age"] or low > previous["to_age"]):
                        raise ValueError(
                            f'ERROR: {p.name}, line {line_no}: ages {low} to {high} overlap with line {previous["line"]}.'
                        )
                records.append(
                    {"from_age": low, "to_age": high, "average": average, "spread": spread, "line": line_no}
                )

    def norm_for_age(self, test_name: str, age: int) -> dict:
        key = self._normalise_test(test_name)
        records = self.by_test.get(key, [])
        for record in records:
            if record["from_age"] <= age <= record["to_age"]:
                return record
        raise ValueError(f'ERROR: No normal values for age {age}.')

    def classify_value(self, test_name: str, age: int, value) -> str:
        key = self._normalise_test(test_name)
        norm = self.norm_for_age(key, age)
        average = float(norm["average"])
        spread = float(norm["spread"])
        if key == "memory":
            if value >= average - spread:
                return "normal"
            if value >= average - (2 * spread):
                return "below"
            return "well below"
        if value <= average + spread:
            return "normal"
        if value <= average + (2 * spread):
            return "below"
        return "well below"

    def normal_range(self, test_name: str, age: int) -> Tuple[float, float]:
        norm = self.norm_for_age(test_name, age)
        average = float(norm["average"])
        spread = float(norm["spread"])
        return average - spread, average + spread

    def label(self, test_name: str) -> str:
        names = {"reaction": "reaction", "memory": "memory", "colorword": "colour words"}
        return names.get(self._normalise_test(test_name), test_name)


# ============================================================================
# Mission 6: Recovery Clinic — brain tests
# ============================================================================

COLOUR_ANSI = {
    "RED": "\033[31m",
    "BLUE": "\033[34m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
}
ANSI_RESET = "\033[0m"


def flush_stdin() -> None:
    """Discard any pending input so the next prompt starts clean."""
    while select.select([sys.stdin], [], [], 0)[0]:
        sys.stdin.readline()


def test_reaction_time() -> int:
    """Reaction time test: 5 rounds, wait random 1-3s then press ENTER at *.
    Returns average ms of valid rounds (whole milliseconds)."""
    print("Press ENTER as soon as you see *")
    rounds: List[float] = []
    while len(rounds) < 5:
        flush_stdin()
        print("Wait...", end="", flush=True)
        delay = random.uniform(1.0, 3.0)
        time.sleep(delay)
        start = time.perf_counter()
        print("*")
        sys.stdin.readline()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms < 100.0:
            print("Too soon!")
            continue
        rounds.append(elapsed_ms)
        print(f"{int(round(elapsed_ms))} ms")
    average = sum(rounds) / len(rounds)
    return int(round(average))


def random_digits(count: int) -> List[str]:
    """Generate `count` random digits with no digit appearing twice in a row."""
    digits: List[str] = []
    last: Optional[str] = None
    for _ in range(count):
        while True:
            d = str(random.randint(0, 9))
            if d != last:
                break
        digits.append(d)
        last = d
    return digits


def test_memory_span() -> int:
    """Memory span test: show growing rows of digits, return longest correct row."""
    print("Remember the digits. They disappear after a moment.")
    longest = 0
    for length in range(3, 10):
        digits = random_digits(length)
        print(" ".join(digits), flush=True)
        time.sleep(length * 1.0)
        # Hide the digits
        print("\r" + " " * (length * 3 + 5) + "\r", end="", flush=True)
        answer = sys.stdin.readline().strip().replace(" ", "")
        expected = "".join(digits)
        if answer == expected:
            longest = length
        else:
            break
    return longest


def test_colour_words() -> float:
    """Colour words test: 10 rounds, at least 7 incongruent.
    Returns total seconds + 2s per wrong answer, one decimal."""
    colours = ["RED", "BLUE", "GREEN", "YELLOW"]
    words = ["RED", "BLUE", "GREEN", "YELLOW"]
    valid_letters = {"r", "b", "g", "y"}
    colour_of_letter = {"r": "RED", "b": "BLUE", "g": "GREEN", "y": "YELLOW"}

    # Build 10 rounds, ensuring at least 7 have colour != word
    rounds: List[Tuple[str, str]] = []
    mismatch = 0
    for _ in range(10):
        word = random.choice(words)
        if mismatch < 7:
            possible = [c for c in colours if c != word]
            colour = random.choice(possible)
            mismatch += 1
        else:
            colour = random.choice(colours)
        rounds.append((word, colour))

    print("Type the first letter of the COLOUR of each word, not the word: r, b, g or y.")
    start = time.perf_counter()
    wrong = 0
    for word, colour in rounds:
        ansi = COLOUR_ANSI.get(colour, "")
        print(f"{ansi}{word}{ANSI_RESET}", flush=True)
        while True:
            answer = sys.stdin.readline().strip().lower()
            if answer and answer[0] in valid_letters:
                break
            print("Type r, b, g or y:", end=" ", flush=True)
        if colour_of_letter[answer[0]] != colour:
            wrong += 1
    elapsed = time.perf_counter() - start
    total = elapsed + wrong * 2.0
    return round(total, 1)


# ============================================================================
# Mission 6: Recovery Clinic — case I/O
# ============================================================================

def load_cases(path: str = "data/cases.json") -> List[Case]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return []
    return [Case.from_dict(item) for item in payload.get("cases", [])]


def save_cases(cases: List[Case], path: str = "data/cases.json") -> None:
    p = Path(path)
    payload = {"cases": [c.to_dict() for c in cases]}
    with open(p, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def find_case(cases: List[Case], case_id: str) -> Optional[Case]:
    target = (case_id or "").strip().lower()
    for case in cases:
        if str(case.id).lower() == target:
            return case
    return None


# ============================================================================
# Mission 6: Recovery Clinic — damage / area logic
# ============================================================================

TEST_EXPECTED_AREAS = {
    "reaction": ["right-arm-face", "awake"],
    "memory": ["memory", "understanding"],
    "colorword": ["understanding", "left-attention", "right-vision", "left-vision"],
}


def stopped_areas_for_pipe(atlas: Optional[Atlas], pipe_name: str) -> Set[str]:
    """Return the set of area names that stop working when `pipe_name` is blocked."""
    if atlas is None or not pipe_name or pipe_name == "unknown":
        return set()
    if pipe_name not in atlas.pipes:
        return set()

    # BFS from heart through unblocked pipes
    blocked = {pipe_name}
    reachable: Set[str] = {"heart"}
    queue: List[str] = ["heart"]
    while queue:
        current = queue.pop(0)
        for child in atlas.children_of(current):
            if child not in blocked and child not in reachable:
                reachable.add(child)
                queue.append(child)

    stopped: Set[str] = set()
    for area_name, area in atlas.areas.items():
        # Area stops working if none of its feeding pipes have blood
        if not any(f in reachable for f in area.fed_by):
            stopped.add(area_name)
    return stopped


def test_is_expected_weak(test_name: str, stopped: Set[str]) -> bool:
    """Return True if the test is expected to be weak given stopped areas."""
    expected = TEST_EXPECTED_AREAS.get(test_name, [])
    return any(area in stopped for area in expected)


# ============================================================================
# Mission 6: Recovery Clinic — trend
# ============================================================================

def compute_trend(test_name: str, old_val, new_val) -> str:
    """Compare last two visits. Returns 'improving', 'worse', or 'steady'."""
    lower_is_better = test_name in ("reaction", "colorword")
    if lower_is_better:
        if old_val == 0:
            return "steady"
        if new_val < old_val * 0.95:
            return "improving"
        if new_val > old_val * 1.05:
            return "worse"
        return "steady"
    else:  # memory: higher is better
        if new_val > old_val:
            return "improving"
        if new_val < old_val:
            return "worse"
        return "steady"


class AtlasLoader:


    @staticmethod
    def parse_list(value: str) -> List[str]:
        if value == "":
            return []
        return [part.strip() for part in value.split(",") if part.strip()]

    @classmethod
    def _group_records(cls, lines: List[str]) -> List[Tuple[int, str]]:
        records: List[Tuple[int, str]] = []
        current: List[str] = []
        start_line = 1

        for line_no, raw in enumerate(lines, start=1):
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            if text.upper().startswith("PIPE") or text.upper().startswith("AREA"):
                if current:
                    records.append((start_line, " | ".join(current)))
                current = [text]
                start_line = line_no
            elif current:
                current.append(text)
            else:
                records.append((line_no, text))

        if current:
            records.append((start_line, " | ".join(current)))

        return records

    @staticmethod
    def _reachable_from_heart(pipes: Dict[str, Pipe], target: str) -> bool:
        if target == "heart":
            return True
        queue: List[str] = ["heart"]
        seen: Set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for child in (p.name for p in pipes.values() if current in p.comes_from):
                if child == target:
                    return True
                if child not in seen:
                    queue.append(child)
        return False

    @staticmethod
    def _find_loops(pipes: Dict[str, Pipe]) -> List[str]:
        messages: List[str] = []
        seen: Set[str] = set()
        stack: List[str] = []
        in_stack: Set[str] = set()

        def dfs(node: str) -> None:
            seen.add(node)
            stack.append(node)
            in_stack.add(node)
            for parent in pipes.get(node, Pipe(name=node, size="big", comes_from=[], line_no=-1)).comes_from:
                if parent == "-":
                    continue
                if parent not in pipes:
                    continue
                if parent in in_stack:
                    start_index = stack.index(parent)
                    cycle = stack[start_index:] + [parent]
                    if len(cycle) >= 2:
                        a, b = cycle[0], cycle[1]
                        messages.append(f"ERROR: Loop: {a} comes from {b}, which comes from {a}.")
                    return
                if parent not in seen:
                    dfs(parent)
            stack.pop()
            in_stack.remove(node)

        for node in pipes:
            if node not in seen:
                dfs(node)

        dedup: List[str] = []
        seen_messages: Set[str] = set()
        for msg in messages:
            if msg not in seen_messages:
                dedup.append(msg)
                seen_messages.add(msg)
        return dedup

    @classmethod
    def load_from_file(cls, file_path: str | Path) -> Atlas:
        path = Path(file_path)
        if not path.exists():
            raise AtlasError(f'ERROR: File not found: {path}')

        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or all(not line.strip() or line.strip().startswith("#") for line in lines):
            raise AtlasError("ERROR: The file is empty.")

        atlas = Atlas()
        seen_pipes: Dict[str, Pipe] = {}
        seen_areas: Dict[str, Area] = {}
        errors: List[str] = []
        heart_count = 0

        for line_no, record_text in cls._group_records(lines):
            if not record_text:
                continue
            parts = [part.strip() for part in record_text.split("|") if part.strip()]
            if not parts:
                continue
            kind = parts[0].upper()

            if kind not in {"PIPE", "AREA"}:
                errors.append(f'ERROR: line {line_no}: unknown record type "{parts[0] if parts else ""}". Expected PIPE or AREA.')
                continue

            if kind == "PIPE":
                if len(parts) != 4:
                    errors.append(f'ERROR: line {line_no}: PIPE needs 4 fields, found {len(parts) - 1}.')
                    continue
                _, name, size, source_text = parts
                if name in seen_pipes:
                    first = seen_pipes[name].line_no
                    errors.append(f'ERROR: line {line_no}: pipe "{name}" is defined twice (first on line {first}).')
                    continue
                if size.lower() not in {"big", "small"}:
                    errors.append(f'ERROR: line {line_no}: size must be big or small, found "{size}".')
                    continue
                sources = cls.parse_list(source_text)
                pipe = Pipe(name=name, size=size.lower(), comes_from=sources, line_no=line_no)
                seen_pipes[name] = pipe
                if "-" in sources:
                    heart_count += 1
                continue

            if len(parts) != 5:
                errors.append(f'ERROR: line {line_no}: AREA needs 5 fields, found {len(parts) - 1}.')
                continue
            _, name, fed_by_text, symptoms_text, description = parts
            if name in seen_areas:
                first = seen_areas[name].line_no
                errors.append(f'ERROR: line {line_no}: area "{name}" is defined twice (first on line {first}).')
                continue
            area = Area(
                name=name,
                fed_by=cls.parse_list(fed_by_text),
                symptoms=cls.parse_list(symptoms_text),
                description=description,
                line_no=line_no,
            )
            seen_areas[name] = area

        for pipe in seen_pipes.values():
            atlas.pipes[pipe.name] = pipe
            for parent in pipe.comes_from:
                if parent == "-":
                    continue
                if parent not in seen_pipes:
                    errors.append(f'ERROR: line {pipe.line_no}: pipe "{pipe.name}" comes from "{parent}", which does not exist.')

        for area in seen_areas.values():
            atlas.areas[area.name] = area
            for feeder in area.fed_by:
                if feeder not in seen_pipes:
                    errors.append(f'ERROR: line {area.line_no}: area "{area.name}" is fed by "{feeder}", which does not exist.')

        if heart_count != 1:
            errors.append(f'ERROR: The atlas needs exactly one pipe that comes from "-" (the heart). Found {heart_count}.')

        for pipe_name in list(seen_pipes):
            if pipe_name != "heart" and not cls._reachable_from_heart(seen_pipes, pipe_name):
                errors.append(f'ERROR: Pipe "{pipe_name}" can never receive blood from the heart.')

        for msg in cls._find_loops(seen_pipes):
            errors.append(msg)

        if errors:
            raise AtlasError("\n".join(errors))

        return atlas


def print_atlas_pipes(atlas: Atlas) -> None:
    print("NAME           SIZE    COMES FROM")
    for name in sorted(atlas.pipes):
        pipe = atlas.pipes[name]
        source = "-" if pipe.comes_from == ["-"] else ", ".join(pipe.comes_from)
        print(f"{name:<15} {pipe.size:<8} {source}")
    print(f"{len(atlas.pipes)} pipes")


def print_atlas_areas(atlas: Atlas) -> None:
    print("NAME           FED BY")
    for name in sorted(atlas.areas):
        area = atlas.areas[name]
        print(f"{name:<15} {', '.join(area.fed_by) if area.fed_by else 'none'}")
    print(f"{len(atlas.areas)} areas")


def handle_show(atlas: Atlas, name: Optional[str]) -> None:
    if not name:
        print("ERROR: Missing name. Usage: atlas show <name>")
        return
    if name in atlas.pipes:
        print(atlas.show_pipe(name))
        return
    if name in atlas.areas:
        print(atlas.show_area(name))
        return
    print(f'ERROR: No pipe or area called "{name}".')


def handle_find(atlas: Atlas, word: Optional[str]) -> None:
    if not word:
        print("ERROR: Missing search word. Usage: atlas find <word>")
        return
    matches = atlas.find_areas_by_keyword(word)
    if not matches:
        print(f'No areas match "{word}".')
        return
    print(f'{len(matches)} areas match "{word}":')
    for area in matches:
        print(f"{area.name:<20}{area.description}")


def handle_tree(atlas: Atlas) -> None:
    for line in atlas.tree_lines():
        print(line)


def handle_path(atlas: Atlas, area_name: Optional[str]) -> None:
    if not area_name:
        print("ERROR: Missing area name. Usage: atlas path <area>")
        return
    if area_name not in atlas.areas:
        print(f'ERROR: No area called "{area_name}".')
        return
    routes = atlas.routes_to_area(area_name)
    if not routes:
        print(f'No route from the heart to "{area_name}".')
        return
    print(f"{len(routes)} routes from the heart to {area_name}:")
    for route in routes:
        print(" > ".join(route))


class SynapseApp:
    def __init__(self, default_path: str = "data/atlas.txt") -> None:
        self.current_path = default_path
        self.atlas: Optional[Atlas] = None
        self.cases: List[Case] = load_cases("data/cases.json")
        self.norms: Optional[ClinicNorms] = None
        try:
            self.norms = ClinicNorms("data/norms.txt")
        except ValueError as exc:
            print(str(exc))
            print("Clinic norms not loaded. Clinic commands requiring norms will fail.")
        self.load_atlas(default_path, print_success=True)

    def load_atlas(self, path: str, print_success: bool = True) -> bool:
        try:
            atlas = AtlasLoader.load_from_file(path)
        except AtlasError as exc:
            print(str(exc))
            if self.atlas is not None:
                print(f"Atlas not loaded. Still using {self.current_path}.")
            else:
                print(f"Atlas not loaded. Still using {path}.")
            return False

        self.atlas = atlas
        self.current_path = path
        if print_success:
            print(f"SUCCESS: Atlas loaded from {path}: {len(atlas.pipes)} pipes, {len(atlas.areas)} areas.")
        return True

    # ========================================================================
    # Mission 6: Recovery Clinic — command handler
    # ========================================================================

    def handle_clinic(self, args: List[str]) -> None:
        if not args:
            print("ERROR: Invalid clinic command. Usage: clinic visit <case id> | clinic record <case id> | clinic results <case id> | clinic check <case id> | clinic chart <case id> <test>")
            return

        sub = args[0].lower()
        if sub == "visit":
            if len(args) != 2:
                print("ERROR: Usage: clinic visit <case id>")
                return
            self.clinic_visit(args[1])
        elif sub == "record":
            if len(args) != 2:
                print("ERROR: Usage: clinic record <case id>")
                return
            self.clinic_record(args[1])
        elif sub == "results":
            if len(args) != 2:
                print("ERROR: Usage: clinic results <case id>")
                return
            self.clinic_results(args[1])
        elif sub == "check":
            if len(args) != 2:
                print("ERROR: Usage: clinic check <case id>")
                return
            self.clinic_check(args[1])
        elif sub == "chart":
            if len(args) < 3:
                print("ERROR: Usage: clinic chart <case id> <test>")
                return
            self.clinic_chart(args[1], " ".join(args[2:]))
        else:
            print(f"Unknown clinic command: {args[0]}")

    def _find_case(self, case_id: str) -> Optional[Case]:
        return find_case(self.cases, case_id)

    def _save_all(self) -> None:
        save_cases(self.cases, "data/cases.json")

    # ----- clinic visit -----

    def clinic_visit(self, case_id: str) -> None:
        case = self._find_case(case_id)
        if case is None:
            print(f'ERROR: No case called "{case_id}".')
            return
        if self.norms is None:
            print("ERROR: Clinic norms not loaded.")
            return

        # Days since stroke
        while True:
            days_text = input("Days since the stroke: ").strip()
            try:
                days = int(days_text)
                if days < 1:
                    raise ValueError
                break
            except ValueError:
                print('ERROR: Days since the stroke must be a whole number of 1 or more.')

        # Check duplicate day
        for v in case.visits:
            if v.day == days:
                print(f'ERROR: {case.id} already has a visit on day {days}.')
                return

        print(f"Test 1 of 3: reaction time")
        reaction = test_reaction_time()
        print(f"Average: {reaction} ms (5 rounds)")

        print(f"Test 2 of 3: memory span")
        memory = test_memory_span()
        print(f"Longest row repeated: {memory} digits")

        print(f"Test 3 of 3: colour words")
        colour = test_colour_words()
        print(f"Time: {colour:.1f} s")

        case.visits.append(Visit(day=days, reactionMs=reaction, memoryDigits=memory, colorWordSeconds=colour))
        self._save_all()
        print(f'SUCCESS: Visit on day {days} saved for {case.id}.')

    # ----- clinic record -----

    def clinic_record(self, case_id: str) -> None:
        case = self._find_case(case_id)
        if case is None:
            print(f'ERROR: No case called "{case_id}".')
            return
        if self.norms is None:
            print("ERROR: Clinic norms not loaded.")
            return

        while True:
            days_text = input("Days since the stroke: ").strip()
            try:
                days = int(days_text)
                if days < 1:
                    raise ValueError
                break
            except ValueError:
                print('ERROR: Days since the stroke must be a whole number of 1 or more.')

        for v in case.visits:
            if v.day == days:
                print(f'ERROR: {case.id} already has a visit on day {days}.')
                return

        while True:
            rt_text = input("Reaction time (ms): ").strip()
            try:
                reaction = int(rt_text)
                if reaction <= 0:
                    raise ValueError
                break
            except ValueError:
                print('ERROR: Reaction time must be a whole number of milliseconds above 0.')

        while True:
            mem_text = input("Memory span (digits): ").strip()
            try:
                memory = int(mem_text)
                if memory < 0:
                    raise ValueError
                break
            except ValueError:
                print("ERROR: Memory span must be a whole number of 0 or more.")

        while True:
            cw_text = input("Colour words (seconds): ").strip()
            try:
                colour = float(cw_text)
                break
            except ValueError:
                print("ERROR: Colour words must be a number of seconds.")

        case.visits.append(Visit(day=days, reactionMs=reaction, memoryDigits=memory, colorWordSeconds=colour))
        self._save_all()
        print(f'SUCCESS: Visit on day {days} saved for {case.id}.')

    # ----- clinic results -----

    def clinic_results(self, case_id: str) -> None:
        case = self._find_case(case_id)
        if case is None:
            print(f'ERROR: No case called "{case_id}".')
            return
        if self.norms is None:
            print("ERROR: Clinic norms not loaded.")
            return
        if not case.visits:
            print(f'Case {case.id} has no visits yet.')
            return

        visits = sorted(case.visits, key=lambda v: v.day)
        age = case.age

        try:
            r_norm = self.norms.norm_for_age("reaction", age)
            m_norm = self.norms.norm_for_age("memory", age)
            c_norm = self.norms.norm_for_age("colorword", age)
        except ValueError as exc:
            print(str(exc))
            return

        print(f'{case.name}, {age} · normal for ages {r_norm["from_age"]}-{r_norm["to_age"]}: reaction {r_norm["average"]:.0f} ms, memory {m_norm["average"]:.1f} digits, colour words {c_norm["average"]:.1f} s')
        print()
        print(f'DAY   REACTION           MEMORY        COLOUR WORDS')
        for v in visits:
            r_class = self.norms.classify_value("reaction", age, v.reactionMs)
            m_class = self.norms.classify_value("memory", age, v.memoryDigits)
            c_class = self.norms.classify_value("colorword", age, v.colorWordSeconds)
            r_str = f"{v.reactionMs} ms {r_class}"
            m_str = f"{v.memoryDigits} digits"
            c_str = f"{v.colorWordSeconds:.1f} s {c_class}"
            print(f"{v.day:<4}  {r_str:<18} {m_str:<14} {c_str}")

    # ----- clinic check (Bonus 2) -----

    def clinic_check(self, case_id: str) -> None:
        case = self._find_case(case_id)
        if case is None:
            print(f'ERROR: No case called "{case_id}".')
            return
        if self.norms is None:
            print("ERROR: Clinic norms not loaded.")
            return
        if not case.visits:
            print(f'Case {case.id} has no visits yet.')
            return

        visits = sorted(case.visits, key=lambda v: v.day)
        age = case.age
        latest = visits[-1]

        stopped = stopped_areas_for_pipe(self.atlas, case.likelyPipe)
        stopped_sorted = sorted(stopped)
        print(f'Damage: {case.likelyPipe} blocked -> {", ".join(stopped_sorted)} stopped working')
        print()

        print(f'TEST')
        print(f'DAY {latest.day}')
        print(f'TREND')
        print(f'EXPECTED WEAK')

        field_map = {"reaction": "reactionMs", "memory": "memoryDigits", "colorword": "colorWordSeconds"}
        label_map = {"reaction": "Reaction", "memory": "Memory", "colorword": "Colour words"}
        unit_map = {"reaction": "ms", "memory": "digits", "colorword": "s"}

        flags: List[Tuple[str, str]] = []
        for test_name in ["reaction", "memory", "colorword"]:
            val = getattr(latest, field_map[test_name])
            classification = self.norms.classify_value(test_name, age, val)

            if len(visits) >= 2:
                old_val = getattr(visits[-2], field_map[test_name])
                trend = compute_trend(test_name, old_val, val)
            else:
                trend = "steady"

            expected = test_is_expected_weak(test_name, stopped)

            print(f'{label_map[test_name]}')
            if test_name == "colorword":
                print(f'{val:.1f} {unit_map[test_name]} {classification}')
            else:
                print(f'{val} {unit_map[test_name]} {classification}')
            print(f'{trend}')
            print(f'{"yes" if expected else "no"}')

            if classification in ("below", "well below") and not expected:
                flags.append((test_name, "damage"))
            if trend == "worse":
                flags.append((test_name, "trend"))

        if flags:
            for test_name, kind in flags:
                if kind == "trend":
                    prev_day = visits[-2].day
                    print(f'FLAG: {label_map[test_name]} is getting worse since day {prev_day}.')
                else:
                    classification = self.norms.classify_value(test_name, age, getattr(latest, field_map[test_name]))
                    if classification == "well below":
                        classification_text = "well below normal"
                    elif classification == "below":
                        classification_text = "below normal"
                    else:
                        classification_text = classification
                    print(f'FLAG: {label_map[test_name]} is {classification_text}, and the damage does not explain it.')
            print("Advice: check the patient for a new stroke.")
        else:
            # Explain why below-normal results are not flagged (damage explains them)
            for test_name in ["reaction", "memory", "colorword"]:
                val = getattr(latest, field_map[test_name])
                classification = self.norms.classify_value(test_name, age, val)
                expected = test_is_expected_weak(test_name, stopped)
                if classification in ("below", "well below") and expected:
                    explained = [a for a in TEST_EXPECTED_AREAS[test_name] if a in stopped]
                    classification = self.norms.classify_value(test_name, age, val)
                    if classification == "well below":
                        classification_text = "well below normal"
                    elif classification == "below":
                        classification_text = "below normal"
                    else:
                        classification_text = classification
                    print(f'Her {label_map[test_name].lower()} result is {classification_text}, but it raises no flag: the damage to {", ".join(explained)} explains it.')

    # ----- clinic chart (Bonus 3) -----

    def clinic_chart(self, case_id: str, test_name: str) -> None:
        case = self._find_case(case_id)
        if case is None:
            print(f'ERROR: No case called "{case_id}".')
            return
        if self.norms is None:
            print("ERROR: Clinic norms not loaded.")
            return
        if not case.visits:
            print(f'Case {case.id} has no visits yet.')
            return

        key = self.norms._normalise_test(test_name)
        if key not in ("reaction", "memory", "colorword"):
            print(f'ERROR: Unknown test "{test_name}". Use reaction, memory or colour words.')
            return

        visits = sorted(case.visits, key=lambda v: v.day)
        age = case.age

        try:
            norm_rec = self.norms.norm_for_age(key, age)
        except ValueError as exc:
            print(str(exc))
            return

        average = float(norm_rec["average"])
        spread = float(norm_rec["spread"])
        low = average - spread
        high = average + spread

        field_map = {"reaction": "reactionMs", "memory": "memoryDigits", "colorword": "colorWordSeconds"}
        unit_map = {"reaction": "ms", "memory": "digits", "colorword": "s"}
        label_map = {"reaction": "Reaction time", "memory": "Memory span", "colorword": "Colour words"}
        scale_map = {"reaction": 20, "memory": 1, "colorword": 1}
        lower_better = key != "memory"

        field = field_map[key]
        unit = unit_map[key]
        scale = scale_map[key]

        print(f'{label_map[key]} · {"lower is better" if lower_better else "higher is better"} · normal for age {age}: {low:.0f} to {high:.0f} {unit}')
        for v in visits:
            val = getattr(v, field)
            bars = round(val / scale)
            val_str = f"{val:.1f} {unit}" if key == "colorword" else f"{val} {unit}"
            print(f"Day {v.day:<3} {'#' * bars} {val_str}")

    def handle_command(self, raw_command: str) -> bool:
        command = raw_command.strip()
        if not command:
            return True
        parts = command.split()
        if not parts:
            return True

        if parts[0].lower() == "atlas":
            if len(parts) == 1:
                print("Available atlas commands: atlas load <path> | atlas pipes | atlas areas | atlas show <name> | atlas find <word> | atlas tree | atlas path <area>")
                return True

            action = parts[1].lower()
            if action == "load":
                if len(parts) < 3:
                    print("ERROR: Missing path. Usage: atlas load <path>")
                    return True
                self.load_atlas(parts[2], print_success=True)
                return True

            if self.atlas is None:
                print("ERROR: No atlas is loaded.")
                return True

            if action == "pipes":
                print_atlas_pipes(self.atlas)
                return True
            if action == "areas":
                print_atlas_areas(self.atlas)
                return True
            if action == "show":
                target = " ".join(parts[2:]) if len(parts) > 2 else None
                handle_show(self.atlas, target)
                return True
            if action == "find":
                target = " ".join(parts[2:]) if len(parts) > 2 else None
                handle_find(self.atlas, target)
                return True
            if action == "tree":
                handle_tree(self.atlas)
                return True
            if action == "path":
                target = " ".join(parts[2:]) if len(parts) > 2 else None
                handle_path(self.atlas, target)
                return True

            print(f"Unknown atlas command: {parts[1]}")
            return True

        if parts[0].lower() == "clinic":
            self.handle_clinic(parts[1:])
            return True

        if command.lower() in {"help", "?"}:
            print('Synapse 1.0 · type "help" to see all commands')
            print("Available commands: atlas load <path> | atlas pipes | atlas areas | atlas show <name> | atlas find <word> | atlas tree | atlas path <area> | clinic visit <case id> | clinic record <case id> | clinic results <case id> | clinic check <case id> | clinic chart <case id> <test> | quit")
            return True

        if command.lower() in {"quit", "exit"}:
            raise KeyboardInterrupt

        print(f"Unknown command: {command}")
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synapse Mission 1")
    parser.add_argument("command", nargs="*", help="Optional command to run without starting the interactive shell")
    parser.add_argument("--file", default="data/atlas.txt", help="Path to the atlas file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print('Synapse 1.0 · type "help" to see all commands')
    app = SynapseApp(default_path=args.file)

    if args.command:
        try:
            app.handle_command(" ".join(args.command))
        except KeyboardInterrupt:
            return 0
        return 0 if app.atlas is not None else 1

    try:
        while True:
            try:
                entry = input("synapse> ")
            except EOFError:
                print()
                break
            try:
                app.handle_command(entry)
            except KeyboardInterrupt:
                print("\nGoodbye.")
                break
    except KeyboardInterrupt:
        print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
