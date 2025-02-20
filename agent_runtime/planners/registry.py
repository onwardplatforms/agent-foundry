from enum import Enum
from typing import Dict, Type

from .base import BasePlanner
from .stepwise import StepwisePlanner


class PlannerType(Enum):
    """Supported planner types."""

    STEPWISE = "stepwise"


# Registry of planner implementations
PLANNER_REGISTRY: Dict[PlannerType, Type[BasePlanner]] = {
    PlannerType.STEPWISE: StepwisePlanner,
}


def get_planner(planner_type: PlannerType, **kwargs) -> BasePlanner:
    """
    Get a planner instance by type.

    Args:
        planner_type: Type of planner to instantiate
        **kwargs: Additional arguments to pass to planner constructor

    Returns:
        An instance of the requested planner
    """
    planner_class = PLANNER_REGISTRY.get(planner_type)
    if not planner_class:
        raise ValueError(f"Unknown planner type: {planner_type}")

    return planner_class(**kwargs)
