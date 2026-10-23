"""Bug categories, seed snippets and the offline bug bank.

Every seed snippet ships with hand-checked tests. The offline bug bank is a
safety net: if no API key is set, or the model returns a mutant that fails
verification three times, GlitchGym serves a pre-verified bug instead so the
app never dead-ends in front of a student (or a judge).
"""

from __future__ import annotations

from dataclasses import dataclass, field

CATEGORIES: dict[str, dict[str, str]] = {
    "off_by_one": {
        "name": "Off-by-one",
        "blurb": "Loop ranges, slice ends and indexes that are one too far or one too short.",
    },
    "boundary_compare": {
        "name": "Boundary comparison",
        "blurb": "< vs <=, > vs >=: the edge case that sits exactly on the line.",
    },
    "mutable_default": {
        "name": "Mutable default argument",
        "blurb": "A default list or dict is created once and shared between calls.",
    },
    "aliasing": {
        "name": "Aliasing",
        "blurb": "Two names (or rows) point at the same object, so changing one changes both.",
    },
    "missing_return": {
        "name": "Missing / misplaced return",
        "blurb": "The function prints instead of returning, or returns too early.",
    },
    "type_mixup": {
        "name": "Type mix-up",
        "blurb": "str vs int, / vs //: the value has a different type than you think.",
    },
    "scope": {
        "name": "Scope & reset",
        "blurb": "A variable is (re)initialised in the wrong place, e.g. inside the loop.",
    },
    "mutate_while_iterating": {
        "name": "Mutating while iterating",
        "blurb": "Removing items from a list while looping over that same list skips elements.",
    },
    "logic": {
        "name": "Boolean & branch logic",
        "blurb": "and/or precedence, or if/elif branches checked in the wrong order.",
    },
    "dict_key": {
        "name": "Dictionary updates",
        "blurb": "Missing keys, overwritten counts, or forgetting an else branch.",
    },
}

CATEGORY_IDS = list(CATEGORIES)


@dataclass
class Snippet:
    id: str
    title: str
    description: str
    code: str
    tests: list[str]


@dataclass
class OfflineBug:
    snippet_id: str
    category: str
    mutated_code: str
    hints: list[str]
    explanation: str
    bug_line_hint: str = ""
    extra: dict = field(default_factory=dict)


SNIPPETS: list[Snippet] = [
    Snippet(
        "sum_evens", "Sum the even numbers",
        "Return the sum of every even number in a list.",
        '''def sum_evens(nums):
    total = 0
    for n in nums:
        if n % 2 == 0:
            total += n
    return total
''',
        [
            "assert sum_evens([1, 2, 3, 4]) == 6",
            "assert sum_evens([]) == 0",
            "assert sum_evens([7, 9]) == 0",
            "assert sum_evens([-2, 5, 10]) == 8",
        ],
    ),
    Snippet(
        "pairwise_diffs", "Differences between neighbours",
        "Return the list of differences between each pair of neighbouring numbers.",
        '''def pairwise_diffs(nums):
    diffs = []
    for i in range(len(nums) - 1):
        diffs.append(nums[i + 1] - nums[i])
    return diffs
''',
        [
            "assert pairwise_diffs([1, 4, 9, 16]) == [3, 5, 7]",
            "assert pairwise_diffs([10, 7]) == [-3]",
            "assert pairwise_diffs([5]) == []",
            "assert pairwise_diffs([]) == []",
        ],
    ),
    Snippet(
        "count_words", "Word frequency counter",
        "Count how many times each word appears, ignoring case.",
        '''def count_words(text):
    counts = {}
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1
    return counts
''',
        [
            'assert count_words("the cat the hat") == {"the": 2, "cat": 1, "hat": 1}',
            'assert count_words("Hi hi HI") == {"hi": 3}',
            'assert count_words("") == {}',
            'assert count_words("solo") == {"solo": 1}',
        ],
    ),
    Snippet(
        "add_item", "Shopping basket",
        "Add an item to a basket; start a fresh basket if none is given.",
        '''def add_item(item, basket=None):
    if basket is None:
        basket = []
    basket.append(item)
    return basket
''',
        [
            'assert add_item("apple") == ["apple"]',
            'assert add_item("pear") == ["pear"]',
            'assert add_item("fig", ["kiwi"]) == ["kiwi", "fig"]',
        ],
    ),
    Snippet(
        "remove_negatives", "Filter out negatives",
        "Return a new list without negative numbers. Do not modify the input.",
        '''def remove_negatives(nums):
    result = []
    for n in nums:
        if n >= 0:
            result.append(n)
    return result
''',
        [
            "assert remove_negatives([3, -1, -2, 4]) == [3, 4]",
            "assert remove_negatives([0, -3, 2]) == [0, 2]",
            "assert remove_negatives([-5, -6]) == []",
            "data = [1, -1]; remove_negatives(data); assert data == [1, -1]",
        ],
    ),
    Snippet(
        "average", "Class average",
        "Average a list of scores to one decimal place; an empty list gives 0.0.",
        '''def average(scores):
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 1)
''',
        [
            "assert average([70, 80, 95]) == 81.7",
            "assert average([1, 2]) == 1.5",
            "assert average([]) == 0.0",
        ],
    ),
    Snippet(
        "is_valid_password", "Password rules",
        "A valid password has at least 8 characters, a digit and an uppercase letter.",
        '''def is_valid_password(pw):
    has_digit = any(c.isdigit() for c in pw)
    has_upper = any(c.isupper() for c in pw)
    return len(pw) >= 8 and has_digit and has_upper
''',
        [
            'assert is_valid_password("Secret123") is True',
            'assert is_valid_password("Exactly8") is True',
            'assert is_valid_password("secret123") is False',
            'assert is_valid_password("Short1A") is False',
            'assert is_valid_password("NoDigitsHere") is False',
        ],
    ),
    Snippet(
        "binary_search", "Binary search",
        "Return the index of target in a sorted list, or -1 if it isn't there.",
        '''def binary_search(items, target):
    lo, hi = 0, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if items[mid] == target:
            return mid
        if items[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
''',
        [
            "assert binary_search([1, 3, 5, 7, 9], 7) == 3",
            "assert binary_search([1, 3, 5, 7, 9], 1) == 0",
            "assert binary_search([1, 3, 5, 7, 9], 9) == 4",
            "assert binary_search([1, 3, 5], 4) == -1",
            "assert binary_search([], 2) == -1",
        ],
    ),
    Snippet(
        "letter_grade", "Letter grades",
        "80+ is A, 65+ is B, 50+ is C, anything lower is F.",
        '''def letter_grade(score):
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    return "F"
''',
        [
            'assert letter_grade(80) == "A"',
            'assert letter_grade(92) == "A"',
            'assert letter_grade(79) == "B"',
            'assert letter_grade(50) == "C"',
            'assert letter_grade(12) == "F"',
        ],
    ),
    Snippet(
        "to_fahrenheit", "Temperature converter",
        "Convert Celsius to Fahrenheit.",
        '''def to_fahrenheit(celsius):
    return celsius * 9 / 5 + 32
''',
        [
            "assert to_fahrenheit(0) == 32",
            "assert to_fahrenheit(100) == 212",
            "assert to_fahrenheit(-40) == -40",
        ],
    ),
    Snippet(
        "make_grid", "Build a game board",
        "Create a rows x cols grid where every cell starts as fill.",
        '''def make_grid(rows, cols, fill=0):
    return [[fill] * cols for _ in range(rows)]
''',
        [
            "g = make_grid(2, 3); g[0][0] = 9; assert g == [[9, 0, 0], [0, 0, 0]]",
            "assert make_grid(1, 2) == [[0, 0]]",
            "assert make_grid(0, 4) == []",
        ],
    ),
    Snippet(
        "total_from_csv", "Sum a CSV line",
        'Add up the numbers in a comma-separated line like "10,20,30".',
        '''def total_from_csv(line):
    if not line.strip():
        return 0
    total = 0
    for part in line.split(","):
        total += int(part)
    return total
''',
        [
            'assert total_from_csv("10,20,30") == 60',
            'assert total_from_csv("5") == 5',
            'assert total_from_csv(" 7, 8 ") == 15',
            'assert total_from_csv("") == 0',
        ],
    ),
]

SNIPPETS_BY_ID = {s.id: s for s in SNIPPETS}


OFFLINE_BUGS: list[OfflineBug] = [
    OfflineBug(
        "sum_evens", "scope",
        '''def sum_evens(nums):
    for n in nums:
        total = 0
        if n % 2 == 0:
            total += n
    return total
''',
        [
            "Trace `total` by hand for [1, 2, 3, 4]. What is it after each pass of the loop?",
            "Something happens to `total` at the start of *every* iteration. Should it?",
            "Move `total = 0` above the `for` loop so it is set once, before counting starts.",
        ],
        "The accumulator was initialised inside the loop, so it was wiped on every pass and only "
        "the last element could ever count. With an empty list the loop never ran, so `total` "
        "was never created at all (UnboundLocalError). Rule of thumb: set accumulators up *before* "
        "the loop that adds to them.",
    ),
    OfflineBug(
        "sum_evens", "missing_return",
        '''def sum_evens(nums):
    total = 0
    for n in nums:
        if n % 2 == 0:
            total += n
        return total
''',
        [
            "How many times does the loop actually run before the function finishes?",
            "Look at the indentation of `return`. Which block does it belong to?",
            "Dedent `return total` so it lines up with `for`, i.e. it runs after the loop ends.",
        ],
        "The `return` was indented inside the loop, so the function exited after looking at only "
        "the first number, and returned None for an empty list. In Python, indentation *is* the "
        "control flow: a return inside a loop body ends the whole function on the first pass.",
    ),
    OfflineBug(
        "pairwise_diffs", "off_by_one",
        '''def pairwise_diffs(nums):
    diffs = []
    for i in range(len(nums)):
        diffs.append(nums[i + 1] - nums[i])
    return diffs
''',
        [
            "Which test errors rather than fails? What index is it trying to read?",
            "On the last iteration, what are `i` and `i + 1` for a list of length 4?",
            "A list of n items has n - 1 neighbouring pairs: loop over `range(len(nums) - 1)`.",
        ],
        "The loop ran one step too far: on the final pass `i + 1` pointed past the end of the "
        "list, raising IndexError. Whenever the body reads `nums[i + 1]`, the range must stop one "
        "earlier. Count the *pairs*, not the items.",
    ),
    OfflineBug(
        "pairwise_diffs", "off_by_one",
        '''def pairwise_diffs(nums):
    diffs = []
    for i in range(1, len(nums) - 1):
        diffs.append(nums[i + 1] - nums[i])
    return diffs
''',
        [
            "Compare the expected and actual lists for [1, 4, 9, 16]. Which difference is missing?",
            "Where does the loop start? Is the very first pair (index 0 and 1) ever visited?",
            "Start the range at 0: `range(len(nums) - 1)`.",
        ],
        "The range started at 1, so the first pair was silently skipped. Off-by-one errors happen "
        "at *both* ends of a range; check the first and last iteration whenever you write one.",
    ),
    OfflineBug(
        "count_words", "dict_key",
        '''def count_words(text):
    counts = {}
    for word in text.lower().split():
        if word in counts:
            counts[word] += 1
        counts[word] = 1
    return counts
''',
        [
            'For "the cat the hat", what is counts["the"] right after the second "the"?',
            "The increment happens, and then the very next line runs too. What does it do?",
            "Put `counts[word] = 1` in an `else:` branch so it only runs for new words.",
        ],
        "The count was incremented and then immediately overwritten with 1, because the "
        "reset line ran unconditionally. An if without an else means the second line always "
        "executes. `counts.get(word, 0) + 1` avoids the branch entirely.",
    ),
    OfflineBug(
        "count_words", "mutable_default",
        '''def count_words(text, counts={}):
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1
    return counts
''',
        [
            "Each test passes on its own. What changes when they run one after another?",
            "When is the default `{}` created: on every call, or once when the function is defined?",
            "Use `counts=None` and create a fresh `{}` inside the function when it is None.",
        ],
        "Default values are evaluated once, when `def` runs. The same dictionary was reused across "
        "calls, so words from earlier calls leaked into later results. Use None as the default and "
        "build the mutable object inside the function.",
    ),
    OfflineBug(
        "add_item", "mutable_default",
        '''def add_item(item, basket=[]):
    basket.append(item)
    return basket
''',
        [
            "The first test passes and the second fails. What is still in the basket from before?",
            "How many different list objects does `basket=[]` ever create?",
            "Default to `None` and create `basket = []` inside the function when it is None.",
        ],
        "`basket=[]` builds one list when the function is defined, and every call without a basket "
        "shares it. That is why 'apple' showed up in the second customer's basket. This is the most "
        "famous Python gotcha: never use a mutable object as a default value.",
    ),
    OfflineBug(
        "remove_negatives", "mutate_while_iterating",
        '''def remove_negatives(nums):
    for n in nums:
        if n < 0:
            nums.remove(n)
    return nums
''',
        [
            "For [3, -1, -2, 4], which negative survives? Why that one?",
            "When you remove an item, everything after it shifts left. Where is the loop's cursor?",
            "Build a new list instead of removing from the one you're looping over.",
        ],
        "Removing from a list while iterating over it shifts the remaining items left, so the loop "
        "skips the element right after each removal. It also modified the caller's list. Loop over "
        "the original and append keepers to a new list (or use a comprehension).",
    ),
    OfflineBug(
        "remove_negatives", "boundary_compare",
        '''def remove_negatives(nums):
    result = []
    for n in nums:
        if n > 0:
            result.append(n)
    return result
''',
        [
            "Which number in the failing test disappeared even though it isn't negative?",
            "Is 0 negative? What does the condition say about 0?",
            "Keep numbers where `n >= 0`.",
        ],
        "Zero isn't negative, but `n > 0` threw it away. Boundary values (0, empty, exactly the "
        "limit) are where comparisons go wrong; always test the value sitting on the line.",
    ),
    OfflineBug(
        "remove_negatives", "aliasing",
        '''def remove_negatives(nums):
    result = nums
    for n in list(nums):
        if n < 0:
            result.remove(n)
    return result
''',
        [
            "The return values are right. Which test still fails, and what does it check?",
            "After `result = nums`, how many lists exist in memory?",
            "Start from a fresh list (`result = []` and append), or copy with `nums[:]`.",
        ],
        "`result = nums` doesn't copy anything; it gives the same list a second name. Removing "
        "from `result` also removed from the caller's data. Assignment binds names to objects; use "
        "`list(x)`, `x[:]` or `x.copy()` when you need an independent copy.",
    ),
    OfflineBug(
        "average", "type_mixup",
        '''def average(scores):
    if not scores:
        return 0.0
    return round(sum(scores) // len(scores), 1)
''',
        [
            "For [1, 2], what does the function return, and what type is it?",
            "Look closely at the division operator. What does `3 // 2` give?",
            "Use true division `/` so the decimal part is kept.",
        ],
        "`//` is floor division: it throws the fractional part away, so 1.5 became 1. Use `/` for "
        "averages and only reach for `//` when you want whole-number results such as pages or "
        "rows.",
    ),
    OfflineBug(
        "is_valid_password", "logic",
        '''def is_valid_password(pw):
    has_digit = any(c.isdigit() for c in pw)
    has_upper = any(c.isupper() for c in pw)
    return len(pw) >= 8 and has_digit or has_upper
''',
        [
            '"NoDigitsHere" is accepted. Which part of the condition lets it through?',
            "`and` binds tighter than `or`. Add the brackets Python silently adds.",
            "Every rule must hold, so join all three with `and`.",
        ],
        "Python reads `a and b or c` as `(a and b) or c`, so any password with an uppercase letter "
        "passed regardless of length or digits. When mixing and/or, write the brackets yourself.",
    ),
    OfflineBug(
        "is_valid_password", "boundary_compare",
        '''def is_valid_password(pw):
    has_digit = any(c.isdigit() for c in pw)
    has_upper = any(c.isupper() for c in pw)
    return len(pw) > 8 and has_digit and has_upper
''',
        [
            'Which password sits exactly on the length limit? How long is "Exactly8"?',
            '"At least 8" includes 8. Does the comparison?',
            "Use `>=` for 'at least'.",
        ],
        "'At least 8' means 8 is allowed, but `> 8` rejected it. Translate the words carefully: "
        "'at least' is >=, 'more than' is >, 'up to' is <=.",
    ),
    OfflineBug(
        "binary_search", "boundary_compare",
        '''def binary_search(items, target):
    lo, hi = 0, len(items) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if items[mid] == target:
            return mid
        if items[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
''',
        [
            "Searching for 9 fails. Write down lo and hi on every iteration.",
            "When lo == hi there's still one candidate left. Does the loop check it?",
            "Use `while lo <= hi` since `hi` is an inclusive index.",
        ],
        "With `hi = len(items) - 1` the search range is inclusive on both ends, so the loop must "
        "keep going while `lo <= hi`. Stopping at `lo < hi` never checked the last remaining "
        "element. Pick one convention (inclusive or half-open) and keep the loop condition "
        "consistent with it.",
    ),
    OfflineBug(
        "letter_grade", "boundary_compare",
        '''def letter_grade(score):
    if score > 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    return "F"
''',
        [
            "Which exact score gets the wrong grade?",
            "Is 80 an A by the rules? Does `score > 80` agree?",
            "Use `>= 80` to include the boundary.",
        ],
        "The rule says 80 *and above* is an A, but `> 80` excluded 80 itself. Grade cut-offs, "
        "age limits and prices are classic boundary bugs; test the exact cut-off value.",
    ),
    OfflineBug(
        "letter_grade", "logic",
        '''def letter_grade(score):
    if score >= 50:
        return "C"
    elif score >= 65:
        return "B"
    elif score >= 80:
        return "A"
    return "F"
''',
        [
            "92 gets a C. Which branch catches it first?",
            "if/elif stops at the first true condition. In what order should the checks go?",
            "Check the highest threshold first: 80, then 65, then 50.",
        ],
        "if/elif chains stop at the first match, and every score of 80 also satisfies `>= 50`, so "
        "the B and A branches could never run. Order range checks from most specific to least.",
    ),
    OfflineBug(
        "to_fahrenheit", "missing_return",
        '''def to_fahrenheit(celsius):
    fahrenheit = celsius * 9 / 5 + 32
    print(fahrenheit)
''',
        [
            "The right number appears on screen, yet the test fails. What does the function *give back*?",
            "What does a Python function return if it never reaches a `return` statement?",
            "Replace `print(...)` with `return fahrenheit`.",
        ],
        "Printing shows a value to a human; returning hands it to the caller. With no return "
        "statement the function gave back None. If code elsewhere needs the value, return it.",
    ),
    OfflineBug(
        "make_grid", "aliasing",
        '''def make_grid(rows, cols, fill=0):
    return [[fill] * cols] * rows
''',
        [
            "Setting one cell changed a whole column. How many distinct row lists exist?",
            "`[row] * 2` copies the *reference* to row, not the row itself.",
            "Build each row separately: `[[fill] * cols for _ in range(rows)]`.",
        ],
        "Multiplying the outer list repeated the same inner list object, so every 'row' was the "
        "same row. A list comprehension creates a new inner list on each iteration.",
    ),
    OfflineBug(
        "total_from_csv", "type_mixup",
        '''def total_from_csv(line):
    if not line.strip():
        return 0
    total = 0
    for part in line.split(","):
        total += part
    return total
''',
        [
            "Read the TypeError word by word. Which two types are being added?",
            'What type is each piece produced by `"10,20".split(",")`?',
            "Convert each part with `int(part)` before adding it.",
        ],
        "`split` always produces strings, so the loop tried to add '10' to the integer 0. Text "
        "from files, input() and split() is str until you convert it.",
    ),
]


def offline_bugs_for(snippet_id: str | None = None, category: str | None = None) -> list[OfflineBug]:
    out = OFFLINE_BUGS
    if snippet_id:
        out = [b for b in out if b.snippet_id == snippet_id]
    if category:
        out = [b for b in out if b.category == category]
    return out
