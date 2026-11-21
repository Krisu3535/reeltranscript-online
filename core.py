"""URL normalization, CSV exports, SRT subtitles and resumable checkpoints."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_URLS = 500
MAX_CHECKPOINT_BYTES = 20 * 1024 * 1024
COLUMNS = ('url', 'title', 'status', 'language', 'transcript', 'error', 'srt')
EXPORT_COLUMNS = COLUMNS[:-1]
HOSTS = frozenset({'facebook.com','www.facebook.com','m.facebook.com','web.facebook.com','mbasic.facebook.com','fb.watch','fb.com','www.fb.com'})
CONTENT_QUERY_KEYS = frozenset({'v','id','story_fbid','fbid','video_id'})
URL_RE = re.compile(r'https?://[^\s\'"<>,;]+', re.IGNORECASE)


def normalize_facebook_url(raw: str) -> str | None:
    if not isinstance(raw,str):
        return None
    raw = raw.strip().rstrip('.,;!)]}').replace('&amp;','&')
    if '\\' in raw or any(ord(ch) < 32 for ch in raw):
        return None
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or '').lower()
        if parts.scheme.lower() not in ('https','http') or host not in HOSTS or parts.username is not None or parts.password is not None or parts.port not in (None,80,443):
            return None
        if not parts.path or parts.path == '/':
            return None
        query = urlencode([(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=False) if k.lower() in CONTENT_QUERY_KEYS])
        return urlunsplit(('https',host,parts.path,query,''))
    except (ValueError,TypeError):
        return None


def extract_links(text: str, limit: int=MAX_URLS) -> list[str]:
    found=[]
    seen=set()
    for token in URL_RE.findall(text or ''):
        url=normalize_facebook_url(token)
        if url and url not in seen:
            seen.add(url)
            found.append(url)
            if len(found)>=limit:
                break
    return found


def as_timestamp(seconds: float) -> str:
    ms=max(0,round(seconds*1000))
    hour,ms=divmod(ms,3600000)
    minute,ms=divmod(ms,60000)
    second,ms=divmod(ms,1000)
    return f'{hour:02d}:{minute:02d}:{second:02d},{ms:03d}'


def make_srt(segments) -> str:
    blocks=[]
    for item in segments:
        content=str(item['text']).strip()
        if not content:
            continue
        first=float(item['start'])
        second=max(first,float(item['end']))
        index=len(blocks)+1
        blocks.append(f'{index}\n{as_timestamp(first)} --> {as_timestamp(second)}\n{content}')
    return '\n\n'.join(blocks)+ ('\n' if blocks else '')


def _excel_safe(value: str) -> str:
    return "'" + value if value and value.lstrip().startswith(('=','+','-','@')) else value


def export_csv(results: dict, *, checkpoint: bool=False) -> bytes:
    buf=io.StringIO(newline='')
    columns=COLUMNS if checkpoint else EXPORT_COLUMNS
    writer=csv.DictWriter(buf,fieldnames=columns,extrasaction='ignore')
    writer.writeheader()
    for result in results.values():
        writer.writerow({field:_excel_safe(str(result.get(field) or '')) for field in columns})
    return buf.getvalue().encode('utf-8-sig')


def import_checkpoint(data: bytes) -> dict:
    if len(data)>MAX_CHECKPOINT_BYTES:
        raise ValueError('Checkpoint exceeds the 20 MB limit.')
    reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if not reader.fieldnames or 'url' not in reader.fieldnames or 'status' not in reader.fieldnames:
        raise ValueError('This is not a valid checkpoint. It needs url and status columns.')
    results={}
    for row in reader:
        normalized=normalize_facebook_url(row.get('url',''))
        if not normalized or len(results)>=MAX_URLS:
            continue
        entry={}
        for field in COLUMNS:
            val=str(row.get(field) or '')
            if val.startswith("'") and val[1:].lstrip().startswith(('=','+','-','@')):
                val=val[1:]
            entry[field]=val
        entry['url']=normalized
        if entry['status'] not in ('done','failed','skipped'):
            entry['status']='failed'
        results[normalized]=entry
    return results


def export_zip(results: dict, extension: str) -> bytes:
    if extension not in ('txt','srt'):
        raise ValueError('Only txt or srt exports are supported.')
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for i,item in enumerate(results.values(),start=1):
            if item.get('status')!='done':
                continue
            content=item.get('transcript') if extension=='txt' else item.get('srt')
            if content:
                archive.writestr(f'video_{i:04}.{extension}',content)
        archive.writestr('source_links.csv',export_csv(results))
    return buf.getvalue()
