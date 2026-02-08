import json, pathlib, urllib.request, urllib.error
base='http://127.0.0.1:18788'
p=pathlib.Path('artifacts/taskboard/tasks.json')
data=json.loads(p.read_text(encoding='utf-8'))
changed=0
for t in data:
    if t.get('kind')=='atomic':
        if not t.get('allowedTests'):
            t['allowedTests']=['python -m pytest -q']; changed+=1
        if t.get('status') in ('failed','in_progress'):
            t['status']='ready'; t['reason']=None; t['lastJobReason']=None; t['lastJobId']=None; changed+=1
p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
ready=[t['id'] for t in data if t.get('kind')=='atomic' and t.get('status')=='ready']
print('tasks saved, changed',changed,'ready',len(ready))
for tid in ready[:30]:
    url=f"{base}/board/tasks/{tid}/dispatch"
    try:
        req=urllib.request.Request(url,data=b'{}',headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=10) as r:
            print('dispatched',tid)
    except urllib.error.HTTPError as e:
        print('dispatch fail',tid,e.read().decode())
    except Exception as e:
        print('dispatch err',tid,e)
