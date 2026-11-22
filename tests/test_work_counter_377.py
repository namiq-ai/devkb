"""#377: the counting helper tells linear work from quadratic work, and is the same on every run."""
import work_counter


def _linear(n):
    return sum(1 for _ in range(n))


def _quadratic(n):
    t = 0
    for i in range(n):
        for j in range(n):
            t += 1
    return t


def test_four_times_the_input_is_about_four_times_the_lines_when_linear_and_sixteen_when_quadratic():
    f = _linear.__code__.co_filename                       # both functions live in this file
    small_l, _ = work_counter.lines_executed(lambda: _linear(200), f)
    big_l, _ = work_counter.lines_executed(lambda: _linear(800), f)
    small_q, _ = work_counter.lines_executed(lambda: _quadratic(30), f)
    big_q, _ = work_counter.lines_executed(lambda: _quadratic(120), f)
    assert 3.5 < big_l / small_l < 4.5, (small_l, big_l)
    assert big_q / small_q > 12, (small_q, big_q)


def test_the_count_is_the_same_on_every_run():
    f = _quadratic.__code__.co_filename
    counts = {work_counter.lines_executed(lambda: _quadratic(40), f)[0] for _ in range(3)}
    assert len(counts) == 1, counts

