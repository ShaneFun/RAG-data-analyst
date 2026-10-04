"""Load the evaluation questions."""
from pathlib import Path

import yaml

QUESTIONS_PATH = Path(__file__).with_name("questions.yaml")


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
