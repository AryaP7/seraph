"""Read-only input readiness evidence; excludes credentials."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from seraph.store.bootstrap import resolve_dsn
async def main():
 import asyncpg
 c=await asyncpg.connect(resolve_dsn(),timeout=10)
 try:
  async with c.transaction(readonly=True):
   out={}
   for t in ('intraday_bars','macro_covariates'):
    out[t]={'count':await c.fetchval('SELECT count(*) FROM '+t)}
   out['macro_columns']=[dict(r) for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='macro_covariates'")]
   out['macro_coverage']=[dict(r) for r in await c.fetch('SELECT min(date),max(date),count(rbi_repo_rate),min(rbi_repo_rate),max(rbi_repo_rate) FROM macro_covariates')]
   print(json.dumps(out,default=str,indent=2))
 finally: await c.close()
asyncio.run(main())
