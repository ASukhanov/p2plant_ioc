'''EPICS p4p-based softIocPVA for P2Plant devices
'''
__version__= 'v0.0.1 2025-02-14'# 

import argparse, time, threading
import numpy as np
import pprint
from p4p.nt import NTScalar, NTEnum
from p4p.nt.enum import ntenum
from p4p.server import Server
from p4p.server.thread import SharedPV

#`````````````````Constants```````````````````````````````````````````````````
SleepTime = 1.
EventExit = threading.Event()
MaxPoints = 100

#``````````````````Module properties``````````````````````````````````````````
class G():
    IocPrefix = None
    PVs = {}
    cycle = 0

    def set_run(vntenum):
        idx = vntenum.raw.value.index
        #print(f">set_run {idx}")
        if idx == 0:# Run
            threading.Thread(target=G.threadProc).start()

#``````````````````Argument parsing```````````````````````````````````````````
parser = argparse.ArgumentParser(description = __doc__,
  formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  epilog=(f'{__version__}'))
parser.add_argument('-l', '--listPVs', action='store_true', help=\
'List all generated PVs')
parser.add_argument('-p', '--prefix', default='p2p:', help=\
'Prefix of all PVs')
parser.add_argument('-v', '--verbose', action='count', default=0, help=\
'Show more log messages (-vv: show even more)')
pargs = parser.parse_args()
P = pargs.prefix

#```````````````````Helper methods````````````````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): print(f'inf_@{printTime()}: {msg}')
def printw(msg): print(f'WAR_@{printTime()}: {msg}')
def printe(msg): print(f'ERR_{printTime()}: {msg}')
def _printv(msg, level):
    if pargs.verbose >= level: print(f'DBG{level}: {msg}')
def printv(msg): _printv(msg, 1)
def printvv(msg): _printv(msg, 2)

from p2plantaccess import Access as pa
pa.init(); pa.start()

info = pa.request(["info", ["*"]])['*']
print(f'Attached P2Plant hosts the following PVs: {list(info.keys())}')

#``````````````````Definition of PVs``````````````````````````````````````````
#typeCode = {
#'F64':'d',  'F32':'f',  'I64':'l',  'I8':'b',   'U8':'B',   'I16':'h',
#'U16':'H',  'I32':'i',  'U32':'I',  'I64':'l',
#}
typeCode = {#'F64':'d',  'F32':'f',  
'int64':'l',  'int8':'b',   'uint8':'B',   'char':'s', 'int16':'h',
'uint16':'H',  'int32':'i',  'uint32':'I',  'int64':'l',
}

def makeNTScalar(t:str):
    tt = t.split('*')# vector type ends with *
    prefix = '' if len(tt)==1 else 'a'
    return NTScalar(prefix+typeCode[tt[0]], display=True)

PVDefs = [# Standard PVs
['Run', 'Start/Stop the device',
    NTEnum(),#DNW:display=True),
    {'choices': ['Run','Stop'], 'index': 0},'WE',
    {'setter': G.set_run}],
['cycle',   'Cycle number', makeNTScalar('uint32'), '0', 'R',{}],
]
for pvName,inf in info.items():
    printv(f'PV {pvName}: {inf}')
    r = pa.request(['get',[pvName]])[pvName]
    printv(f'r: {r}')
    shape = r.get('shape',[1])
    if len(shape) > 1:  continue# skip multi-dimensional arrays for now
    #if inf['type'] in ('char*'): continue#  skip for now
    PVDefs.append([pvName, inf['desc'], makeNTScalar(inf['type']),
        r['v'], inf['fbits'], {}])

ts = time.time()

#``````````````````create_PVs()```````````````````````````````````````````````
for defs in PVDefs:
    pname,desc,nt,ivalue,features,extra = defs
    writable = 'W' in features
    #print(f'creating pv {pname}, writable: {writable}, initial: {ivalue}, extra: {extra}')
    pv = SharedPV(nt=nt)
    G.PVs[P+pname] = pv
    pv.open(ivalue)
    #if isinstance(ivalue,dict):# NTEnum
    if isinstance(nt,NTEnum):# NTEnum
        pv.post(ivalue, timestamp=ts)
    else:
        v = pv._wrap(ivalue, timestamp=ts)
        #if display:
        displayFields = {'display.description':desc}
        for field in ['limitLow','limitHigh','format','units']:
            try:    displayFields[f'display.{field}'] = extra[field]
            except: pass
        for key,value in displayFields.items():
            #print(f'Trying to add {key} to {pname}')
            try:    v[key] = value
            except Exception as e:
                printe(f'in adding {key} to {pname}: {e}')
                pass
        pv.post(v)
    pv.name = pname
    pv.setter = extra.get('setter')

    if writable:
        @pv.put
        def handle(pv, op):
            ct = time.time()
            v = op.value()
            vr = v.raw.value
            if isinstance(v, ntenum):
                vr = v
            if pv.setter:
                pv.setter(vr)
            if pargs.verbose >= 1:
                printi(f'putting {pv.name} = {vr}')
            pv.post(vr, timestamp=ct) # update subscribers
            op.done()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if pargs.listPVs:
    print('List of PVs:')
    pprint.pp(list(G.PVs.keys()))

def myThread_proc():
    threads = 0
    printi('Run started')
    while not EventExit.is_set():
        G.cycle += 1
        printv(f'cycle {G.cycle}')
        if str(G.PVs[P+'Run'].current())!='Run':
            break
        EventExit.wait(SleepTime)
    printi('Run stopped')
    return

G.threadProc = myThread_proc
thread = threading.Thread(target=myThread_proc).start()

Server.forever(providers=[G.PVs]) # runs until KeyboardInterrupt
