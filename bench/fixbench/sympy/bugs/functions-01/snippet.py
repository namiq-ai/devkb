from sympy import symbols, sin, integrate, pi
x, t = symbols('x t')
print(integrate(sin(t), (t, 0, x + 2*pi/3)))
