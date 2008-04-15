import time
import profily

def main():
	t01()
	for i in range(7): t7x02()
	t03()

def t01():
	busy(0.1)

def t7x02():
	busy(0.2)

def t03():
	busy(0.3)

def busy(delay):
	t = time.time
	t0 = t()
	while t()-t0<delay*3:
		t1 = t0+1

if __name__ == '__main__':
	profily.run('main()')
