from pydantic import BaseModel


class ComparisonPartner(BaseModel):
    """A model compared side by side with a `ComparedModelStat`'s model."""

    model_id: int
    brand: str
    model: str
    # In how many comparisons the two models appeared together.
    count: int


class ComparedModelStat(BaseModel):
    """One model in the "most compared models" statistic."""

    model_id: int
    brand: str
    model: str
    # In how many displayed comparisons the model appeared.
    comparisons: int
    # How many of those compared 2+ of its own trims/engines.
    within_model: int
    # The models it was most often compared with, most frequent first.
    partners: list[ComparisonPartner]


class ComparisonStats(BaseModel):
    """The admin console's comparison statistic for one period."""

    # Displayed comparisons in the period.
    total: int
    # The most compared models, most frequent first.
    models: list[ComparedModelStat]
