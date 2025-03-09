# EPICS softIocPVA for P2Plant devices

# Example
Start P2Plant of simulated 8-channel ADC as described in [P2Plant](https://github.com/ASukhanov/P2Plant).

Run softIocPVA:<br>
```
python -m p2plant_ioc -l -k
```
The P2Plant should start streaming data:
```
ADC:rps=10 reqs:81, trig:69021 client:1, DBG:0
...
```
Open another terminal to control P2Plant.<br>
Change debugging level of the P2Plant:
```
python -m p4p.client.cli put p2p:debug=1
# disable debugging:
python -m p4p.client.cli put p2p:debug=0
```
Change streaming rate of the P2Plant to 1000 Hz (sleep time = 1 ms):<br>
```
python -m p4p.client.cli put p2p:sleep=1
```
The P2Plot should indicate the rps (rounds per seconds) change to ~920.<br>
Monitor ADC channel 0:<br>
```
python -m p4p.client.cli monitor p2p:adc0
p2p:adc0 Sun Mar  9 11:29:44 2025 ntnumericarray([457, 458, 459, ..., 454, 455, 456], dtype=uint16)
```
Plot ADC0 samples using pvplot:<br>
```
python -m pvplot V:p2p:adc0
```

