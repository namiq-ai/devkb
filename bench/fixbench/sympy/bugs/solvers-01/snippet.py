from sympy import symbols, solve, nonlinsolve
x, y, z = symbols('x y z')
print(solve([x*y - 2, y*z - 6, x*z - 3], [x, y, z]))
print(nonlinsolve([x*y - 2, y*z - 6, x*z - 3], [x, y, z]))
