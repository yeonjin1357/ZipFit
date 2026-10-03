"""Read explicitly labelled application periods; never guess from document dates."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import re
import time
from bs4 import BeautifulSoup
import requests

from .catalog import RUNTIME, load_catalog, schedule
from .rules import KST
from .verification import fetch, digest


class NeedsSourceReview(ValueError):
    """A correction link requires manual inspection, not a retry loop."""


def parse_lh(raw):
    html = raw.decode('utf-8')
    soup = BeautifulSoup(html, 'lxml')
    if not soup.select_one('#sub_container'):
        raise ValueError('LH 상세 구조 확인 실패')
    signals = {}
    for key in ('currPanId', 'currPanKdCd'):
        match = re.search(r'var\s+' + key + r"\s*=\s*['\"]([^'\"]*)['\"]", html)
        if not match:
            raise ValueError('정정·취소 연결 확인 실패')
        signals[key] = match[1]
    if any(signals.values()):
        raise NeedsSourceReview('정정·취소 공고 연결 확인 필요')
    windows = []
    if soup.select_one('#sta_acpDt'):
        values = {}
        for key in ('sbscAcpStDt','sbscAcpClsgDt','sbscAcpStHm','sbscAcpClsgHm'):
            match = re.search(r'var\s+' + key + r"\s*=\s*['\"]([^'\"]*)['\"]", html)
            values[key] = match[1].strip() if match else ''
        if values['sbscAcpStDt'] and values['sbscAcpClsgDt']:
            start = datetime.strptime(values['sbscAcpStDt'], '%Y.%m.%d').date().isoformat()
            end = datetime.strptime(values['sbscAcpClsgDt'], '%Y.%m.%d').date().isoformat()
            # Detailed daily restrictions still require the PDF; keep this a
            # date-level period, with source times displayed as a reference.
            windows.append({'label':'청약 접수기간 (기관 상세)', 'start':start,'end':end,'hours_note':f"시작 {values['sbscAcpStHm'] or '시간 미확인'} / 마감 {values['sbscAcpClsgHm'] or '시간 미확인'} · 일별 운영시간은 원문 확인"})
        else:
            dates=re.findall(r'20\d{2}\.\d{2}\.\d{2}',soup.select_one('#sta_acpDt').get_text(' ',strip=True))
            if len(dates)==2:
                start,end=[datetime.strptime(v,'%Y.%m.%d').date().isoformat() for v in dates]
                windows.append({'label':'청약 접수기간 (기관 상세)','start':start,'end':end,'hours_note':'공급 유형별·일별 접수 시간은 원문 확인'})
    # Separate supply rows take precedence over a page-wide aggregate period.
    # Otherwise the days between two rounds would incorrectly look open.
    detailed = []
    for table in soup.select('table'):
        headers = [c.get_text(' ',strip=True) for c in table.select('thead th')]
        period_cols = [i for i,h in enumerate(headers) if '접수' in h and ('기간' in h or '일시' in h) and '서류' not in h]
        if len(period_cols) != 1:
            continue
        idx = period_cols[0]
        for row in table.select('tbody tr'):
            cells = row.find_all(['td','th'],recursive=False)
            if len(cells) != len(headers) or any(c.get('rowspan') or c.get('colspan') for c in cells):
                continue
            dates = re.findall(r'20\d{2}[.-]\d{2}[.-]\d{2}',cells[idx].get_text(' ',strip=True))
            if len(dates) != 2:
                continue
            start,end = [datetime.strptime(v.replace('.','-'),'%Y-%m-%d').date().isoformat() for v in dates]
            label = ' · '.join(c.get_text(' ',strip=True) for c in cells[:idx]) or '청약 접수'
            if '서류' in label or '발표' in label:
                continue
            detailed.append({'label':label[:160],'start':start,'end':end,'hours_note':'공급 유형별 시간은 원문 확인'})
    if detailed:
        windows = detailed
    unique = {json.dumps(w,sort_keys=True):w for w in windows}
    windows = list(unique.values())
    if len(windows)>30 or any(w['end']<w['start'] for w in windows):
        raise ValueError('신청 기간 범위를 확인해야 해요')
    return windows


def refresh_one(n, now):
    result = dict(n)
    record = {'checked_at':now.isoformat(), 'url':n['url'], 'state':'unknown'}
    try:
        with requests.Session() as session:
            session.headers['User-Agent']='ZipFit/0.1 (public schedule reader)'
            raw=fetch(session,n['url'],4*1024*1024)
        windows=parse_lh(raw)
        previous=n.get('application_windows')
        if previous and previous != windows:
            result['schedule_changes']={'before':previous,'after':windows,'checked_at':now.isoformat()}
        result['application_windows']=windows
        result['schedule_invalidated']=False
        record.update(state='extracted' if windows else 'unknown',sha256=digest(raw))
    except (ValueError, requests.RequestException) as exc:
        record.update(state='error',error=str(exc)[:240],error_kind='needs_review' if isinstance(exc,NeedsSourceReview) else 'fetch_or_parse')
        result['schedule_invalidated']=True
    result['schedule_source']=record
    time.sleep(.15)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=60,choices=range(1,201))
    args=parser.parse_args();c=load_catalog();now=datetime.now(KST)
    candidates=[n for n in c['notices'] if n['source']=='LH' and n['kind']=='recruitment' and not n.get('schedule_reviewed') and schedule(n,now)['state'] not in ('closed','superseded')]
    candidates.sort(key=lambda n:(n.get('schedule_source',{}).get('checked_at',''), -(int((n.get('published_date') or '0000-00-00').replace('-','')))))
    with ThreadPoolExecutor(max_workers=3) as pool:
        updates={n['id']:n for n in pool.map(lambda n:refresh_one(n,now),candidates[:args.limit])}
    c['notices']=[updates.get(n['id'],n) for n in c['notices']]
    c['schedule_refresh']={'checked_at':now.isoformat(),'attempted':len(updates),'extracted':sum(n['schedule_source']['state']=='extracted' for n in updates.values()),'errors':sum(n['schedule_source']['state']=='error' for n in updates.values())}
    temp=RUNTIME.with_suffix('.tmp');temp.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(RUNTIME)
    print(json.dumps(c['schedule_refresh']))


if __name__=='__main__': main()
