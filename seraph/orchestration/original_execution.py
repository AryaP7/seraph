"""Fresh original C4/C5/C6/C7 execution against a read-only source connection.

No E1-E14 writes. Historical cutoff is applied in SQL before feature fitting.
This path is deliberately separate from the verified archive adapter; current
jump-calibration results must never inherit old Hawkes validation claims.
"""
from datetime import date, datetime
import hashlib
import numpy as np
from seraph.features.alignment import aligned_returns
from seraph.market_calendar import SessionCalendar
from seraph.ingestion.hawkes_universe import build_symbol_list
from seraph.pillars.rmt.engine import RmtEngine, T_WINDOW
from seraph.pillars.hawkes.engine import estimate_state
from seraph.orchestration.hamilton_causal import walk_forward, causal_tvtp_exog, DEFAULT_INITIAL_TRAIN


class CutoffIntradayReader:
    def __init__(self, conn, cutoff):
        self.conn,self.cutoff=conn,cutoff

    async def fetch(self, sql, symbol):
        # Used only by load_stream's fixed E1 query. Fail on interface drift.
        expected='SELECT ts, close FROM intraday_bars WHERE symbol=$1 ORDER BY ts'
        if sql!=expected:
            raise ValueError('Unexpected intraday reader query')
        return await self.conn.fetch(
            'SELECT ts, close FROM intraday_bars WHERE symbol=$1 AND ts<=$2 ORDER BY ts',
            symbol,self.cutoff)


async def execute_originals(conn, day):
    """Prepare real features, then invoke all three original estimators.

    Minimum histories and native estimator defaults are retained. Hamilton
    fitting is chronological and diagnostic-only, never smoothed output.
    """
    from scripts.write_hawkes_production import load_stream, tod_profile
    from scripts.build_observations import build_row, universe_for
    # FIX01: the cutoff is the session's declared close, not a fixed 15:30.
    ts=SessionCalendar().close_timestamp(day); cutoff=datetime.fromisoformat(ts)
    end=date.fromisoformat(day)
    members=await universe_for(conn,end)
    if not members:
        raise ValueError('No point-in-time universe at requested cutoff')
    # An ineligible pillar declares its absence type explicitly (FIX02).
    output={p:dict(model='original '+p,origin='fresh read-only source execution',
        score_eligible=False,value=None,information_timestamp=ts,detail=None,
        absence='structural',absence_reason='insufficient_history',
        reason='insufficient data')
        for p in ('hawkes','rmt','hamilton')}
    audit={'cutoff':ts,'errors':{},'input_hashes':{},'limitations':[
        'RMT spectral-state warmup uses two endpoint windows; SCA calibration is incomplete',
        'Fresh corrected intraday detector has not received corpus-wide empirical validation',
        'Original Hamilton regime support remains unvalidated; output is diagnostic only']}
    rows=await conn.fetch('SELECT symbol,date,adj_close FROM daily_prices WHERE symbol=ANY($1::text[]) '
                          'AND date<=$2 AND adj_close>0 ORDER BY date,symbol',members,end)
    calendar=sorted({r['date'] for r in rows})
    px={s:{} for s in members}
    for r in rows: px[r['symbol']][r['date']]=float(r['adj_close'])
    rmt=RmtEngine()
    if calendar and calendar[-1]==end and len(calendar)>=T_WINDOW+2:
        last=None
        for days in (calendar[:-1],calendar):
            panel,keep=aligned_returns(px,days,T_WINDOW+1)
            if len(keep)<30: break
            audit['input_hashes']['rmt_'+str(days[-1])]=hashlib.sha256(panel.tobytes()).hexdigest()
            last=rmt.step(returns=panel,members=keep,date=days[-1].isoformat())
        if last and last.status=='ok' and len(keep)>=30:
            detail,sca=last.value
            output['rmt'].update(score_eligible=True,value=rmt._prev_share,
                detail={'spectral':detail.model_dump(),'sca_t':sca},reason=None,
                absence=None,absence_reason=None)
            audit['limitations'].extend(w.message for w in last.warnings)
    try:
        stream=await load_stream(CutoffIntradayReader(conn,cutoff),list(build_symbol_list(members)))
        unique=np.unique(stream['day'])
        if len(unique)>=500 and unique[-1]==end:
            start=int(np.searchsorted(stream['day'],unique[-500]))
            counts=stream['n_neg'][start:]; sessions=stream['new_sess'][start:]
            tod=stream['tod_index'][start:]
            profile=tod_profile(counts,tod,stream['n_slots'])
            audit['input_hashes']['hawkes_counts']=hashlib.sha256(counts.tobytes()).hexdigest()
            result=estimate_state(counts=counts,session_starts=sessions,tod_profile=profile,tod_index=tod,
                n_neg=int(counts.sum()),n_pos=int(stream['n_pos'][start:].sum()))
            if result.status=='ok':
                detail,mts=result.value; n=detail.branching_ratio
                output['hawkes'].update(score_eligible=True,value=n/(1-n),
                    detail={'hawkes':detail.model_dump(),'mts':mts,'data_quality':stream['dq']},reason=None,
                    absence=None,absence_reason=None)
                audit['limitations'].extend(w.message for w in result.warnings)
            else: audit['errors']['hawkes']=str(result.error)
    except (ValueError,TypeError) as exc:
        audit['errors']['hawkes']=str(exc)
    # Rebuild C4 observations with date-aligned panels; do not reuse E8's
    # in-sample posteriors or unversioned historical feature rows.
    dates=[]; observations=[]
    for d in calendar:
        if d<date(2005,1,1): continue
        historical_members=await universe_for(conn,d)
        row=await build_row(conn,d,historical_members)
        if row is not None:
            dates.append(d.isoformat()); observations.append(row[1:4])
    if len(dates)>DEFAULT_INITIAL_TRAIN and dates[-1]==day:
        y=np.asarray(observations)
        audit['input_hashes']['hamilton_y']=hashlib.sha256(y.tobytes()).hexdigest()
        # One endpoint fit, trained strictly before the requested date.
        result=walk_forward(dates,y,causal_tvtp_exog(y[:,0]),initial_train=len(dates)-1)
        output['hamilton'].update(detail={'xi':result.xi[:,-1].tolist(),
            'lsd':float(result.lsd()[-1]),'train_end_exclusive':len(dates)-1,
            'converged':result.blocks[-1].converged},
            absence='structural',absence_reason='no_data_coverage',
            exclusion='standing research decision (NOT_PRODUCTION); not a feed outage',
            reason='regime support unvalidated; diagnostic only')
    return output,audit
