"""Economic order quantity helper (classic Wilson formula)."""
import math


def eoq_annual(demand_annual: float, ordering_cost: float, holding_cost_per_unit: float) -> float:
    if demand_annual <= 0 or ordering_cost <= 0 or holding_cost_per_unit <= 0:
        return 0.0
    return math.sqrt((2 * demand_annual * ordering_cost) / holding_cost_per_unit)


def suggest_reorder_qty(
    daily_usage: float,
    lead_time_days: int,
    ordering_cost: float = 25.0,
    holding_fraction_of_cost: float = 0.2,
    unit_cost: float = 1.0,
) -> float:
    """Heuristic EOQ using annualized demand from daily usage."""
    annual = max(daily_usage * 365, 1.0)
    h = max(unit_cost * holding_fraction_of_cost, 0.01)
    q = eoq_annual(annual, ordering_cost, h)
    return max(round(q, 2), daily_usage * lead_time_days * 2 or 1.0)
