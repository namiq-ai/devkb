"""#418: a TypeScript or TSX symbol has its real start and end line. A brace in a string, a nested template literal, a regular-expression literal, a
comment or JSX text does not move the end; each fixture has a symbol after it, which a wrong end would swallow or misplace. Fixture code is synthetic."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from devkb import read_tools, ts_symbols  # noqa: E402
import cpp_support as S  # noqa: E402


def spans(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    syms, _routes = ts_symbols.extract_file(p, tmp_path)
    return {s["qualified_name"]: (s["line_start"], s["line_end"]) for s in syms}


def test_a_brace_in_a_string_does_not_move_the_end(tmp_path):
    src = 'export function a(): string {\n  const open = "{";\n  const close = \'}\';\n  return open + close;\n}\n\nexport function after() {\n  return 1;\n}\n'
    assert spans(tmp_path, "a.ts", src) == {"a": (1, 5), "after": (7, 9)}


def test_a_nested_template_literal_does_not_move_the_end(tmp_path):
    src = "export function t(user: { name: string }): string {\n  return `hello ${user.name} ${`inner ${ { a: 1 }.a } }`} done`;\n}\n\nexport function after() {\n  return 1;\n}\n"
    assert spans(tmp_path, "t.ts", src) == {"t": (1, 3), "after": (5, 7)}


def test_a_regular_expression_and_comments_do_not_move_the_end(tmp_path):
    src = "export function r(s: string): boolean {\n  // a brace }\n  /* and { */\n  return /[{}]+/.test(s);\n}\n\nexport function after() {\n  return 1;\n}\n"
    assert spans(tmp_path, "r.ts", src) == {"r": (1, 5), "after": (7, 9)}


def test_a_division_is_not_a_regular_expression(tmp_path):
    src = "export function d(a: number, b: number): number {\n  const half = a / 2 + b / 4; // }\n  return half;\n}\n\nexport function after() {\n  return 1;\n}\n"
    assert spans(tmp_path, "d.ts", src) == {"d": (1, 4), "after": (6, 8)}


def test_jsx_text_with_an_apostrophe_and_a_quoted_brace_do_not_move_the_end(tmp_path):
    src = ('export function View({ count }: { count: number }) {\n  return (\n    <div>\n      <p>Don\'t panic: {count} items</p>\n'
           '      <span>{"}"}</span>\n    </div>\n  );\n}\n\nexport function After() {\n  return 1;\n}\n')
    assert spans(tmp_path, "View.tsx", src) == {"View": (1, 8), "After": (10, 12)}


def test_a_comment_inside_a_jsx_tag_and_a_generic_arrow_in_tsx(tmp_path):
    src = ("export function V() {\n  return (\n    <style\n      // note: comes from elsewhere\n      a={{ b: `x ${1} y {` }}\n    />\n  );\n}\n\n"
           "export const g = <T,>(x: T) => {\n  return x;\n};\n\nexport function After() {\n  return 1;\n}\n")
    got = spans(tmp_path, "V.tsx", src)
    assert got["V"] == (1, 8) and got["After"] == (14, 16), got


def test_a_return_type_with_string_literals_and_a_type_literal_in_the_parameters(tmp_path):
    src = ('export function bucket(\n  a: Date,\n  b: Date,\n): "hour" | "day" | "week" {\n  return "hour";\n}\n\n'
           "export function shape(o: { x: number }): { y: number } {\n  return { y: o.x };\n}\n")
    assert spans(tmp_path, "b.ts", src) == {"bucket": (1, 6), "shape": (8, 10)}


def test_an_overload_signature_is_not_a_symbol_and_the_implementation_has_its_span(tmp_path):
    src = "export function f(x: string): string;\nexport function f(x: number): number;\nexport function f(x: any): any {\n  return x;\n}\n"
    assert spans(tmp_path, "o.ts", src) == {"f": (3, 5)}


def test_an_arrow_const_whose_parameters_hold_an_arrow_default(tmp_path):
    src = ("export const block = ({\n  onConfirm = () => {},\n}: Props) => {\n  return 1;\n};\n\n"
           "export const expr = (\n  ids: string[],\n  onConfirm = () => {},\n) =>\n  confirm({\n    go: () => {\n      run(ids);\n    },\n  });\n\n"
           "export function after() {\n  return 1;\n}\n")
    assert spans(tmp_path, "c.ts", src) == {"block": (1, 5), "expr": (7, 15), "after": (17, 19)}


def test_a_declaration_inside_a_comment_is_not_a_symbol(tmp_path):
    src = "/**\n * @example\n * function Fake() {\n *   return 1;\n * }\n */\nexport function real() {\n  return 2;\n}\n"
    assert spans(tmp_path, "j.ts", src) == {"real": (7, 9)}


def test_classes_and_object_literal_methods(tmp_path):
    src = ("export class Counter<T extends { a: number }> extends Base<{ x: 1 }> {\n  inc(): number {\n    return 1;\n  }\n}\n\n"
           "export const api = {\n  one: () => get<number>(\"/one\"),\n  two: (id: string) => {\n    return get<string>(`/two/${id}`);\n  },\n"
           "  three: () =>\n    get<string>(\"/three\"),\n};\n")
    assert spans(tmp_path, "k.ts", src) == {"Counter": (1, 5), "api.one": (8, 8), "api.two": (9, 11), "api.three": (12, 13)}


def test_an_unterminated_string_does_not_swallow_the_file(tmp_path):
    src = "export function a() {\n  const s = 'oops;\n  return s;\n}\n\nexport function after() {\n  return 1;\n}\n"
    assert spans(tmp_path, "u.ts", src)["after"] == (6, 8)


def test_the_route_calls_are_still_found_in_a_body_with_a_nested_template(tmp_path):
    p = tmp_path / "r.ts"
    p.write_text('export const api = {\n  list: () => get<number[]>("/jobs"),\n  one: (id: string) => {\n    return get<string>(`/jobs/${id}`);\n  },\n};\n')
    _syms, routes = ts_symbols.extract_file(p, tmp_path)
    assert ("api.list", "GET", "/jobs") in routes and any(r[0] == "api.one" and r[1] == "GET" for r in routes), routes


def test_outline_and_symbol_say_exact_for_ts_and_tsx(tmp_path, monkeypatch):
    files = {"src/a.ts": "export function plain(a: number): number {\n  return a + 1;\n}\n\nexport function second() {\n  return `${1}`;\n}\n",
             "src/V.tsx": "export function V() {\n  return <p>Don't</p>;\n}\n"}
    a, _packer = S.api(tmp_path, files, monkeypatch)
    out = read_tools.render_outline(a.call("outline", path="src/a.ts"))
    assert "range=exact" in out and "plain  L1-3" in out and "second  L5-7" in out, out
    assert "range=exact" in read_tools.render_outline(a.call("outline", path="src/V.tsx"))
    sym = read_tools.render_symbol(a.call("symbol", query="second", source=True))
    assert "L5-7" in sym and "end unknown" not in sym, sym


def test_a_regular_expression_after_the_paren_of_an_if_is_not_a_division_found_by_the_review_of_419(tmp_path):
    src = ("export function r(a: boolean, s: string) {\n  if (a) /x}/.test(s);\n  while (a) /y{/.test(s);\n  return (a) / 2 + (s.length) / 4;\n}\n\n"
           "export function after() {\n  return 1;\n}\n")
    assert spans(tmp_path, "r.ts", src) == {"r": (1, 5), "after": (7, 9)}


def test_a_generic_jsx_element_is_one_tag_found_by_the_review_of_419(tmp_path):
    src = ("export function V() {\n  return (\n    <Foo<string> x=\"1\">\n      <Bar<number, Map<string, number>> y={{ a: 1 }} />\n    </Foo>\n  );\n}\n\n"
           "export function After() {\n  return 1;\n}\n")
    assert spans(tmp_path, "V.tsx", src) == {"V": (1, 7), "After": (9, 11)}
