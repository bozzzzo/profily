import time
import profily
import pstatsy

def main():
	t01(); t03()
	for i in range(7):
                def zzz():
                        t7x02()
                zzz()
	t03(); t01()

def t01():
	busy(0.1)

def t7x02():
	busy(0.2)

def t03():
	busy(0.3)

def busy(delay):
	t = time.time
	t0 = t()
	while t()-t0<delay:
		t1 = t0+1
                time.sleep(0.05)

if __name__ == '__main__':
	prof = profily.Profile()
        prof.run('main()')
        pstatsy.Stats(prof).strip_dirs().sort_stats('cumulative').dot_callers()
