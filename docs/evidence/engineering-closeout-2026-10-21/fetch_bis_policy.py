"""Read-only bounded retrieval of published BIS daily India policy observations."""
from datetime import datetime, timezone, timedelta
import hashlib,json
from pathlib import Path
import requests
root=Path(__file__).resolve().parent
url="https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.IN?startPeriod=2025-06-01&endPeriod=2026-08-21&format=csvfile"
result=dict(url=url,retrieved_at=datetime.now(timezone(timedelta(hours=5,minutes=30))).isoformat())
try:
 response=requests.get(url,timeout=(10,25),headers={"Accept":"text/csv"})
 result.update(status=response.status_code,content_type=response.headers.get("Content-Type"),bytes=len(response.content))
 if response.status_code==200:
  (root/"bis-india-policy.csv").write_bytes(response.content)
  result["sha256"]=hashlib.sha256(response.content).hexdigest()
except requests.RequestException as exc:
 result["error"]=str(exc)
(root/"bis-policy-retrieval.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
