"""Read-only readiness checks: structure and meaningful values, not interview quality."""
import argparse
import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from common import ROOT, safe_path
from personalize import read_embedded, render, block, load_records
from registry import load_registry, validate_registry
from projects import known_projects

PLACEHOLDER=re.compile(r'<[^>\n]+>|\bTODO\b|\bTBD\b|шаблон — не заполнять здесь|^\s*(?:пока не знаю|заполнить|неизвестно)\s*$',re.I)

def text(root,path):
    p=safe_path(root,path)
    if not p.is_file() or not p.read_text(encoding='utf-8').strip():raise ValueError('Нет содержимого: '+path)
    return p.read_text(encoding='utf-8')

def meaningful(value):
    if not value.strip() or PLACEHOLDER.search(value):raise ValueError('Пустое значение или плейсхолдер')

def slots(root,path):
    value=text(root,path)
    if PLACEHOLDER.search(value):raise ValueError('Незаполненная карточка: '+path)
    for label in ('За что отвечаю','Вектор','Помогаю с','Каким ты меня видишь'):
        match=re.search(r'\*\*'+re.escape(label)+r':\*\*[ \t]*(.*)',value)
        if not match:raise ValueError('Нет поля '+label+' в '+path)
        meaningful(match[1])
    return value

def links(root,path):
    source=safe_path(root,path)
    for target in re.findall(r'\]\(([^)]+)\)',source.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        p=(source.parent/target.split('#')[0]).resolve()
        if not p.is_relative_to(root.resolve()) or not p.exists():raise ValueError('Нерабочая ссылка: '+path+' -> '+target)

def employee(root,slug):
    validate_registry(root)
    item=next((a for a in load_registry(root)['agents'] if a['id']==slug),None)
    if not item:raise ValueError('Нет сотрудника в реестре: '+slug)
    if item['status']!='active':raise ValueError('Сотрудник не активирован: '+slug)
    text(root,item['core'])
    card=slots(root,item['card'])
    if 'me/goals.md' in card:
        goals=load_records(root,'goals')
        if not goals:raise ValueError('Карточка ссылается на отсутствующие цели')
    for path in item['memory']:text(root,path)
    links(root,item['card'])

def stage_statuses(root):
    path=root/'team/ops/build-log.md'
    if not path.exists():return {}
    data={}
    for n,status in re.findall(r'^\s*#*\s*Этап (\d+):[^\n]*\((открыт|готов|пропущен)\)',path.read_text(encoding='utf-8'),re.M):data[int(n)]=status
    return data

def results(root):
    return [p for p in (root/'results').rglob('*') if p.is_file() and p.name not in ('AGENTS.md','CLAUDE.md','INDEX.md') and not any(part.startswith(('_','.')) for part in p.relative_to(root/'results').parts) and p.stat().st_size]

def check_stage(root,n):
    states=stage_statuses(root)
    if n not in states:raise ValueError('Нет строки этапа в журнале')
    if states[n]=='пропущен':
        if n!=3:raise ValueError('Пропуск поддержан только для необязательного коуча')
        return 'SKIPPED:owner-declined-coach'
    validate_registry(root)
    if n==1:
        meaningful(text(root,'knowledge/summary.md'))
        if 'summary.md' not in text(root,'knowledge/INDEX.md'):raise ValueError('Выжимка отсутствует в INDEX')
    elif n==2:
        data=read_embedded(root/'me/profile.md','office-profile')
        if not data:raise ValueError('Нет подтверждённого профиля')
        expected=render(data)
        if block(text(root,'AGENTS.md')).strip()!=expected.strip():raise ValueError('Персональный блок разошёлся с профилем')
        if not any(f['status']=='confirmed' for f in data['facts']):raise ValueError('Нет ни одного подтверждённого основания')
        if not results(root):raise ValueError('Первый результат не создан')
    elif n==3:employee(root,'atlas')
    elif n==4:
        data=load_records(root,'work')
        if not data or not any(r['status']=='confirmed' for r in data):raise ValueError('В карте нет подтверждённых фактов')
        for record in data:meaningful(str(record.get('value','')))
    elif n==5:
        if len(results(root))<2:raise ValueError('Нет подарка и первой рабочей вещи')
    elif n==6:
        employee(root,'director')
        day=text(root,'team/ops/today.md')
        day_match=re.search(r'^Дата: (\d{4}-\d{2}-\d{2})$',day,re.M)
        zone_match=re.search(r'^Timezone: (\S+)$',day,re.M)
        if not day_match or not zone_match:raise ValueError('У шапки дня нет даты/timezone')
        try:
            date.fromisoformat(day_match[1])
            ZoneInfo(zone_match[1])
        except (ValueError,ZoneInfoNotFoundError) as exc:
            raise ValueError('Неверная календарная дата или IANA timezone') from exc
    elif n==7:
        projects=known_projects(root)
        if not projects:raise ValueError('Нет первого проекта')
        for p in projects:
            prefix='projects/'+p['slug']
            value=text(root,prefix+'/AGENTS.md')
            for label in ('Предмет','источники','данные','приёмка','контекст'):
                if label.casefold() not in value.casefold():raise ValueError('Неполные правила проекта: '+prefix)
            if text(root,prefix+'/CLAUDE.md').strip()!='@AGENTS.md':raise ValueError('Неверная обёртка проекта')
            if p['slug']+'/map.md' not in text(root,'projects/map.md') or p['slug']+'/' not in text(root,'projects/INDEX.md'):raise ValueError('Проект не в картах')
        for path in (root/'clients').glob('*/README.md'):
            meaningful(path.read_text(encoding='utf-8'))
            if path.parent.name+'/' not in text(root,'clients/INDEX.md'):raise ValueError('Клиент не в INDEX')
    elif n==8:
        employee(root,'rita')
        value=text(root,'MAP.md')
        if '](' not in value or 'Никита наполнит её на финале' in value:raise ValueError('Карта офиса не заполнена')
        links(root,'MAP.md')
    else:raise ValueError('Номер этапа 1..8')
    return 'PASS:structure-only'

def audit(root):
    states=stage_statuses(root)
    if not states:return ['SKIPPED:onboarding-not-started']
    failures=[]
    for n,status in states.items():
        if status in ('готов','пропущен'):
            try:check_stage(root,n)
            except (ValueError,OSError,KeyError) as exc:failures.append(f'stage{n}: {exc}')
    log=text(root,'team/ops/build-log.md')
    if 'СТРОЙКА ЗАВЕРШЕНА' in log and any(states.get(n) not in ('готов','пропущен') for n in range(1,9)):failures.append('Финал объявлен до завершения этапов')
    return failures

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=[str(n) for n in range(1,9)]+['audit'])
    args=parser.parse_args()
    try:
        if args.stage=='audit':
            errors=audit(ROOT)
            if errors and not errors[0].startswith('SKIPPED:'):raise ValueError('; '.join(errors))
            print('audit=SKIPPED '+errors[0] if errors else 'audit=ok')
        else:
            result=check_stage(ROOT,int(args.stage))
            print('stage'+args.stage+('=SKIPPED ' if result.startswith('SKIPPED:') else '=ok ')+result)
    except (ValueError,OSError,KeyError) as exc:
        parser.exit(1,('audit' if args.stage=='audit' else 'stage'+args.stage)+'=fail: '+str(exc)+'\n')
