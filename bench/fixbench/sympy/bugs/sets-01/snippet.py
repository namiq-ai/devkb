from sympy import Symbol, Interval, imageset
x = Symbol('x', real=True)
print(imageset(x, 1/x + 1/(x - 1)**2, Interval.Lopen(0, 2)))
