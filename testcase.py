import time
import profily

def maingen():
	print "#maingen 1"
	t04()
	yield "#maingen 2"
	t05()
	yield "#maingen 3"
	t06()
	print "#maingen 4"

def main():
	t01();
	t03()
	t04();
	t05()
	t03();
	t01()
	t06();

def t04():
	print "# t04"
	def workgen():
		for i in range(4):
			n = "zzz%s"%i
			x = {}
			exec "def "+n+"(): slow("+str(i)+")" in globals(), x
			zzz = x[n]
			yield zzz
	for work in workgen():
                work()
	return "# t04"

def t05():
	print "# t05"
	def genwork():
		t03()
		for i in range(5):
			def zzz():
				t7x02()
			yield zzz
	def wrapper(g):
		t03()
		try:
			while True:
				l = g.next()
				l()
				def z(): t01()
				yield z
		except:
			pass
	for work in wrapper(genwork()):
                work()
	return "# t05"

def t06():
	print "# t06"
	s = 3.0
	while s > 0:
		s = s/2.
		busy(s)
	return "# t06"
def t01():
	print "# t01 1"
	busy(0.1)
	return "# t01"

def t7x02():
	busy(0.2)

def slow(i):
	busy(0.01*i)

def t03():
	print "# t03"
	busy(0.3)
	return "# t03"

def busy(delay):
	t = time.time
	t0 = t1 = t()
	a = []
	while t1-t0<=delay:
		t1 = t()
		a.insert(0,t1)
		del a[20:]

if __name__ == '__main__':
	prof = profily.Profile()
	def creategen():
		return prof.rungen(maingen)
	def consumegen(gen):
		print "#", ", ".join(gen)
	consumegen(creategen())
        profily.Stats(prof,threshold=0.01).strip_dirs().sort_stats('cumulative').dot_callers()
