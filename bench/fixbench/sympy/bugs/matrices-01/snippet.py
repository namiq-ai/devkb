from sympy import Matrix
A = Matrix([[1, 2, 3], [2, 4, 7], [3, 7, 1]]); b = Matrix([1, 2, 3])
x = A.LUsolve(b)
print(x.T, (A*x - b).T)
