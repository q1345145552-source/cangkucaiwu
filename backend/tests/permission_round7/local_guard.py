"""Test-process network boundary. No business authorization is replaced."""
import sys

def guard(event,args):
    if event in ('socket.connect','socket.connect_ex'):
        address=args[1]
        if isinstance(address,tuple) and not(address[0] in ('127.0.0.1','::1','localhost') and address[1] in (65519,65520,65521,65522)):
            raise RuntimeError('Round7 tests prohibit non-isolated socket connections: '+str(address))
    if event=='open' and args and isinstance(args[0],str):
        name=args[0].replace('\\','/')
        if '/.deploy/' in name or name.endswith('/.deploy') or '/.ssh/' in name:
            raise RuntimeError('Round7 tests prohibit deployment/production credential access')
sys.addaudithook(guard)
