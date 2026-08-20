"""Route modules grouped by simulation routes use case."""

from . import (
    activity,
    catalog,
    entities,
    execution,
    interviews,
    preparation,
)

_ROUTE_MODULES = (activity, catalog, entities, execution, interviews, preparation)
