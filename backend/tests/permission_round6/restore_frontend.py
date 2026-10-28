"""Offline npm lock-integrity verification and independent package restoration."""
import pathlib,json,base64,hashlib,tarfile
root=pathlib.Path(__file__).resolve().parents[3];dest=pathlib.Path('/private/tmp/permissions-round6-env/frontend')
lock=json.loads((root/'frontend/package-lock.json').read_text());restored=[];missing=[]
for path,entry in lock['packages'].items():
 if not path or 'integrity' not in entry:continue
 h=base64.b64decode(entry['integrity'].split('-')[1]).hex();archive=pathlib.Path.home()/'.npm/_cacache/content-v2/sha512'/h[:2]/h[2:4]/h[4:]
 if not archive.exists():
  if entry.get('optional') and ('darwin' not in entry.get('os',['darwin']) or 'arm64' not in entry.get('cpu',['arm64'])):missing.append(path);continue
  raise RuntimeError('missing local package: '+path)
 assert hashlib.sha512(archive.read_bytes()).hexdigest()==h
 with tarfile.open(archive) as t:
  for m in t.getmembers():
   parts=pathlib.PurePosixPath(m.name).parts
   if not parts or pathlib.PurePosixPath(m.name).is_absolute() or '..' in parts:raise ValueError(m.name)
   m.name=str(pathlib.PurePosixPath(*parts[1:]));t.extract(m,dest/path,filter='data')
 restored.append(path)
print(json.dumps({'restored':len(restored),'foreign_platform_optional_unavailable':missing},indent=2))
