from fixtures import *
suite=sys.argv[1];assert suite in ('extended','acceptance')
p=ROOT/'backend/tests/permission_round6'/(suite+'.py')
(OUT/'provenance.json').write_text(json.dumps({'source':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'adaptation':'round7 fixture/output; unchanged assertion bodies'},indent=2))
exec(compile(p.read_text(),str(p),'exec'),{'__name__':'__main__'})
