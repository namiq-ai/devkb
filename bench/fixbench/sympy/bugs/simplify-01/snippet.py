from sympy import sqrt, sqrtdenest, N
e = sqrt(10 + 2*sqrt(6) + 2*sqrt(10) + 2*sqrt(15))
r = sqrtdenest(e)
print(r, N(e - r))
