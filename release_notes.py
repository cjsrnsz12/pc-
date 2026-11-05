"""Extract only the selected release and group user-visible changes."""
import re

KINDS=[('new','새 기능','#65dfad'),('improvement','개선','#79b8ff'),('fix','버그 수정','#ffbd78')]
VERSION_HEADING=re.compile(r'^#{1,4}\s*\[?v?(\d+\.\d+\.\d+)\]?(?:[ \t]|$|[-—:]).*$',re.M|re.I)


def latest_notes(body,version):
    body=str(body or '').replace('\r\n','\n')
    headings=list(VERSION_HEADING.finditer(body))
    tag=str(version).lstrip('vV')
    if headings:
        for i,h in enumerate(headings):
            if h.group(1)==tag:
                end=headings[i+1].start() if i+1<len(headings) else len(body)
                return body[h.end():end].strip()[:24000]
        return body[:headings[0].start()].strip()[:24000]
    return body.strip()[:24000]


def category(text):
    compact=re.sub(r'\s+','',text).casefold()
    if any(w in compact for w in ['버그','수정','오류','실패','fix','bug']):return 'fix'
    if any(w in compact for w in ['새기능','신규','추가','new','feature']):return 'new'
    return 'improvement'


def grouped_changes(notes):
    groups={key:[] for key,_,_ in KINDS};section=None;previous=None
    for line in notes.splitlines():
        line=line.strip()
        if not line:continue
        if line.startswith('#'):
            title=line.lstrip('#').strip()
            if VERSION_HEADING.match(line):break
            section=category(title);previous=None;continue
        content=re.sub(r'^(?:[-*+]\s+|\d+[.)]\s+)','',line)
        explicit=re.match(r'^\[(새 기능|신규|개선|버그 수정|수정)\]\s*(.*)',content)
        kind=category(explicit.group(1)) if explicit else (section or category(content))
        content=explicit.group(2) if explicit else content
        content=content.replace('**','').replace('`','').strip()
        if content and content not in groups[kind]:groups[kind].append(content)
        previous=kind
    if not any(groups.values()):groups['improvement']=['이 버전의 자세한 변경 안내가 아직 등록되지 않았습니다.']
    return groups
