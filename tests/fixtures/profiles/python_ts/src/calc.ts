export function add(a: number, b: number): number {
  return a + b;
}

export class Calc {
  total(xs: number[]): number {
    return xs.reduce((p, c) => add(p, c), 0);
  }
}
