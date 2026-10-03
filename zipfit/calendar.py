"""RFC 5545 calendar export of public application windows. No profile data."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from .catalog import schedule
from .rules import KST


def windows_for(n):
    if n.get('application_windows'):
        return n['application_windows']
    if n.get('application_start') and n.get('application_end'):
        return [{'label':'신청 접수','start':n['application_start'],'end':n['application_end'],'daily_hours':n.get('daily_hours')}]
    return []


def text(value):
    return str(value).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    # 75 octets, retaining complete UTF-8 characters. Continuation includes SP.
    lines=[];part=''
    for ch in line:
        if len((part+ch).encode('utf-8'))>75:
            lines.append(part);part=' '
        part+=ch
    return '\r\n'.join(lines+[part])


def export_calendar(n, now=None):
    now=now or datetime.now(KST)
    state=schedule(n,now)['state']
    if state not in ('open','upcoming') or not windows_for(n):
        raise ValueError('확인된 접수 중·예정 일정만 저장할 수 있어요.')
    if n.get('rule_model'):
        from .rules import evaluate
        from .models import Profile
        if evaluate(n,Profile(),now)['version_stale']:
            raise ValueError('원문을 다시 확인한 뒤 일정을 저장할 수 있어요.')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//ZipFit//Housing dates//KO','CALSCALE:GREGORIAN']
    stamp=now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for index,w in enumerate(windows_for(n)):
        spans=[]
        if 'T' in w['start'] and 'T' in w['end']:
            start,end=datetime.fromisoformat(w['start']),datetime.fromisoformat(w['end'])
            if not start.tzinfo or not end.tzinfo or end<=start:
                raise ValueError('접수 시간 확인이 필요해요.')
            if w.get('daily_hours'):
                if (end-start).days>366: raise ValueError('일정 범위 초과')
                opens,closes=[time.fromisoformat(v) for v in w['daily_hours']]
                day=start.astimezone(KST).date()
                while day<=end.astimezone(KST).date():
                    a=max(start,datetime.combine(day,opens,KST));b=min(end,datetime.combine(day,closes,KST))
                    if a<b: spans.append((a,b,day.isoformat()))
                    day+=timedelta(days=1)
            else: spans=[(start,end,'period')]
            fmt=lambda dt:dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            events=[('DTSTART:'+fmt(a),'DTEND:'+fmt(b),key) for a,b,key in spans if b>now]
            qualifier=''
        else:
            a,b=date.fromisoformat(w['start'][:10]),date.fromisoformat(w['end'][:10])
            if b<a: raise ValueError('접수 날짜 확인이 필요해요.')
            events=[] if b<now.astimezone(KST).date() else [('DTSTART;VALUE=DATE:'+a.strftime('%Y%m%d'),'DTEND;VALUE=DATE:'+(b+timedelta(days=1)).strftime('%Y%m%d'),'period')]
            qualifier=' · 시간은 원문 확인'
        for a,b,key in events:
            uid=hashlib.sha256(f'{n["id"]}:{index}:{key}'.encode()).hexdigest()+'@zipfit'
            description=f"{w.get('hours_note','')}\n신청 자격과 정정 여부는 공식 원문에서 확인하세요. 저장한 일정은 자동 갱신되지 않습니다.\n{n['url']}"
            lines+=['BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+stamp,a,b,'SUMMARY:'+text(n['title']+' · '+w['label']+qualifier),'DESCRIPTION:'+text(description),'URL:'+n['url'],'TRANSP:TRANSPARENT','END:VEVENT']
    if 'BEGIN:VEVENT' not in lines: raise ValueError('남은 접수 일정이 없어요.')
    return '\r\n'.join(fold(line) for line in lines+['END:VCALENDAR'])+'\r\n'
