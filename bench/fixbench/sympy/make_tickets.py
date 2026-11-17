import json, pathlib
B = pathlib.Path(__file__).parent / 'bugs'
def body(snip, got, exp, extra=''):
    s = f"### What I did\n\n```python\n{snip.strip()}\n```\n\n### What I got\n\n```\n{got.strip()}\n```\n\n### What I expected\n\n{exp.strip()}\n"
    return s + (f"\n{extra.strip()}\n" if extra else '')
T = {
 'printing-01': ("LaTeX output of a symbol named with a double underscore shows a subscript instead of a superscript",
   "x_{2}",
   "`x^{2}`. The docs say a double underscore in a symbol name marks a superscript (like `^`), and this used to work. `pprint` of the same symbol also prints `x₂` now."),
 'simplify-01': ("sqrtdenest returns a value that is not equal to its input",
   "sqrt(6)/3 + sqrt(3) + sqrt(5) 0.597716981445369",
   "`sqrt(2) + sqrt(3) + sqrt(5)`, which squares back to the original radicand, and a difference of 0. Getting a numerically different number out of a simplification is worse than getting the input back unchanged."),
 'sets-01': ("imageset drops an endpoint the function actually reaches",
   "Interval.open(3/2, oo)",
   "`Interval(3/2, oo)`. At x = 2 (which is in the domain, the interval is closed on the right) the function equals 1/2 + 1 = 3/2, so 3/2 belongs to the image and the lower end should be closed, not open."),
 'matrices-01': ("LUsolve gives a wrong solution for an invertible 3x3 system",
   "Matrix([[18, -7, -1]]) Matrix([[0, -1, 1]])",
   "`Matrix([[1, 0, 0]]) Matrix([[0, 0, 0]])`. The matrix is invertible (determinant -1) so the answer is unique, and `A.solve(b)` does return (1, 0, 0). LUsolve's answer doesn't even satisfy the system (non-zero residual)."),
 'functions-01': ("Definite integral of sin with an upper limit containing 2*pi/3 is wrong",
   "sin(x) + 1",
   "`1 - cos(x + 2*pi/3)`, i.e. `sin(x + pi/6) + 1`. Plugging in x = 0 the true value is 3/2, but the returned expression gives 1. Upper limits like x + pi/2 or x + pi seem fine."),
 'solvers-01': ("solve returns an empty list for a simple polynomial system, nonlinsolve returns tuples that do not satisfy it",
   "[]\n{(-3, -2, -1), (3, 2, 1)}",
   "Both should give (x, y, z) = (1, 2, 3) and (-1, -2, -3), which are easy to check by hand. `solve` returning an empty list claims the system is inconsistent, and the tuples from `nonlinsolve` don't satisfy x*y = 2."),
}
for k, (title, got, exp) in T.items():
    snip = (B / k / 'snippet.py').read_text()
    (B / k / 'ticket.json').write_text(json.dumps({'title': title, 'body': body(snip, got, exp)}, indent=2) + '\n')
    print(k, 'ok')
