"""C7/C10 audit supplement (FR20–24, FR32–37): episode credit and fit starts.

No new predictive candidates, parameter fitting, or production mutations.
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
from seraph.prediction.evaluation import episode_spans
from seraph.pillars.hamilton.engine import MultivariateTVTPHamilton


def main():
    predictions=pd.read_parquet(OUT/'experiment/predictions.parquet')
    episodes=[]
    for (target,name),g in predictions.groupby(['target','model']):
        g=g.sort_values('date').reset_index(drop=True)
        for s,e in episode_spans(g.alarm):
            y=g.label.iloc[s:e]
            episodes.append(dict(target=target,model=name,start=str(g.date.iloc[s].date()),
                end=str(g.date.iloc[e-1].date()),sessions=int(e-s),
                positive_decision_days=int(y.eq(1).sum()),
                outcome='pending' if y.isna().any() else 'target_overlap' if y.eq(1).any() else 'false_alarm'))
    pd.DataFrame(episodes).to_csv(OUT/'experiment/episodes.csv',index=False)

    model=MultivariateTVTPHamilton(np.random.default_rng(410).normal(size=(300,3)))
    rng=np.random.default_rng(0)
    starts=[]
    for i in range(4):
        params=model.start_params.copy()
        index=model.parameters['regime_transition']
        params[index]=rng.uniform(-2,2,size=params[index].size)
        transition=model.regime_transition_matrix(params)
        starts.append(dict(restart=i,minimum=float(transition.min()),maximum=float(transition.max()),
                           valid_probabilities=bool(((transition>=0)&(transition<=1)).all())))
    assert not any(s['valid_probabilities'] for s in starts)
    (OUT/'supplement.json').write_text(json.dumps(dict(
        original_constant_transition_restarts=starts,
        scope='Exact default seed/draw construction in original engine.fit; constant-transition branch only',
        note='A source-level initialization defect, not proof the selected final fit is invalid.'
    ),indent=2),encoding='utf-8')
    print('Saved all candidate alarm episodes and original constant-transition restart counterexample.')


if __name__=='__main__':
    main()
