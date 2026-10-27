"""Record reached assertion source lines, without changing requests, auth or assertions."""
import ast,json,os,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
INDEX={};RESULT={}
for p in [*ROOT.glob('test_*.py'),ROOT/'round3_flow_support.py']:
    nodes=[n for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.Assert)]
    source=p.read_text();byline={}
    for n in nodes:byline.setdefault(n.lineno,[]).append(ast.get_source_segment(source,n))
    INDEX[str(p)]=byline
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    reached={};failed={};previous=sys.gettrace()
    def trace(frame,event,arg):
        filename=frame.f_code.co_filename
        if filename not in INDEX:return None
        if event=='line' and frame.f_lineno in INDEX[filename]:
            key=str(Path(filename).relative_to(ROOT))+':'+str(frame.f_lineno)
            reached[key]=INDEX[filename][frame.f_lineno]
        if event=='exception' and isinstance(arg[1],AssertionError) and frame.f_lineno in INDEX[filename]:
            key=str(Path(filename).relative_to(ROOT))+':'+str(frame.f_lineno)
            failed[key]=str(arg[1])
        return trace
    sys.settrace(trace)
    try:yield
    finally:
        sys.settrace(previous)
        RESULT[item.nodeid]={'reached_assertions':reached,'failed_assertion_lines':failed}
def pytest_runtest_logreport(report):
    if report.when=='call':RESULT.setdefault(report.nodeid,{})['outcome']=report.outcome
def pytest_sessionfinish(session,exitstatus):
    Path(os.environ['ASSERTION_TRACE_OUT']).write_text(json.dumps({'exit_code':int(exitstatus),'tests':RESULT},ensure_ascii=False,indent=2))
