import sys; sys.path.insert(0,'.')
from vt_store import get_store
store = get_store()
with open('check_auto.txt','w') as f:
    for cid in [39047, 39917, 42712, 45230]:
        for r in store.all_records():
            if r.get('circularId') == cid:
                body = r.get('body','')
                f.write(f'=== GCN{cid} {r.get("subject","")[:60]} ===\n')
                for line in body.splitlines():
                    ln = line.strip()
                    if any(k in ln.lower() for k in ['began','start','automatic','slew','seconds','minutes','hour']):
                        if len(ln) < 200:
                            f.write(f'  {ln}\n')
                f.write('\n')
print('Done')
