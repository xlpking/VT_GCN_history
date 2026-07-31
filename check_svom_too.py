import sys; sys.path.insert(0,'.')
from vt_store import get_store
store = get_store()
events = store.upper_limit_events()

svom_too = [ev for ev in events if ev['is_svom'] and not ev['is_auto_followup']]
with open('check_svom_too.txt', 'w') as f:
    f.write(f'SVOM/ECLAIRs ToO events with only upper limits: {len(svom_too)}\n\n')
    for ev in svom_too:
        f.write(f'{ev["event"]:<25} delay={ev["delay_hr"]}h gcns={ev["gcns"]}\n')
        for r in store.all_records():
            evt_name = (r.get('event_name','') or '')
            if evt_name == ev['event']:
                cid = r.get('circularId')
                d = r.get('trigger_to_obs_hr')
                body = r.get('body','') or ''
                is_auto = any(k in body.lower() for k in ['automatic slew','auto slew','slew of the platform'])
                small_delay = isinstance(d, (int,float)) and d <= 1.0
                if is_auto or small_delay:
                    f.write(f'  >>> GCN{cid} delay={d}h auto={is_auto} -- POSSIBLE AUTO FOLLOWUP\n')
        f.write('\n')
print('Done, written to check_svom_too.txt')
