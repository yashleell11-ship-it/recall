/**
 * Fixture backend, enabled with NEXT_PUBLIC_MOCK=1.
 *
 * Not a stub: it holds mutable state for the lifetime of the tab, so grading a
 * card removes it from the queue (grade 1 pushes it back), approving pending
 * cards drains the triage list, and settings changes stick. That is what makes
 * it useful for building against while the Python API is being written.
 *
 * The numbers are meant to look like a real second-semester deck in week
 * eleven, not like a fresh install: 1,240 active cards, a 21-day streak, a
 * daily cap that today's load actually collides with.
 */

import type {
  CardKind,
  DecideAction,
  DecideResponse,
  Explanation,
  GenerateResponse,
  Grade,
  PendingCard,
  PendingResponse,
  QueueCard,
  QueueResponse,
  ReviewResponse,
  Settings,
  Source,
  Stats,
  TestKind,
  TestPaper,
  TestQuestion,
  TestResult,
  TestSummary,
  Topic,
  UploadResponse,
  Verdict,
} from "./types";
import { initialState, intervalDays, nextState } from "./fsrs";
import { ApiError } from "./http";
import { marksFor, scoreFor } from "./marks";

/* --- deck ---------------------------------------------------------------- */

interface Seed {
  t: string;
  k: CardKind;
  p: string;
  q: string;
  a: string;
  c?: string;
  src: string;
}

const MATHS_SRC = "maths-unit3-calculus-notes.pdf";
const MATHS_SRC2 = "maths-unit4-linear-algebra.pdf";
const CSE_SRC = "cse111-pointers-and-memory.pdf";
const CSE_SRC2 = "cse111-lecture-09-arrays.pdf";
const INT108_SRC = "int108-python-lectures-05-08.pdf";
const INT335_SRC = "int335-shell-scripting-lab.pdf";
const INT335_SRC2 = "int335-filesystems-permissions.pdf";
const HTML_SRC = "html-semantics-and-forms.pdf";

const ACTIVE_SEEDS: Seed[] = [
  // --- MATHS ---
  {
    t: "MATHS",
    k: "qa",
    p: "p31",
    q: "State Rolle's theorem.",
    a: "If f is continuous on [a, b], differentiable on (a, b), and f(a) = f(b), then there is at least one c in (a, b) with f′(c) = 0.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p34",
    q: "Maclaurin series for e^x",
    a: "1 + x + x²/2! + x³/3! + …",
    c: "The Maclaurin series for e^x is {{c1::1 + x + x²/2! + x³/3! + …}}, and it converges for every real x.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p37",
    q: "What does a non-zero Wronskian at a point tell you about a set of solutions?",
    a: "That they are linearly independent on the interval. A zero Wronskian alone does not prove dependence unless the functions solve the same linear ODE.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p29",
    q: "Indeterminate forms for L'Hôpital",
    a: "0/0 and ∞/∞",
    c: "L'Hôpital's rule may only be applied when the limit has the indeterminate form {{c1::0/0}} or {{c2::∞/∞}}.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p42",
    q: "Give the integrating factor for dy/dx + P(x)·y = Q(x).",
    a: "μ(x) = e^(∫P(x)dx). Multiplying through makes the left side the exact derivative (μy)′.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p12",
    q: "For any matrix, how do row rank and column rank relate?",
    a: "They are always equal. That common value is the rank.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p14",
    q: "Invertibility and the determinant",
    a: "≠ 0",
    c: "A square matrix A is invertible if and only if det(A) {{c1::≠ 0}}.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p18-p19",
    q: "What is the geometric meaning of an eigenvector of A?",
    a: "A non-zero vector whose direction A leaves unchanged. A only scales it, by the eigenvalue λ.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p22",
    q: "State the Cauchy–Schwarz inequality for real vectors.",
    a: "|⟨u, v⟩| ≤ ‖u‖·‖v‖, with equality exactly when u and v are linearly dependent.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p27",
    q: "Derivative of arctan",
    a: "1/(1 + x²)",
    c: "d/dx arctan(x) = {{c1::1/(1 + x²)}}.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p45",
    q: "What is the trace of a square matrix, and what does it equal?",
    a: "The sum of the diagonal entries. It equals the sum of the eigenvalues counted with algebraic multiplicity.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p39",
    q: "When is a power series Σaₙ(x − a)ⁿ absolutely convergent?",
    a: "For |x − a| < R, where the radius R satisfies 1/R = lim sup |aₙ|^(1/n). Behaviour at |x − a| = R must be checked separately.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p16",
    q: "Rank–nullity",
    a: "rank(A) + nullity(A) = n",
    c: "For a linear map on an n-dimensional space, {{c1::rank(A) + nullity(A) = n}}.",
    src: MATHS_SRC2,
  },

  // --- CSE111 ---
  {
    t: "CSE111",
    k: "qa",
    p: "p7",
    q: "What is sizeof(char) in C, and why?",
    a: "Exactly 1, by definition. The standard defines a byte as the size of a char, whatever number of bits that is on the platform.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p11",
    q: "malloc failure",
    a: "NULL",
    c: "malloc returns {{c1::NULL}} when it cannot satisfy the request, so the result must be checked before it is dereferenced.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p14",
    q: 'What is the difference between char *s = "hi"; and char s[] = "hi";?',
    a: "The first points at a string literal, which lives in read-only storage — writing through it is undefined behaviour. The second copies the literal into a mutable array the function owns.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p9",
    q: "Why does an array decay to a pointer when passed to a function?",
    a: "C passes everything by value. The array expression converts to a pointer to its first element, so the length is lost and must be passed separately.",
    src: CSE_SRC2,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p21",
    q: "static at file scope",
    a: "internal linkage",
    c: "Applying static to a file-scope function gives it {{c1::internal linkage}}, so no other translation unit can refer to it.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p16",
    q: "What does int *p[10] declare?",
    a: "An array of 10 pointers to int. A pointer to an array of 10 ints would be int (*p)[10] — [] binds tighter than *.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p24",
    q: "Define undefined behaviour and give one everyday example.",
    a: "Behaviour on which the standard places no requirements at all — the compiler may assume it never happens. Example: reading an uninitialised local, or indexing one past the end of an array.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p5",
    q: "Post- vs pre-increment",
    a: "before / after",
    c: "x++ evaluates to the value {{c1::before}} the increment; ++x evaluates to the value {{c2::after}} it.",
    src: CSE_SRC2,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p28",
    q: "How do you free a 2-D array built as an array of row pointers?",
    a: "Free every row pointer first, then free the array of pointers. Freeing the outer block first loses the addresses of the rows.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p12",
    q: "What is the difference between the stack and the heap for a C program?",
    a: "Stack memory is allocated and released automatically with the enclosing call frame. Heap memory comes from malloc and lives until the program frees it.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p19",
    q: "Dangling pointer",
    a: "freed",
    c: "A dangling pointer is one that still holds the address of memory that has already been {{c1::freed}}; using it is undefined behaviour.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p31",
    q: "Why is gets() removed from the C standard library?",
    a: "It has no way to bound the write, so any input longer than the buffer overflows it. fgets, which takes a size, replaces it.",
    src: CSE_SRC2,
  },

  // --- INT108 ---
  {
    t: "INT108",
    k: "qa",
    p: "p8",
    q: "What does [x*x for x in r if x % 2] build?",
    a: "A new list holding the squares of the odd elements of r, built eagerly. A generator expression with parentheses would build it lazily instead.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p15",
    q: "Mutable default arguments",
    a: "once, when the function is defined",
    c: "Python evaluates default arguments {{c1::once, when the function is defined}}, which is why a mutable default such as [] is shared across every call.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p6",
    q: "What is the difference between is and ==?",
    a: "is compares identity — whether both names refer to the same object. == compares value through __eq__.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p27",
    q: "What exactly does the GIL prevent?",
    a: "More than one thread executing Python bytecode at a time in CPython. Threads still overlap during I/O and inside C extensions that release it.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p11",
    q: "Reverse slice",
    a: "a reversed copy",
    c: "a[::-1] returns {{c1::a reversed copy}} of the sequence, leaving the original untouched.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p18",
    q: "Why can a tuple be a dict key when a list cannot?",
    a: "Keys must be hashable. A tuple of hashable items is hashable; a list is mutable, so its hash would change and it is deliberately unhashable.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p22",
    q: "What makes a function a generator",
    a: "yield",
    c: "A function becomes a generator as soon as its body contains a {{c1::yield}}; calling it returns an iterator and runs none of the body.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p13",
    q: "What does with open(p) as f: guarantee?",
    a: "That the file is closed when the block exits, including when it exits by exception. That is the context manager protocol, not anything special about files.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p20",
    q: "What does dict.items() return in Python 3?",
    a: "A dict_items view — a live window on the dictionary, not a copied list. It reflects later mutations.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p24",
    q: "How does collections.defaultdict differ from dict?",
    a: "A missing key is created by calling the factory instead of raising KeyError. Plain lookup of an absent key therefore mutates the dictionary.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p9",
    q: "Shallow vs deep copy",
    a: "the same nested objects",
    c: "A shallow copy of a list creates a new outer list that still refers to {{c1::the same nested objects}}; copy.deepcopy walks the whole structure.",
    src: INT108_SRC,
  },

  // --- INT335 ---
  {
    t: "INT335",
    k: "qa",
    p: "p4",
    q: "What do the permission bits 755 mean on a directory?",
    a: "Owner may read, write and traverse; group and others may read and traverse. On a directory the execute bit is permission to enter it, not to run it.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "cloze",
    p: "p7",
    q: "Where file metadata lives",
    a: "inode",
    c: "A file's metadata lives in its {{c1::inode}}; the name is only a directory entry pointing at that number.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p9",
    q: "What is the difference between a hard link and a symbolic link?",
    a: "A hard link is a second directory entry for the same inode, so it cannot cross filesystems and keeps the data alive. A symlink stores a path and breaks if the target moves.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p16",
    q: "What does 2>&1 do, and why does its position matter?",
    a: "It points fd 2 at whatever fd 1 refers to at that moment. Written before a > redirect it copies the old destination, which is why > f 2>&1 and 2>&1 > f differ.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "cloze",
    p: "p18",
    q: "Pipeline exit status",
    a: "the last command",
    c: "The exit status of a pipeline is by default the status of {{c1::the last command}}, unless set -o pipefail is in force.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p12",
    q: "What happens to a process whose parent exits first?",
    a: "It is re-parented to init/systemd (PID 1), which reaps it. It becomes an orphan, not a zombie.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "cloze",
    p: "p6",
    q: "chmod u+s",
    a: "setuid",
    c: "chmod u+s sets the {{c1::setuid}} bit, so the program runs with the privileges of the file's owner rather than the caller's.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p21",
    q: "Why must cd be a shell builtin rather than a program?",
    a: "It has to change the working directory of the shell process itself. A child process cannot alter its parent's state.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p26",
    q: "What does systemctl enable do that systemctl start does not?",
    a: "enable writes the symlinks that make the unit start at boot. start only runs it right now, and the two are independent.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p14",
    q: "What is the difference between $* and $@ inside double quotes?",
    a: '"$*" joins every argument into one word separated by the first character of IFS. "$@" expands to one word per argument, which is almost always what you want.',
    src: INT335_SRC,
  },

  // --- HTML ---
  {
    t: "HTML",
    k: "qa",
    p: "p3",
    q: "When should you reach for <section> instead of <div>?",
    a: "When the group is a real part of the document outline and would carry a heading. <div> has no meaning and should be the fallback, not the default.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "cloze",
    p: "p12",
    q: "Which box-sizing includes padding and border",
    a: "border-box",
    c: "With box-sizing: {{c1::border-box}}, the width you declare already includes the padding and the border.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p8",
    q: "What alt text does a purely decorative image need?",
    a: 'An empty one: alt="". That tells assistive technology to skip it. Omitting the attribute entirely makes some readers announce the filename instead.',
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p17",
    q: "What does the shorthand flex: 1 expand to?",
    a: "flex-grow: 1; flex-shrink: 1; flex-basis: 0%. The zero basis is what makes items share space equally rather than by content width.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "cloze",
    p: "p6",
    q: "Associating a label with an input",
    a: "the for attribute to the input's id",
    c: "A <label> is tied to its control either by wrapping it or by matching {{c1::the for attribute to the input's id}}.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p7",
    q: "Why must a form control carry a name attribute?",
    a: "Without a name the control's value is simply not included in the submitted form data, however it is labelled or styled.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "cloze",
    p: "p14",
    q: "Default position value",
    a: "static",
    c: "The initial value of position is {{c1::static}}, and a static box ignores top, right, bottom and left entirely.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p15",
    q: "How do display: none and visibility: hidden differ?",
    a: "display: none removes the box from layout altogether. visibility: hidden keeps the space it occupied. Neither is exposed to assistive technology.",
    src: HTML_SRC,
  },
];

const PENDING_SEEDS: Seed[] = [
  {
    t: "MATHS",
    k: "qa",
    p: "p47",
    q: "State the mean value theorem.",
    a: "If f is continuous on [a, b] and differentiable on (a, b), some c in (a, b) satisfies f′(c) = (f(b) − f(a))/(b − a).",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p48",
    q: "Second derivative test",
    a: "a local minimum",
    c: "If f′(c) = 0 and f″(c) > 0, then c is {{c1::a local minimum}}.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p50",
    q: "What is the determinant of a triangular matrix?",
    a: "The product of the diagonal entries.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p51",
    q: "What is the sum of a convergent geometric series Σarⁿ from n = 0?",
    a: "a/(1 − r) for |r| < 1.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p52",
    q: "Orthogonal matrix inverse",
    a: "its transpose",
    c: "For an orthogonal matrix Q, the inverse equals {{c1::its transpose}}.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p53",
    q: "When is an improper integral said to converge?",
    a: "When the limit defining it exists and is finite.",
    src: MATHS_SRC,
  },
  {
    t: "MATHS",
    k: "qa",
    p: "p55",
    q: "What does it mean for a matrix to be positive definite?",
    a: "xᵀAx > 0 for every non-zero x. Equivalently, every eigenvalue of a symmetric A is positive.",
    src: MATHS_SRC2,
  },
  {
    t: "MATHS",
    k: "cloze",
    p: "p56",
    q: "Integration by parts",
    a: "∫u dv = uv − ∫v du",
    c: "Integration by parts states {{c1::∫u dv = uv − ∫v du}}.",
    src: MATHS_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p33",
    q: "What is the difference between calloc and malloc?",
    a: "calloc takes a count and a size, and zeroes the memory it returns. malloc leaves the contents indeterminate.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p34",
    q: "realloc failure",
    a: "the original block is left untouched",
    c: "If realloc fails it returns NULL and {{c1::the original block is left untouched}}, so assigning the result straight back over the old pointer leaks it.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p36",
    q: "Why is strcpy considered unsafe?",
    a: "It copies until the terminating NUL with no knowledge of the destination size, so a longer source overflows the buffer.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p37",
    q: "What is a struct's padding, and why does the compiler insert it?",
    a: "Unused bytes added between members so each one lands on its required alignment boundary. It is why sizeof(struct) can exceed the sum of the members.",
    src: CSE_SRC2,
  },
  {
    t: "CSE111",
    k: "cloze",
    p: "p38",
    q: "const char * vs char * const",
    a: "the pointed-to characters",
    c: "In const char *p, the const protects {{c1::the pointed-to characters}}; in char * const p it protects the pointer itself.",
    src: CSE_SRC,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p40",
    q: "What does the preprocessor do with #include?",
    a: "It textually substitutes the contents of the named file before compilation proper begins.",
    src: CSE_SRC2,
  },
  {
    t: "CSE111",
    k: "qa",
    p: "p41",
    q: "Why should a macro's parameters be parenthesised in its body?",
    a: "Because the macro expands as text, so an unparenthesised argument binds by the surrounding operator precedence and silently changes the meaning.",
    src: CSE_SRC2,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p29",
    q: "What is the difference between append and extend on a list?",
    a: "append adds its argument as one element. extend iterates the argument and adds each item.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p30",
    q: "What *args collects",
    a: "a tuple",
    c: "In a function signature, *args collects the extra positional arguments into {{c1::a tuple}} and **kwargs collects keyword arguments into a dict.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p31",
    q: "What does the __name__ == \"__main__\" guard actually do?",
    a: "It runs the block only when the file is executed as a script, not when it is imported, because __name__ is the module name on import.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p32",
    q: "How does a set differ from a list in Python?",
    a: "A set is unordered, holds only hashable items, deduplicates, and tests membership in roughly constant time rather than linear.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "cloze",
    p: "p33",
    q: "Decorator syntax",
    a: "f = decorator(f)",
    c: "Writing @decorator above a function definition is shorthand for {{c1::f = decorator(f)}} immediately after it.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p35",
    q: "What does enumerate give you that range(len(x)) does not?",
    a: "The index and the item together, without a second lookup, and it works on any iterable rather than only on sequences.",
    src: INT108_SRC,
  },
  {
    t: "INT108",
    k: "qa",
    p: "p36",
    q: "Why is str immutable in Python?",
    a: "So strings can be hashed and interned safely and shared freely. Every apparent mutation builds a new string.",
    src: INT108_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p28",
    q: "What does chmod -R differ from chmod in?",
    a: "-R descends into directories and applies the change to everything underneath, which is how directories accidentally lose their traverse bit.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "cloze",
    p: "p29",
    q: "Sticky bit on /tmp",
    a: "only the owner of a file may delete it",
    c: "The sticky bit on a world-writable directory such as /tmp means {{c1::only the owner of a file may delete it}}.",
    src: INT335_SRC2,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p31",
    q: "What is the difference between > and >> in the shell?",
    a: "> truncates the target file before writing; >> appends to it.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p32",
    q: "What does the shell do with an unquoted variable containing spaces?",
    a: "It word-splits the expansion and then glob-expands each word, which is why almost every expansion should be quoted.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "cloze",
    p: "p33",
    q: "Signal that cannot be caught",
    a: "SIGKILL",
    c: "{{c1::SIGKILL}} cannot be caught, blocked, or ignored by the receiving process.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p35",
    q: "What is the purpose of a shebang line?",
    a: "It tells the kernel which interpreter to hand the file to when it is executed directly.",
    src: INT335_SRC,
  },
  {
    t: "INT335",
    k: "qa",
    p: "p37",
    q: "What does set -e do, and what is its main trap?",
    a: "It aborts the script when a command exits non-zero. It does not fire for commands in conditionals or, by default, in the middle of a pipeline.",
    src: INT335_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p19",
    q: "What is the purpose of the viewport meta tag?",
    a: "It stops mobile browsers rendering at a fake ~980px width and then scaling down, so CSS pixels match device-independent pixels.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "cloze",
    p: "p21",
    q: "Landmark element for primary content",
    a: "<main>",
    c: "The {{c1::<main>}} element marks the primary content of the document, and there should be exactly one per page.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p22",
    q: "Why should heading levels not skip?",
    a: "Screen reader users navigate by heading level, and a jump from h2 to h4 makes the outline read as if a section is missing.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p24",
    q: "What is the difference between <button> and a <div> with a click handler?",
    a: "<button> is focusable, fires on Enter and Space, is announced as a button, and participates in forms. A div does none of that without extra work.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "cloze",
    p: "p26",
    q: "Which CSS units are relative to the root font size",
    a: "rem",
    c: "{{c1::rem}} units are relative to the root element's font size, while em units are relative to the element's own.",
    src: HTML_SRC,
  },
  {
    t: "HTML",
    k: "qa",
    p: "p27",
    q: "What does the defer attribute on a script do?",
    a: "It downloads the script in parallel and runs it after parsing completes, in document order. async runs it as soon as it lands, in any order.",
    src: HTML_SRC,
  },
];

/* --- state --------------------------------------------------------------- */

const TOPIC_META: { code: string; label: string }[] = [
  { code: "MATHS", label: "Engineering Mathematics II" },
  { code: "CSE111", label: "Programming in C" },
  { code: "INT108", label: "Python Programming" },
  { code: "INT335", label: "Linux and Shell Scripting" },
  { code: "HTML", label: "Web Technologies" },
];

/** Deterministic jitter, so the fixture is identical on every render. */
function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

interface MockCard extends QueueCard {
  source_filename: string;
}

function buildQueue(): MockCard[] {
  const rand = lcg(20260904);
  return ACTIVE_SEEDS.map((s, i) => {
    // First six of the deck are the day's new cards; the rest are due reviews
    // with a plausible spread of maturity.
    const isNew = i % 9 === 4 && i < 50;
    const stability = isNew ? null : Number((1.5 + rand() * 90).toFixed(2));
    const difficulty = isNew ? null : Number((2.4 + rand() * 6).toFixed(2));
    const elapsed =
      stability === null ? null : Number((stability * (0.8 + rand() * 0.7)).toFixed(2));
    return {
      id: 1000 + i,
      kind: s.k,
      question: s.q,
      answer: s.a,
      cloze_text: s.c ?? null,
      topic_code: s.t,
      page_ref: s.p,
      is_new: isNew,
      stability,
      difficulty,
      elapsed_days: elapsed,
      source_filename: s.src,
    };
  });
}

interface MockState {
  queue: MockCard[];
  pending: PendingCard[];
  settings: Settings;
  reviewedToday: number;
  againToday: number;
  streak: number;
  reviewedByTopic: Record<string, number>;
  gradedIds: Set<number>;
}

let state: MockState | null = null;

function store(): MockState {
  if (state) return state;
  state = {
    queue: buildQueue(),
    pending: PENDING_SEEDS.map((s, i) => ({
      id: 5000 + i,
      kind: s.k,
      question: s.q,
      answer: s.a,
      cloze_text: s.c ?? null,
      topic_code: s.t,
      page_ref: s.p,
      source_filename: s.src,
    })),
    settings: {
      new_cards_per_day: 15,
      daily_review_cap: 140,
      desired_retention: 0.9,
    },
    reviewedToday: 63,
    againToday: 9,
    streak: 21,
    reviewedByTopic: {
      MATHS: 24,
      CSE111: 15,
      INT108: 11,
      INT335: 8,
      HTML: 5,
    },
    gradedIds: new Set(),
  };
  return state;
}

/* Counts the dashboard shows. The queue the mock actually serves is a slice of
   a larger backlog, exactly as the real endpoint's `limit` implies. */
const BACKLOG = {
  MATHS: { due: 31, new: 4, active: 402, pending: 8 },
  CSE111: { due: 22, new: 3, active: 286, pending: 8 },
  INT108: { due: 17, new: 2, active: 241, pending: 7 },
  INT335: { due: 9, new: 2, active: 183, pending: 7 },
  HTML: { due: 5, new: 1, active: 128, pending: 5 },
} as const;

const delay = (ms = 130) => new Promise((r) => setTimeout(r, ms));

/** Strip the fixture-only field so the shape matches the contract exactly. */
function toQueueCard(c: MockCard): QueueCard {
  return {
    id: c.id,
    kind: c.kind,
    question: c.question,
    answer: c.answer,
    cloze_text: c.cloze_text,
    topic_code: c.topic_code,
    page_ref: c.page_ref,
    is_new: c.is_new,
    stability: c.stability,
    difficulty: c.difficulty,
    elapsed_days: c.elapsed_days,
  };
}

function isoDay(offsetDays: number): string {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

/* --- endpoints ----------------------------------------------------------- */

export async function getTopics(): Promise<Topic[]> {
  await delay();
  const s = store();
  return TOPIC_META.map((t, i) => {
    const b = BACKLOG[t.code as keyof typeof BACKLOG];
    const servedDue = s.queue.filter(
      (c) => c.topic_code === t.code && !c.is_new,
    ).length;
    const servedNew = s.queue.filter(
      (c) => c.topic_code === t.code && c.is_new,
    ).length;
    const pending = s.pending.filter((c) => c.topic_code === t.code).length;
    return {
      id: i + 1,
      code: t.code,
      label: t.label,
      due: Math.max(servedDue, Math.min(b.due, servedDue + 20)),
      new: Math.min(b.new, servedNew + 2),
      active: b.active,
      pending,
    };
  });
}

export async function getQueue(
  topic?: string,
  limit?: number,
): Promise<QueueResponse> {
  await delay();
  const s = store();
  const pool = topic
    ? s.queue.filter((c) => c.topic_code === topic)
    : s.queue.slice();

  const slotsLeft = Math.max(
    0,
    s.settings.daily_review_cap - s.reviewedToday,
  );
  const wanted = topic
    ? pool.length
    : Object.values(BACKLOG).reduce((n, b) => n + b.due + b.new, 0);

  const take = Math.min(pool.length, limit ?? 50, slotsLeft);
  const cards = pool.slice(0, take);

  const totalDue = Object.values(BACKLOG).reduce((n, b) => n + b.due, 0);
  const totalNew = Object.values(BACKLOG).reduce((n, b) => n + b.new, 0);
  const servedDue = cards.filter((c) => !c.is_new).length;
  const servedNew = cards.filter((c) => c.is_new).length;

  return {
    cards: cards.map(toQueueCard),
    due_remaining: topic
      ? Math.max(0, pool.filter((c) => !c.is_new).length - servedDue)
      : Math.max(0, Math.min(totalDue, slotsLeft) - servedDue),
    new_remaining: topic
      ? Math.max(0, pool.filter((c) => c.is_new).length - servedNew)
      : Math.max(0, totalNew - servedNew),
    cap_reached: !topic && wanted > slotsLeft,
  };
}

export async function postReview(
  cardId: number,
  grade: Grade,
): Promise<ReviewResponse> {
  await delay(70);
  const s = store();
  const idx = s.queue.findIndex((c) => c.id === cardId);
  const card = idx >= 0 ? s.queue[idx] : null;

  const prior =
    card && card.stability != null && card.difficulty != null
      ? { stability: card.stability, difficulty: card.difficulty }
      : null;
  const elapsed = card?.elapsed_days ?? 0;

  const next = prior
    ? nextState(prior, grade, elapsed)
    : initialState(grade);
  const days = intervalDays(next.stability, s.settings.desired_retention);

  if (idx >= 0) {
    // Grade 1 sends the card back to the end of the queue, as a real
    // scheduler's relearning step would.
    const [removed] = s.queue.splice(idx, 1);
    if (grade === 1) {
      s.queue.push({
        ...removed,
        is_new: false,
        stability: next.stability,
        difficulty: next.difficulty,
        elapsed_days: 0,
      });
      s.againToday += 1;
    }
    if (!s.gradedIds.has(cardId)) {
      s.gradedIds.add(cardId);
      s.reviewedToday += 1;
      s.reviewedByTopic[removed.topic_code] =
        (s.reviewedByTopic[removed.topic_code] ?? 0) + 1;
    }
  }

  const due = new Date();
  due.setTime(due.getTime() + days * 86400000);

  return {
    card_id: cardId,
    interval_days: Number(days.toFixed(4)),
    due_at: due.toISOString(),
    stability: Number(next.stability.toFixed(4)),
    difficulty: Number(next.difficulty.toFixed(4)),
  };
}

export async function getPending(
  limit = 50,
  offset = 0,
  topic?: string,
): Promise<PendingResponse> {
  await delay();
  const s = store();
  const pool = topic
    ? s.pending.filter((c) => c.topic_code === topic)
    : s.pending;
  return { cards: pool.slice(offset, offset + limit), total: pool.length };
}

export async function postDecide(
  ids: number[],
  _action: DecideAction,
): Promise<DecideResponse> {
  await delay(180);
  const s = store();
  const before = s.pending.length;
  s.pending = s.pending.filter((c) => !ids.includes(c.id));
  void _action;
  return { updated: before - s.pending.length };
}

export async function getSettings(): Promise<Settings> {
  await delay(80);
  return { ...store().settings };
}

export async function putSettings(patch: Partial<Settings>): Promise<Settings> {
  await delay(160);
  const s = store();
  s.settings = { ...s.settings, ...patch };
  return { ...s.settings };
}

export async function getStats(): Promise<Stats> {
  await delay();
  const s = store();
  const counts = [58, 71, 44, 0, 96, 82, 63, 77, 51, 88, 34, 69, 74];
  const last14 = counts.map((count, i) => ({
    date: isoDay(i - 13),
    count,
  }));
  last14.push({ date: isoDay(0), count: s.reviewedToday });

  return {
    today: {
      reviewed: s.reviewedToday,
      again: s.againToday,
      streak: s.streak,
    },
    by_topic: TOPIC_META.map((t, i) => {
      const b = BACKLOG[t.code as keyof typeof BACKLOG];
      return {
        id: i + 1,
        code: t.code,
        label: t.label,
        due: b?.due ?? 0,
        new: b?.new ?? 0,
        active: b?.active ?? 0,
        pending: b?.pending ?? 0,
        reviewed: s.reviewedByTopic[t.code] ?? 0,
      };
    }),
    last_14_days: last14,
    totals: {
      active: Object.values(BACKLOG).reduce((n, b) => n + b.active, 0),
      pending: s.pending.length,
      sources: SOURCES.length + uploaded.length,
    },
  };
}

const SOURCES: Omit<Source, "added_at">[] = [
  {
    id: 1,
    filename: MATHS_SRC,
    topic_code: "MATHS",
    accepted: 84,
    rejected: 11,
    cost_estimate: 0.0412,
  },
  {
    id: 2,
    filename: MATHS_SRC2,
    topic_code: "MATHS",
    accepted: 61,
    rejected: 7,
    cost_estimate: 0.0298,
  },
  {
    id: 3,
    filename: CSE_SRC,
    topic_code: "CSE111",
    accepted: 73,
    rejected: 19,
    cost_estimate: 0.0367,
  },
  {
    id: 4,
    filename: CSE_SRC2,
    topic_code: "CSE111",
    accepted: 48,
    rejected: 6,
    cost_estimate: 0.0221,
  },
  {
    id: 5,
    filename: INT108_SRC,
    topic_code: "INT108",
    accepted: 96,
    rejected: 14,
    cost_estimate: 0.0503,
  },
  {
    id: 6,
    filename: "int108-lab-manual-week-06.pdf",
    topic_code: "INT108",
    accepted: 39,
    rejected: 22,
    cost_estimate: 0.0187,
  },
  {
    id: 7,
    filename: INT335_SRC,
    topic_code: "INT335",
    accepted: 67,
    rejected: 9,
    cost_estimate: 0.0341,
  },
  {
    id: 8,
    filename: INT335_SRC2,
    topic_code: "INT335",
    accepted: 52,
    rejected: 5,
    cost_estimate: 0.0264,
  },
  {
    id: 9,
    filename: HTML_SRC,
    topic_code: "HTML",
    accepted: 58,
    rejected: 12,
    cost_estimate: 0.0289,
  },
  {
    id: 10,
    filename: "html-css-layout-workshop.pdf",
    topic_code: "HTML",
    accepted: 44,
    rejected: 8,
    cost_estimate: 0.0213,
  },
  {
    id: 11,
    filename: "maths-tutorial-sheet-07.pdf",
    topic_code: "MATHS",
    accepted: 27,
    rejected: 31,
    cost_estimate: 0.0154,
  },
  {
    id: 12,
    filename: "cse111-midterm-revision.md",
    topic_code: "CSE111",
    accepted: 19,
    rejected: 2,
    cost_estimate: 0.0071,
  },
];

const SOURCE_AGE_DAYS = [2, 5, 6, 9, 12, 14, 18, 21, 24, 27, 33, 41];

/** Anything uploaded during this tab's lifetime, newest first. */
const uploaded: Source[] = [];

export async function getSources(): Promise<Source[]> {
  await delay();
  return [
    ...uploaded,
    ...SOURCES.map((s, i) => ({
      ...s,
      added_at: isoDay(-SOURCE_AGE_DAYS[i]),
    })),
  ];
}

/* --- test mode ----------------------------------------------------------- */

const PAPERS: Record<TestKind, { target: number | null; limit: number | null }> =
  {
    class30: { target: 30, limit: 45 * 60 },
    endterm100: { target: 100, limit: 180 * 60 },
    fullday: { target: null, limit: null },
  };

interface MockTest {
  id: number;
  kind: TestKind;
  started_at: string;
  startedMs: number;
  time_limit_s: number | null;
  questions: TestQuestion[];
  seconds: Record<number, number>;
  submitted: boolean;
  obtained: number;
  duration_s: number | null;
}

const tests = new Map<number, MockTest>();
let nextTestId = 41;

/**
 * Weak first: high difficulty, low stability. A brand-new card has no state, so
 * it sits mid-table rather than pretending to be either.
 */
function weakness(c: MockCard): number {
  const d = c.difficulty ?? 5.5;
  const s = c.stability ?? 1;
  return d / Math.log2(2 + s);
}

/**
 * Assembly, per the contract: stratified across topics in proportion to their
 * active cards, weak cards preferred but not exclusively, greedy fill to hit
 * the target exactly. Returns fewer marks than asked for when the deck cannot
 * reach the target — the caller says so rather than padding.
 */
function assemble(pool: MockCard[], target: number | null): TestQuestion[] {
  const byTopic = new Map<string, MockCard[]>();
  for (const c of pool) {
    const list = byTopic.get(c.topic_code) ?? [];
    list.push(c);
    byTopic.set(c.topic_code, list);
  }

  // Within a topic: weakest first, but every fourth pick comes off the strong
  // end so a paper is not purely punishment.
  const ordered = new Map<string, MockCard[]>();
  for (const [code, cards] of byTopic) {
    const sorted = [...cards].sort((a, b) => weakness(b) - weakness(a));
    const out: MockCard[] = [];
    let head = 0;
    let tail = sorted.length - 1;
    while (head <= tail) {
      out.push(sorted[head++]);
      if (out.length % 4 === 0 && head <= tail) out.push(sorted[tail--]);
    }
    ordered.set(code, out);
  }

  // Round-robin weighted by each topic's share, which is stratification.
  const taken = new Map<string, number>();
  const draw: MockCard[] = [];
  const total = pool.length;
  for (let n = 0; n < total; n++) {
    let best: string | null = null;
    let bestRatio = Infinity;
    for (const [code, cards] of ordered) {
      const used = taken.get(code) ?? 0;
      if (used >= cards.length) continue;
      const ratio = used / (cards.length / total);
      if (ratio < bestRatio) {
        bestRatio = ratio;
        best = code;
      }
    }
    if (best === null) break;
    const used = taken.get(best) ?? 0;
    draw.push(ordered.get(best)![used]);
    taken.set(best, used + 1);
  }

  const questions: TestQuestion[] = [];
  let marks = 0;
  for (const c of draw) {
    const m = marksFor(c.kind, c.answer);
    if (target !== null) {
      if (marks >= target) break;
      if (marks + m > target) continue; // too big for the gap left; keep filling
    }
    marks += m;
    questions.push({
      ordinal: questions.length + 1,
      card_id: c.id,
      kind: c.kind,
      question: c.question,
      answer: c.answer,
      cloze_text: c.cloze_text,
      marks: m,
      topic_code: c.topic_code,
      page_ref: c.page_ref,
      verdict: null,
    });
  }
  return questions;
}

export async function createTest(
  kind: TestKind,
  topicCode?: string,
): Promise<TestPaper> {
  await delay(320);
  const s = store();
  const pool = topicCode
    ? s.queue.filter((c) => c.topic_code === topicCode)
    : s.queue.slice();

  const paper = PAPERS[kind];
  const questions = assemble(pool, paper.target);
  const id = nextTestId++;
  const now = Date.now();

  tests.set(id, {
    id,
    kind,
    started_at: new Date(now).toISOString(),
    startedMs: now,
    time_limit_s: paper.limit,
    questions,
    seconds: {},
    submitted: false,
    obtained: 0,
    duration_s: null,
  });

  return toPaper(tests.get(id)!);
}

function toPaper(t: MockTest): TestPaper {
  return {
    test_id: t.id,
    kind: t.kind,
    total_marks: t.questions.reduce((n, q) => n + q.marks, 0),
    time_limit_s: t.time_limit_s,
    questions: t.questions.map((q) => ({ ...q })),
  };
}

export async function getTest(id: number): Promise<TestPaper> {
  await delay();
  seedPast();
  const t = tests.get(id);
  if (!t) throw new ApiError(404, `/api/tests/${id}`, "No such test.");
  return toPaper(t);
}

export async function postAnswer(
  id: number,
  ordinal: number,
  verdict: Verdict,
  seconds: number,
): Promise<{ ok: true }> {
  await delay(60);
  const t = tests.get(id);
  if (!t) throw new ApiError(404, `/api/tests/${id}/answer`, "No such test.");
  const q = t.questions.find((x) => x.ordinal === ordinal);
  if (!q) {
    throw new ApiError(
      404,
      `/api/tests/${id}/answer`,
      `This paper has no question ${ordinal}.`,
    );
  }
  if (verdict === "partial" && q.marks < 2) {
    throw new ApiError(
      422,
      `/api/tests/${id}/answer`,
      "Partial credit needs a question worth 2 marks or more.",
    );
  }
  q.verdict = verdict;
  t.seconds[ordinal] = seconds;
  return { ok: true };
}

export async function submitTest(id: number): Promise<TestResult> {
  await delay(360);
  const t = tests.get(id);
  if (!t) throw new ApiError(404, `/api/tests/${id}/submit`, "No such test.");

  const totals = new Map<string, { obtained: number; total: number }>();
  let obtained = 0;
  for (const q of t.questions) {
    const got = scoreFor(q.verdict, q.marks);
    obtained += got;
    const row = totals.get(q.topic_code) ?? { obtained: 0, total: 0 };
    row.obtained += got;
    row.total += q.marks;
    totals.set(q.topic_code, row);
  }

  const total = t.questions.reduce((n, q) => n + q.marks, 0);
  const duration = Math.max(1, Math.round((Date.now() - t.startedMs) / 1000));

  t.submitted = true;
  t.obtained = obtained;
  t.duration_s = duration;

  return {
    obtained_marks: obtained,
    total_marks: total,
    percent: total > 0 ? Number(((obtained / total) * 100).toFixed(1)) : 0,
    duration_s: duration,
    by_topic: [...totals.entries()].map(([topic_code, r]) => ({
      topic_code,
      obtained: r.obtained,
      total: r.total,
    })),
    wrong: t.questions.filter((q) => q.verdict === "wrong").map((q) => ({ ...q })),
    partial: t.questions
      .filter((q) => q.verdict === "partial")
      .map((q) => ({ ...q })),
  };
}

/**
 * Two finished papers from earlier in the term.
 *
 * They are entries in the same map a live paper lives in, not summary rows, so
 * `GET /api/tests/{id}` answers for them exactly as the server does: the paper
 * comes back with its verdicts, and the client can see it was already
 * submitted rather than offering to sit it again.
 */
const PAST: { id: number; kind: TestKind; startedAt: string; duration: number; seed: number }[] =
  [
    {
      id: 39,
      kind: "class30",
      startedAt: `${isoDay(-9)}T09:12:00+05:30`,
      duration: 1985,
      seed: 7,
    },
    {
      id: 40,
      kind: "endterm100",
      startedAt: `${isoDay(-3)}T14:05:00+05:30`,
      duration: 8760,
      seed: 13,
    },
  ];

let seeded = false;

function seedPast() {
  if (seeded) return;
  seeded = true;
  const s = store();
  for (const p of PAST) {
    const questions = assemble(s.queue.slice(), PAPERS[p.kind].target);
    // Deterministic, and roughly the shape of a real attempt: mostly right,
    // a handful missed, one or two never attempted.
    const rand = lcg(p.seed);
    let obtained = 0;
    for (const q of questions) {
      const r = rand();
      const verdict: Verdict =
        r < 0.17 ? "wrong" : r < 0.3 && q.marks >= 2 ? "partial" : r < 0.34 ? "skipped" : "correct";
      q.verdict = verdict;
      obtained += scoreFor(verdict, q.marks);
    }
    tests.set(p.id, {
      id: p.id,
      kind: p.kind,
      started_at: p.startedAt,
      startedMs: Date.parse(p.startedAt),
      time_limit_s: PAPERS[p.kind].limit,
      questions,
      seconds: {},
      submitted: true,
      obtained,
      duration_s: p.duration,
    });
  }
}

export async function getTests(): Promise<TestSummary[]> {
  await delay();
  seedPast();
  // Newest first, exactly as a server ordering by started_at desc would.
  return [...tests.values()]
    .map((t) => ({
      id: t.id,
      kind: t.kind,
      started_at: t.started_at,
      obtained_marks: t.obtained,
      total_marks: t.questions.reduce((n, q) => n + q.marks, 0),
      duration_s: t.duration_s,
    }))
    .sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
}

/* --- teaching ------------------------------------------------------------ */

const explained = new Set<number>();

/**
 * The real endpoint quotes the card's own source chunk and refuses when it
 * cannot. The fixture builds a chunk around the card's answer and quotes a
 * verbatim slice of it, so the screen renders exactly what a grounded
 * explanation renders.
 */
export async function postExplain(cardId: number): Promise<Explanation> {
  await delay(explained.has(cardId) ? 120 : 900);
  const s = store();
  const card =
    s.queue.find((c) => c.id === cardId) ??
    [...tests.values()]
      .flatMap((t) => t.questions)
      .find((q) => q.card_id === cardId);

  if (!card) {
    throw new ApiError(404, "/api/teach/explain", "No such card.");
  }

  const answer = card.answer.trim();
  const firstSentence = answer.split(/(?<=\.)\s/)[0] ?? answer;
  const marks = marksFor(card.kind, answer);

  const wasCached = explained.has(cardId);
  explained.add(cardId);

  return {
    explanation: [
      answer,
      `The source states this directly, so the mark is for reproducing the condition exactly rather than paraphrasing it. ${
        marks >= 2
          ? "On a question worth this much the working carries the marks, not the final line — write the reason down."
          : "This is a one-mark recall question: the examiner wants the exact term, nothing around it."
      }`,
      `Most common mistake: stating the conclusion without the condition it depends on. If you wrote something close but left out the qualifier, that is the half you lost.`,
    ].join("\n\n"),
    source_quote: firstSentence,
    page_ref: card.page_ref,
    topic_code: card.topic_code,
    cached: wasCached,
  };
}

/* --- upload -------------------------------------------------------------- */

const IMAGE_EXT = /\.(png|jpe?g|webp)$/i;

export async function uploadSource(
  file: File,
  topicCode: string,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  // Enough ticks that the bar visibly moves, as it would on a phone.
  for (let i = 1; i <= 10; i++) {
    if (signal?.aborted) throw new ApiError(0, "/api/sources/upload", "Upload cancelled.");
    await delay(70);
    onProgress?.(i / 10);
  }
  await delay(240);
  if (signal?.aborted) throw new ApiError(0, "/api/sources/upload", "Upload cancelled.");

  const isImage = IMAGE_EXT.test(file.name);
  // A page of printed text is roughly 2 kB of characters; a phone photo of one
  // is a couple of hundred kB of JPEG. That ratio is why OCR output always
  // looks sparse next to the file it came from.
  const textChars = isImage
    ? Math.max(40, Math.round(file.size / 900))
    : Math.max(120, Math.round(file.size / 3.2));
  const chunks = Math.max(1, Math.round(textChars / 1400));

  const id = 100 + uploaded.length;
  uploaded.unshift({
    id,
    filename: file.name,
    topic_code: topicCode,
    added_at: isoDay(0),
    accepted: 0,
    rejected: 0,
    cost_estimate: 0,
  });

  return {
    source_id: id,
    filename: file.name,
    kind: isImage ? "image" : file.name.toLowerCase().endsWith(".pdf") ? "pdf" : "text",
    chunks,
    text_chars: textChars,
    warning: isImage
      ? "Only " +
        textChars +
        " characters came out of this image. Tesseract runs on the CPU and reads printed slides and textbook pages well, but handwriting badly. Check the generated cards carefully, or retake the photo straight-on in better light."
      : null,
  };
}

export async function generateCards(sourceId: number): Promise<GenerateResponse> {
  await delay(1500);
  const src = uploaded.find((s) => s.id === sourceId);
  const chunks = Math.max(1, Math.round((src ? 6 : 4) + (sourceId % 5)));
  const accepted = chunks * 3 + 2;
  const rejected = Math.round(accepted * 0.22);

  if (src) {
    src.accepted = accepted;
    src.rejected = rejected;
    src.cost_estimate = Number((chunks * 0.0042).toFixed(4));
  }

  const s = store();
  // Generated cards land in the triage queue, which is where the flow goes next.
  for (let i = 0; i < Math.min(accepted, 6); i++) {
    const seed = PENDING_SEEDS[i % PENDING_SEEDS.length];
    s.pending.unshift({
      id: 9000 + s.pending.length + i,
      kind: seed.k,
      question: seed.q,
      answer: seed.a,
      cloze_text: seed.c ?? null,
      topic_code: src?.topic_code ?? seed.t,
      page_ref: seed.p,
      source_filename: src?.filename ?? seed.src,
    });
  }

  return {
    accepted,
    rejected,
    cost_usd: Number((chunks * 0.0042).toFixed(4)),
    stopped_early: chunks > 9,
  };
}
