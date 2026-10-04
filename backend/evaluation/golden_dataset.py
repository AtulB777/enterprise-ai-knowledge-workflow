"""The evaluation framework's golden dataset (spec §27/§28): a small,
versioned, reproducible set of synthetic documents and queries with
hand-labeled ground truth. Lives in version control as plain data — a
change to it is a reviewable diff, not something generated at runtime.
"""

from dataclasses import dataclass

DATASET_VERSION = "v1"


@dataclass(frozen=True)
class GoldenDocument:
    filename: str
    content: str


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    query: str
    # Ground truth: which of GOLDEN_DOCUMENTS' filenames should be retrieved
    # for this query. Empty means "nothing in this dataset is relevant" —
    # used to verify the system doesn't force a match where none exists.
    relevant_filenames: frozenset[str]


GOLDEN_DOCUMENTS: list[GoldenDocument] = [
    GoldenDocument(
        filename="vacation_policy.txt",
        content=(
            "Employees receive 20 days of paid vacation per year, accrued monthly. "
            "Unused vacation days roll over up to a maximum of 5 days into the next year."
        ),
    ),
    GoldenDocument(
        filename="remote_work_policy.txt",
        content=(
            "Employees may work remotely up to three days per week with manager approval. "
            "Fully remote arrangements require VP-level sign-off and are reviewed quarterly."
        ),
    ),
    GoldenDocument(
        filename="expense_policy.txt",
        content=(
            "Business travel expenses under $75 do not require a receipt. "
            "All expense reports must be submitted within 30 days of the trip."
        ),
    ),
    GoldenDocument(
        filename="onboarding_guide.txt",
        content=(
            "New employees complete a two-week onboarding program covering company systems, "
            "security training, and introductions to their team."
        ),
    ),
    GoldenDocument(
        filename="astronomy_facts.txt",
        content=(
            "Telescopes allow astronomers to observe distant galaxies and orbiting planets. "
            "The Hubble Space Telescope has operated in orbit since 1990."
        ),
    ),
]


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        case_id="vacation-days",
        query="How many vacation days do employees get per year?",
        relevant_filenames=frozenset({"vacation_policy.txt"}),
    ),
    GoldenCase(
        case_id="remote-work-days",
        query="How many days per week can employees work remotely?",
        relevant_filenames=frozenset({"remote_work_policy.txt"}),
    ),
    GoldenCase(
        case_id="expense-receipt-threshold",
        query="Do I need a receipt for a small business expense?",
        relevant_filenames=frozenset({"expense_policy.txt"}),
    ),
    GoldenCase(
        case_id="onboarding-length",
        query="How long is the new employee onboarding program?",
        relevant_filenames=frozenset({"onboarding_guide.txt"}),
    ),
    GoldenCase(
        case_id="unrelated-topic",
        query="What is the capital of France?",
        relevant_filenames=frozenset(),
    ),
]
