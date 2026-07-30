"""收集网页顶部统计数据 + VT探测率 + VT only"""
import json, config
from vt_parser import enrich
from vt_store import get_store
from collections import Counter

store = get_store()
recs = store.all_records()
stats = store.stats()

# 基础统计
result = {
    'total': stats['total'],
    'detection_count': stats['detection_count'],
    'upper_limit_count': stats['upper_limit_count'],
    'stellar_flare_count': stats['stellar_flare_count'],
    'clarification_count': stats['clarification_count'],
    'events_count': stats['events_count'],
    'median_delay_hr': stats.get('median_delay_hr'),
    'frac_within_2h': stats.get('frac_within_2h'),
    'frac_within_6h': stats.get('frac_within_6h'),
}

# VT 探测率 = 探测数 / (探测数 + 上限数)
det = stats['detection_count']
ul = stats['upper_limit_count']
result['detection_rate'] = det / (det + ul) if (det + ul) > 0 else 0

# VT only: SVOM/ECLAIRs触发的探测
svom_recs = [r for r in recs if (r.get('trigger_source') or '').startswith('SVOM')]
svom_det = [r for r in svom_recs if r.get('report_type') == 'detection']
svom_ul = [r for r in svom_recs if r.get('report_type') == 'upper_limit']
result['svom_total'] = len(svom_recs)
result['svom_det'] = len(svom_det)
result['svom_ul'] = len(svom_ul)
result['svom_det_rate'] = len(svom_det) / (len(svom_det)+len(svom_ul)) if (len(svom_det)+len(svom_ul)) > 0 else 0

# 外部卫星触发的统计
ext_recs = [r for r in recs if not (r.get('trigger_source') or '').startswith('SVOM')]
ext_det = [r for r in ext_recs if r.get('report_type') == 'detection']
ext_ul = [r for r in ext_recs if r.get('report_type') == 'upper_limit']
result['ext_total'] = len(ext_recs)
result['ext_det'] = len(ext_det)
result['ext_ul'] = len(ext_ul)
result['ext_det_rate'] = len(ext_det) / (len(ext_det)+len(ext_ul)) if (len(ext_det)+len(ext_ul)) > 0 else 0

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
