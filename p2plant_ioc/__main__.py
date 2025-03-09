'''EPICS p4p-based softIocPVA for P2Plant devices
'''
__version__= 'v1.0.1 2025-03-07'# Setting is working
#TODO: handle multi-dimensional data

import time, threading
import numpy as np
import pprint
from p4p.nt import NTScalar, NTEnum
from p4p.nt.enum import ntenum
from p4p.server import Server
from p4p.server.thread import SharedPV

from p2plantaccess import Access as PA

#``````````````````Module properties``````````````````````````````````````````
EventExit = threading.Event()
pargs = None
threadProc = None

#```````````````````Helper methods````````````````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): print(f'inf_@{printTime()}: {msg}')
def printw(msg): print(f'WAR_@{printTime()}: {msg}')
def printe(msg): print(f'ERR_{printTime()}: {msg}')
def _printv(msg, level):
    if pargs.verbose >= level: print(f'DBG{level}: {msg}')
def printv(msg): _printv(msg, 1)
def printvv(msg): _printv(msg, 2)

typeCode = {#'F64':'d',  'F32':'f',  
'int64':'l',  'int8':'b',   'uint8':'B', 'char*':'s', 'int16':'h',
'uint16':'H',  'int32':'i',  'uint32':'I',  'int64':'l',
}

def set_run(vntenum):
    idx = vntenum.raw.value.index
    #print(f">set_run {idx}")
    #if idx == 0:# Run
    #    threading.Thread(target=threadProc).start()

def makeNTScalar(key:str):
    prefix = ''
    if key != 'char*':
        if key[-1] == '*':
            key = key[:-1]
            prefix = 'a'
    return NTScalar(prefix+typeCode[key], display=True)

PVs = {}# Map of process variables

PVDefs = [# Standard PVs
['Run', 'Start/Stop the device',
    NTEnum(),#DNW:display=True),
    {'choices': ['Run','Stop'], 'index': 0},'WE',
    {'setter': set_run}],
['cycle',   'Cycle number', makeNTScalar('uint32'), '0', 'R',{}],
]

def append_PVDefs(info:dict):
    for pvName,inf in info.items():
        printv(f'PV {pvName}: {inf}')
        r = PA.request(['get',[pvName]])[pvName]
        printvv(f'r: {r}')
        shape = r.get('shape',[1])
        if len(shape) > 1: # skip multi-dimensional arrays for now
            printw(f'multi-dimensional arrays not supported: {pvName}')
            continue
        PVDefs.append([pvName, inf['desc'], makeNTScalar(inf['type']),
            r['v'], inf['fbits'], {}])

#``````````````````create_PVs()```````````````````````````````````````````````
def create_PVs():
    tstamp = time.time()
    for defs in PVDefs:
        pname,desc,nt,ivalue,features,extra = defs
        writable = 'W' in features
        #print(f'creating pv {pname}, writable: {writable}, initial: {ivalue}, extra: {extra}')
        pv = SharedPV(nt=nt)
        PVs[pargs.prefix+pname] = pv
        #print(f'ivalue: {ivalue}')
        pv.open(ivalue)
        #if isinstance(ivalue,dict):# NTEnum
        if isinstance(nt,NTEnum):# NTEnum
            pv.post(ivalue, timestamp=tstamp)
        else:
            v = pv._wrap(ivalue, timestamp=tstamp)
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
                cmd = f'["set",[["{pv.name}",{vr}]]]'
                r = PA.request(cmd)
                printv(f'Requested: {cmd}')
                pv.post(vr, timestamp=ct) # update subscribers
                op.done()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
lasttime = time.time()
fps = 0
def receive_subscription(blocking=False):
    global lasttime,fps
    ct = time.time()
    printInterval = 10#s
    if ct - lasttime >= printInterval:
        lasttime = ct
        txt = ''
        if pargs.keep_alive:
            # request something to inform server that I am alive
            r = PA.request('["get", ["perf"]]');
            try:
                txt += f'Perf: {str(r["perf"]["v"])}.'
            except Exception as e:
                txt = 'WARNING: Got unexpected value for perf: {}, {e}'
        txt += f' Frame rate: {round(fps/printInterval,3)} Hz.'
        if not pargs.quiet: 
            printi(txt)
        fps = 0

    r = PA.recv('subscription', blocking)
    if len(r) == 0:
        #printv(f'no data, fps: {fps}')
        time.sleep(.000001)#ISSUE: if return without any system call, then the cycle rate is slow, same as with -g and CPU=100%. Is this QT issue? With this microsleep the CPU=26% and trig rate=frame. 
        return {}

    # data received
    fps += 1
    printvv(f'data received, fps: {fps}')
    decoded = PA.decode()
    if pargs.verbose >= 2:
        printvv(f'decoded: {decoded}')
    return decoded

def mainLoop():
    """ Receive subscriptions from P2Plant and post PVs"""
    threads = 0
    cycle = 0
    printi('========== mainLoop have started ==========')
    while not EventExit.is_set():
        cycle += 1
        printvv(f'cycle {cycle}')
        if str(PVs[pargs.prefix+'Run'].current())!='Run':
            break
        ts = time.time()
        PVs[pargs.prefix+'cycle'].post(cycle, timestamp=ts)

        r = receive_subscription()
        for pvname,rd in r.items():
            printvv(f'received {pvname}')
            #TODO: handle shape
            shape = rd.get('shape',[1])
            if len(shape) > 1:  continue# skip multi-dimensional arrays for now
            PVs[pargs.prefix+pvname].post(rd['v'], timestamp=rd['t'])

        EventExit.wait(pargs.sleep)
    printi('Run stopped')
    return

#``````````````````Main function``````````````````````````````````````````````
def main():
    import argparse
    global pargs, threadProc
    # Argument parsing
    parser = argparse.ArgumentParser(description = __doc__,
      formatter_class=argparse.ArgumentDefaultsHelpFormatter,
      epilog=(f'{__version__}'))
    parser.add_argument('-k', '--keep_alive', action='store_true', help=\
      'Periodically send request to server to keep it alive')
    parser.add_argument('-l', '--listPVs', action='store_true', help=\
    'List all generated PVs')
    parser.add_argument('-p', '--prefix', default='p2p:', help=\
    'Prefix of all PVs')
    parser.add_argument('-q', '--quiet', action='store_true', help=\
      'Do not print frame statistics')
    parser.add_argument('-s','--sleep',type=float,default=.1, help=\
    'Sleep time between checking for subscription delivery')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=\
    'Show more log messages (-vv: show even more)')
    pargs = parser.parse_args()

    # Connect to plant and start it.
    PA.init();
    PA.start()
    r = PA.request('["get", ["version"]]');
    print(f'P2Plant {r["version"]["v"]}')
    info = PA.request(["info", ["*"]])['*']
    print(f'Attached P2Plant hosts the following PVs: {list(info.keys())}')
    #print(f'info: {info}')

    # Construct PVs
    append_PVDefs(info)
    create_PVs()
    if pargs.listPVs:
        print('List of PVs:')
        pprint.pp(list(PVs.keys()))

    #```````````````The P2Plant seems to be alive`````````````````````````````````
    # Start the PVA server as a thread
    #threadProc = mainLoop
    thread = threading.Thread(target=mainLoop).start()

    #print('sleep before run')
    #time.sleep(5)
    PA.request('["set", [["run", "start"]]]')
    print(f'Asked server to start')

    Server.forever(providers=[PVs]) # runs until KeyboardInterrupt

    # Start the PVA server
    #Server(providers=[PVs])
    # start data receiving and posting
    #mainLoop()

if __name__ == "__main__":
    main()
