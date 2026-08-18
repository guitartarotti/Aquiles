import sys, os, io, types, logging
logging.disable(logging.WARNING)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

class _S(types.ModuleType):
    class _A:
        def __init__(self,*a,**kw): pass
        def __call__(self,*a,**kw): return type(self)()
        def __getattr__(self,n): return type(self)()
    def __getattr__(self,n): return self._A()
for m in ["neo4j","graphiti_core","openai","anthropic","zep_cloud","blpapi"]:
    if m not in sys.modules: sys.modules[m]=_S(m)
class _C:
    def __init__(self,*a,**kw): pass
sys.modules["openai"].OpenAI = _C
sys.modules["anthropic"].Anthropic = _C
_svc = types.ModuleType("app.services")
_svc.__path__ = [os.path.join(BACKEND,"app","services")]
_svc.__package__ = "app.services"
sys.modules["app.services"] = _svc

import datetime
from app.services.options_store import OptionsStore

store = OptionsStore()
print("volume_dir:", store.volume_dir)

# 1. load (deve ser vazio ou ter o que ja existe)
state = store.load_volume_state()
print(f"load_volume_state: {len(state)} simbolos")

# 2. save
store.save_volume_state({'IBOVF178': 500.0, 'IBOVG180': 0.0, 'IBOVH195': 1200.0})
state2 = store.load_volume_state()
print("Apos save:", state2)

# 3. append events
events = [
    {
        'event_id': 'abc001',
        'captured_at': datetime.datetime.utcnow().isoformat(),
        'session_date': datetime.date.today().isoformat(),
        'underlying_security': 'IBOVE Index',
        'symbol': 'IBOVF178',
        'put_call': 'C',
        'strike': 130000.0,
        'expiry_date': '2025-06-20',
        'days_to_maturity': 36,
        'volume_before': 400.0,
        'volume_after': 500.0,
        'volume_delta': 100.0,
        'spot_price': 131000.0,
        'close': 450.0,
        'bid': 440.0,
        'ask': 460.0,
    },
    {
        'event_id': 'abc002',
        'captured_at': datetime.datetime.utcnow().isoformat(),
        'session_date': datetime.date.today().isoformat(),
        'underlying_security': 'IBOVE Index',
        'symbol': 'IBOVG180',
        'put_call': 'P',
        'strike': 128000.0,
        'expiry_date': '2025-07-18',
        'days_to_maturity': 64,
        'volume_before': 0.0,
        'volume_after': 300.0,
        'volume_delta': 300.0,
        'spot_price': 131000.0,
        'close': None,
        'bid': 120.0,
        'ask': 140.0,
    },
]
written = store.append_volume_activity(events)
print(f"Events written: {written}")

# 4. read
rows = store.read_volume_activity()
print(f"Read events: {len(rows)}")
for r in rows[:3]:
    print(f"  {r['symbol']} delta={r['volume_delta']} vol={r['volume_before']}->{r['volume_after']}")

# 5. summary
summ = store.volume_activity_summary()
print(f"Summary: {summ}")

print("\nALL OK")
