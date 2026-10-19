"""C4: align a covariance panel by session date, never by row position."""
import numpy as np


def aligned_returns(prices, calendar, lookback=250):
    days=list(calendar)[-lookback:]
    if len(days)<lookback:
        return np.empty((0,0)), ()
    columns=[]; names=[]
    for name, observations in sorted(prices.items()):
        values=np.array([observations.get(d,np.nan) for d in days],dtype=float)
        if np.isfinite(values).all() and (values>0).all():
            columns.append(np.diff(np.log(values))); names.append(name)
    return (np.column_stack(columns) if columns else np.empty((lookback-1,0))),tuple(names)
