from collections.abc import Iterable

from app.core.constants import DealState

_ALLOWED_TRANSITIONS: dict[DealState, set[DealState]] = {
    DealState.LEAD: {DealState.PRE_QUALIFYING, DealState.CLOSED_LOST},
    DealState.PRE_QUALIFYING: {DealState.QUALIFIED, DealState.DISQUALIFIED, DealState.CLOSED_LOST},
    DealState.DISQUALIFIED: {DealState.LEAD},
    DealState.QUALIFIED: {DealState.ENGAGED, DealState.CLOSED_LOST},
    DealState.ENGAGED: {DealState.PROFILED, DealState.CLOSED_LOST},
    DealState.PROFILED: {DealState.MATCHING, DealState.CLOSED_LOST},
    DealState.MATCHING: {DealState.VEHICLE_SELECTED, DealState.CLOSED_LOST},
    DealState.VEHICLE_SELECTED: {DealState.FUNDING, DealState.CLOSED_LOST},
    DealState.FUNDING: {DealState.ACQUISITION_PENDING, DealState.CLOSED_LOST, DealState.EXCEPTION},
    DealState.ACQUISITION_PENDING: {DealState.ACQUIRED, DealState.CLOSED_LOST, DealState.EXCEPTION},
    DealState.ACQUIRED: {DealState.IN_TRANSIT, DealState.EXCEPTION},
    DealState.IN_TRANSIT: {DealState.DELIVERED, DealState.EXCEPTION},
    DealState.DELIVERED: {DealState.RETURN_PENDING, DealState.CLOSED_WON, DealState.EXCEPTION},
    DealState.RETURN_PENDING: {DealState.CLOSED_LOST, DealState.EXCEPTION},
    DealState.EXCEPTION: {
        DealState.PRE_QUALIFYING,
        DealState.QUALIFIED,
        DealState.ENGAGED,
        DealState.PROFILED,
        DealState.MATCHING,
        DealState.VEHICLE_SELECTED,
        DealState.FUNDING,
        DealState.ACQUISITION_PENDING,
        DealState.ACQUIRED,
        DealState.IN_TRANSIT,
        DealState.DELIVERED,
        DealState.RETURN_PENDING,
        DealState.CLOSED_LOST,
        DealState.CLOSED_WON,
    },
    DealState.CLOSED_WON: set(),
    DealState.CLOSED_LOST: set(),
}


def can_transition(current: DealState, target: DealState) -> bool:
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def next_allowed(current: DealState) -> Iterable[DealState]:
    return _ALLOWED_TRANSITIONS.get(current, set())
