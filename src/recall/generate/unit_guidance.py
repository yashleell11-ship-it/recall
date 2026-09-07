"""What a good card looks like for one specific unit of one specific subject.

`format_guidance` in prompts.py knows the shape of the PAPER — objective,
practical, subjective. This knows the shape of the SUBJECT: that unit 1 of
MTH165 is examined by asking you to find a rank, not to define one; that the
mistake students actually make in unit 6 is dropping the a_0/2.

It lives here rather than in `lpu.py` on purpose. `lpu.py` is the registry
that gets serialised into `topics.meta` and shipped to the browser on every
page load; this is several paragraphs per unit that only the generator and the
fact checker ever read. Putting it in the registry would put it in the DB and
then in the wire.

Everything here was researched per-unit and then checked by a second pass for
mathematical correctness before being written down, because a wrong condition
in guidance becomes a wrong condition on a card and then a wrong condition in
a student's memory. Where research found nothing solid, there is no entry —
`guidance_for` returning None is a supported answer, and the prompt simply
falls back to the paper-shape guidance alone.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitGuidance:
    """One unit's worth of "write cards like this"."""

    guidance: str
    """A paragraph, in the imperative, spliced into the generation prompt."""

    traps: tuple[str, ...] = ()
    """The specific errors students (and models) make in this unit. Shown to
    the fact checker as a checklist, not to the writer — telling a model
    "don't say X" is a reliable way to make it say X."""


# Keyed by topic code, indexed by unit number - 1, so the tuple's length must
# match that subject's `units` list in lpu.py. tests/test_unit_guidance.py
# enforces that; a unit list that grows without guidance is fine (None), a
# guidance list longer than the unit list is a bug.
#
# MTH165 was mapped unit by unit against how the subject is actually taught and
# drilled for Indian first-year engineering exams — Tikle's Academy of Maths
# first, at the owner's request, then standard practice where his channel does
# not reach (it has no double/triple-integral course at all, and unit 5 says
# so rather than inventing a citation). Every unit was then re-derived by a
# second pass before being written down here, which is the only reason to trust
# it: that pass found an Euler corollary missing its continuity hypothesis, an
# error-propagation rule stated as an equality when it is a first-order
# approximation, a periodicity identity with no "positive integer" on n, an
# eigenvalue identity that is false over the reals, and a recurrence quoted
# with no function attached. All of those are corrected below.
_UNITS: dict[str, tuple[UnitGuidance, ...]] = {
    "MTH165": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour short computational cards a student can finish in "
                "under a minute: 2×2 or 3×3 integer matrices whose answers are "
                "small integers. Always write the matrix or the system out "
                "entry by entry inside the question — never say \"the given "
                "matrix\". Ask for a rank, for whether given vectors are "
                "dependent, for the value of a parameter k that makes a system "
                "inconsistent, for the eigenvalues of a small matrix, or for "
                "A⁻¹ by Cayley–Hamilton. State every hypothesis in full: say "
                "\"square\", \"non-singular\", \"counted with multiplicity\", and "
                "\"n = the number of unknowns\" rather than leaving them "
                "implied. Use cloze cards for the rank–consistency rule, the "
                "eigenvalue property list, and the characteristic-equation "
                "coefficients. Say explicitly that an eigenvector is "
                "determined only up to a non-zero scalar multiple. Never ask "
                "for diagonalization, quadratic forms, similarity, or vector "
                "spaces beyond dependence and independence."
            ),
            traps=(
                "Stopping at rank(A) = rank([A|b]) and calling the solution "
                "unique. Consistency only says a solution exists; the common "
                "rank r must then be compared with n, the number of unknowns — "
                "r = n gives a unique solution, r < n gives infinitely many "
                "with n − r free parameters.",
                "Mixing row and column operations while inverting by "
                "elementary transformations. For rank both are legal; for the "
                "inverse you must pick one side and stay there — A = IA with "
                "row operations only, or A = AI with column operations only.",
                "Getting the 3×3 characteristic-equation coefficients wrong. "
                "It is λ³ − S₁λ² + S₂λ − S₃ = 0 with S₁ = trace A, S₂ = the sum "
                "of the three principal 2×2 minors, S₃ = det A. Dropping S₂ or "
                "flipping the alternating signs is the usual failure.",
                "Getting A⁻¹ from Cayley–Hamilton when A is singular. That "
                "step divides by the constant term of the characteristic "
                "polynomial, which is (−1)ⁿ det A; if det A = 0 the inverse "
                "does not exist and the manipulation is invalid.",
                "Using a determinant to test linear dependence when the number "
                "of vectors is not their dimension. A determinant works only "
                "for n vectors in ℝⁿ; for any other count build the matrix and "
                "use rank — dependent exactly when rank < number of vectors.",
                "Treating an eigenvector as a unique answer, or assuming a "
                "repeated eigenvalue supplies as many independent eigenvectors "
                "as its algebraic multiplicity. (1, 1) and (−3, −3) are the "
                "same eigenvector, and a repeated eigenvalue may yield fewer.",
                "Stating λᵐ is an eigenvalue of Aᵐ without \"for every positive "
                "integer m\" (it fails at m = −1 on a singular matrix); "
                "(AB)⁻¹ = B⁻¹A⁻¹ without requiring A and B both square, of the "
                "same order and both non-singular; or the trace/determinant "
                "identity without \"counted with multiplicity, including "
                "complex eigenvalues\" — [[0, −1], [1, 0]] has trace 0 and "
                "determinant 1 and no real eigenvalue at all.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that make the student execute one clean "
                "differentiation step or recall one exact statement. On every "
                "theorem card demand the hypotheses in full: Rolle's theorem "
                "and the Mean Value Theorem each need continuity on the closed "
                "[a, b] AND differentiability on the open (a, b), with "
                "f(a) = f(b) for Rolle only; L'Hospital's rule needs a genuine "
                "0/0 or ∞/∞ form and a limit of f′/g′ that exists. Ask for a "
                "specific c on a specific interval, a specific nth derivative, "
                "or one numerical limit, so the answer is a short expression a "
                "marker can tick. Keep worked examples to two lines: "
                "low-degree polynomials, eˣ, sin(ax + b), xˣ, x = a cos³θ. Use "
                "cloze cards for the nth-derivative and Maclaurin formulas. "
                "Never ask the student to explain, discuss or prove at length, "
                "and never use partial derivatives, integrals or convergence "
                "tests."
            ),
            traps=(
                "Applying L'Hospital's rule to a limit that is not "
                "indeterminate (3/0, 0/5), or differentiating the whole "
                "quotient with the quotient rule instead of differentiating "
                "numerator and denominator separately.",
                "Attacking 0·∞, ∞ − ∞, 1^∞, 0⁰ or ∞⁰ with L'Hospital directly. "
                "They must first be turned into 0/0 or ∞/∞ — logarithms for "
                "the power forms, combining or reciprocating for the others. "
                "Also: if lim f′/g′ fails to exist, that says nothing about "
                "the original limit.",
                "Misquoting the mean-value hypotheses: continuity on the "
                "CLOSED [a, b], differentiability only on the OPEN (a, b), and "
                "f(a) = f(b) for Rolle. Reporting a c outside (a, b), or at an "
                "endpoint, does not verify the theorem.",
                "Computing the parametric second derivative as "
                "(d²y/dt²)/(d²x/dt²). It is d²y/dx² = [d/dt(dy/dx)]/(dx/dt), "
                "with dx/dt ≠ 0.",
                "In logarithmic differentiation, dropping the factor y when "
                "undoing the log: from (1/y)y′ = … the answer is y′ = y·(…) "
                "with y written back in terms of x. Related: differentiating "
                "xˣ as x·x^(x−1) or as xˣ ln x — neither the base nor the "
                "exponent is constant.",
                "Treating every stationary point as an extremum. f′(c) = 0 "
                "with f″(c) = 0 is inconclusive — x³ has an inflexion at 0, x⁴ "
                "a minimum — so the sign change of f′ or a higher derivative "
                "must be checked. On a closed [a, b] the endpoints must be "
                "checked too before naming an absolute maximum or minimum.",
                "Quoting the recurrence (1 − x²)y_(n+2) − (2n + 1)x·y_(n+1) − "
                "n²y_n = 0 with no function attached. It is a statement about "
                "particular y — it holds for y = sin⁻¹x, and for "
                "y = e^(a·sin⁻¹x) the n² becomes n² + a². Unattached, it is "
                "not true of anything.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour short, exactly-checkable cards: one integral with a "
                "closed-form answer, or one formula stated with its condition. "
                "The mid-term on this unit is MCQ-only, so prefer the stems "
                "that paper actually uses — which substitution, which "
                "decomposition, which property applies, evaluate — and keep "
                "every answer to a line a marker can verify. Choose integrals "
                "that resolve in one or two steps (2x cos x², x eˣ, "
                "dx/((x + 1)(x + 2)), ∫₀^(π/2) sin x/(sin x + cos x) dx) over "
                "long computations. Always attach the condition: the even/odd "
                "shortcut needs an interval symmetric about 0, King's rule "
                "uses f(a + b − x), the 0-to-2a rule needs f(2a − x) = f(x). "
                "Label ILATE a heuristic, never a law. Always write + C on an "
                "indefinite answer and never on a definite one. Never generate "
                "improper integrals, reduction formulae, multiple integrals or "
                "differential equations."
            ),
            traps=(
                "Mixing the two bookkeeping schemes in a definite "
                "substitution: evaluating a u-antiderivative at the old "
                "x-limits, or converting the limits to u and then "
                "back-substituting to x but still evaluating at the u-limits. "
                "The variable and the limits must match — either convert both "
                "and stop, or return to x and use the original limits.",
                "The 1/a coefficient. ∫dx/(a² + x²) = (1/a)tan⁻¹(x/a) + C does "
                "carry 1/a; ∫dx/√(a² − x²) = sin⁻¹(x/a) + C carries none. The "
                "1/a in ∫f(ax + b)dx exists only because the inner function is "
                "LINEAR — there is no 1/g′(x) shortcut for a general inner g.",
                "Misapplying symmetry. \"Odd, so it is zero\" needs an interval "
                "symmetric about 0. ∫₀^(2a) f = 2∫₀^a f needs f(2a − x) = f(x), "
                "which is not the same as f being even; when f(2a − x) = −f(x) "
                "the integral is 0 instead. King's rule on a general interval "
                "is f(a + b − x), not f(a − x). And ∫₀^(na) f = n∫₀^a f for a "
                "function of period a holds for positive integer n only.",
                "Partial fractions: not dividing first when the fraction is "
                "improper; writing only B/(x − a)² for a repeated factor "
                "instead of A/(x − a) + B/(x − a)²; a bare constant instead of "
                "(Ax + B) over an irreducible quadratic; and \"factoring\" a "
                "quadratic whose discriminant is negative.",
                "Integration by parts mechanics: dropping the minus sign, or "
                "using v instead of ∫v in the second term. Also treating ILATE "
                "as a theorem — it is a heuristic for choosing u and it does "
                "not decide every integral.",
                "Power-rule and log slips: applying x^(n+1)/(n + 1) at n = −1 "
                "instead of ln|x|; writing ln x without the modulus; omitting "
                "+ C on an indefinite integral while attaching it to a "
                "definite one; and integrating |x| or a piecewise integrand "
                "across its kink without splitting the interval there.",
                "Justifying ∫tan x dx = −ln|cos x| + C as \"f′/f with "
                "f = cos x\". With f = cos x the integrand is −f′/f, hence the "
                "minus sign. The clean f′/f drill is ∫cot x dx = ln|sin x| + C.",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour one-step computational cards over proofs. For Euler's "
                "theorem always name the function explicitly and make the "
                "student check homogeneity and its degree first; when u is an "
                "inverse-trig or log wrapper the answer is n·F(u)/F′(u), never "
                "n·u — write cards that punish that confusion. For the "
                "two-variable second-derivative test require both "
                "D = f_xx·f_yy − (f_xy)² and the sign of f_xx in the answer, "
                "and include at least one saddle case and one D = 0 case so "
                "\"saddle\" and \"inconclusive\" both get drilled — at the "
                "origin x⁴ + y⁴ has D = 0 and a minimum, −(x⁴ + y⁴) has D = 0 "
                "and a maximum, and x³ + y³ has D = 0 and neither, which is "
                "the whole point of the word inconclusive. The second "
                "class test on this course targets real-time applications of "
                "this unit, so make roughly half the cards word problems: "
                "percentage-error propagation through a total differential, a "
                "rate-of-change chain-rule problem with given dr/dt and dh/dt, "
                "and a constrained geometric optimisation solved by "
                "F = f + λg. Demand numeric answers with units and signs. "
                "Never generate Jacobians, two-variable Taylor series, or any "
                "vector calculus."
            ),
            traps=(
                "Applying Euler's theorem to a function that is not "
                "homogeneous. For u = tan⁻¹((x³ + y³)/(x − y)) or "
                "u = log((x² + y²)/(x + y)) it is tan u and e^u that are "
                "homogeneous, not u, so the answer is n·F(u)/F′(u) — sin 2u "
                "and 1 respectively — never n·u.",
                "Getting the degree wrong: for a quotient the degree "
                "subtracts. Adding a non-zero constant to, or taking a log or "
                "inverse-trig of, a function homogeneous of degree n ≠ 0 "
                "destroys homogeneity — which is exactly why the extended form "
                "of the theorem exists.",
                "Second-derivative-test misuse: quoting D > 0 without the sign "
                "of f_xx, so maximum and minimum swap; calling D < 0 "
                "\"inconclusive\" when it is a definite saddle point; and "
                "treating D = 0 as an extremum when the test genuinely says "
                "nothing.",
                "Confusing the total derivative with the partial: when "
                "u = f(x, y) and y itself depends on x, "
                "du/dx = ∂u/∂x + (∂u/∂y)(dy/dx). Reporting ∂u/∂x alone drops "
                "the second term.",
                "Declaring a two-variable limit to exist after testing y = 0, "
                "x = 0, or only straight lines y = mx. Agreement along every "
                "straight line still proves nothing — y = mx² can break it. "
                "Existence needs the same value along every path.",
                "Assuming f_x and f_y existing at a point implies continuity "
                "or differentiability there (false), or that f_xy = f_yx "
                "unconditionally (the mixed partials must exist nearby and be "
                "continuous at the point). The same continuity hypothesis is "
                "needed by the second-order Euler corollary "
                "x²f_xx + 2xy·f_xy + y²f_yy = n(n − 1)f, and the extended form "
                "additionally needs F′(u) ≠ 0.",
                "Stating the error rule as an equality. The total differential "
                "gives a FIRST-ORDER APPROXIMATION for small errors: "
                "δu ≈ (∂u/∂x)δx + (∂u/∂y)δy. And on Lagrange problems: "
                "forgetting that g = 0 is itself one of the equations, and "
                "claiming the method proves a point is a maximum or a minimum "
                "— it only produces candidates.",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that make the student produce limits, not just "
                "an antiderivative. For change of order, give the original "
                "iterated integral and ask for the reversed limits explicitly, "
                "derived from the region rather than by swapping symbols, and "
                "say whether the reversed form is one integral or two. For "
                "polar, cylindrical and spherical work always require the "
                "element itself — r dr dθ, r dr dθ dz, r² sin θ dr dθ dφ — "
                "together with the correct θ and φ ranges, and state the angle "
                "convention you are using. For a change of variables, say "
                "which direction of the Jacobian is used and keep it inside an "
                "absolute value. Keep answers short and closed-form: a number, "
                "a standard formula, or a single reversed iterated integral. "
                "Prefer textbook regions — triangles, paired parabolas, discs, "
                "cardioids, tetrahedra, spheres, ellipsoids. Never ask about "
                "line integrals, surface integrals, or Green's, Stokes' or the "
                "divergence theorem."
            ),
            traps=(
                "Reversing the order by mechanically swapping the limit "
                "expressions instead of re-deriving them from the region: "
                "turning \"y from x² to x, x from 0 to 1\" into \"x from y² to "
                "y\" rather than the correct \"x from y to √y, y from 0 to 1\".",
                "Dropping the area or volume element: writing dx dy = dr dθ "
                "instead of r dr dθ, or dV = dr dθ dφ instead of "
                "r² sin θ dr dθ dφ.",
                "Using the Jacobian in the wrong direction or without the "
                "modulus: rewriting an integral in u, v needs "
                "|∂(x, y)/∂(u, v)|, which is 1/|∂(u, v)/∂(x, y)| — not the "
                "signed determinant, and not the reciprocal one.",
                "Leaving ANY variable in the outer limits — most often the one "
                "just integrated away. After the inner integration the outer "
                "limits must be pure constants, and the value of a definite "
                "double or triple integral must contain no x, y or z.",
                "Failing to split, or failing to merge, the region: a region "
                "needing two integrals in one order often needs one in the "
                "other. The triangle (0, 0), (2, 0), (1, 1) is two integrals "
                "as dy dx but the single \"x from y to 2 − y, y from 0 to 1\" "
                "as dx dy.",
                "Spherical-coordinate angle confusion: putting the sine of the "
                "azimuthal angle in the element, or letting the polar angle "
                "run 0 to 2π. With x = r sin θ cos φ, θ runs 0 to π and φ runs "
                "0 to 2π — and θ means something different here than it does "
                "in plane polars, so any card using both must say which.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that make the student produce a specific "
                "coefficient, a specific series, or a specific number — never "
                "a vague \"explain Fourier series\". Always state the interval "
                "explicitly in the question, because the interval fixes the "
                "factor: 1/L on any full interval of length 2L, and 2/L only "
                "for even/odd or half-range work, where the integral runs over "
                "half the range. Fix one convention — a₀/2 + Σ(aₙ cos + bₙ "
                "sin) — and never write a bare a₀ as the constant term. Ask "
                "which coefficients vanish and why, and never allow an "
                "even/odd shortcut on an interval that is not symmetric about "
                "the origin. Include cards that deduce π²/6, π²/8 or π/4 and "
                "that name the substitution point. Test the jump rule as the "
                "mean ½[f(a⁻) + f(a⁺)]. Cloze Dirichlet's conditions as "
                "sufficient, never necessary. Keep answers to one or two "
                "lines. Never introduce Fourier transforms, Parseval's "
                "identity, or the complex-exponential form."
            ),
            traps=(
                "Mixing the two a₀ conventions: writing the series as "
                "a₀/2 + Σ(…) and then quoting a₀ = (1/2L)∫, which is the mean "
                "value. Keep one: a₀ = (1/L)∫ over one period of length 2L, "
                "and the constant term of the series is a₀/2. A card that "
                "reports \"a₀ = …\" where the source said \"a₀/2 = …\" has "
                "silently halved the answer.",
                "Using the wrong Euler factor after a change of interval — "
                "carrying 1/π (or 2/L) onto an interval of length 2L. On any "
                "full interval of length 2L the factor is 1/L; 2/L belongs "
                "only to the even/odd and half-range formulas.",
                "Applying the even/odd shortcut on an interval not symmetric "
                "about the origin. f(x) = x² on (0, 2π) is not an "
                "even-function problem and its bₙ is generally non-zero. The "
                "shortcut is valid only on (−L, L) or (−π, π).",
                "Integrating a piecewise f with a single formula across the "
                "whole period instead of splitting at every breakpoint — the "
                "commonest source of a wrong aₙ or bₙ on discontinuous "
                "problems.",
                "Substituting a jump point x = a into the series and equating "
                "it to f(a) when deducing a numerical sum. The series "
                "converges to ½[f(a⁻) + f(a⁺)] there; substitute a point of "
                "continuity, or use the mean deliberately. Whether an endpoint "
                "counts as continuous depends on the PERIODIC EXTENSION: "
                "x = π is a point of continuity for x² on (−π, π) but a jump "
                "for x on (−π, π).",
                "Sign and limit slips in repeated integration by parts: "
                "dropping the alternating sign, and mis-evaluating "
                "cos nπ = (−1)ⁿ, sin nπ = 0, cos 2nπ = 1 at the limits.",
            ),
        ),
    ),
    "CSE111": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that separate the three translators and the "
                "three language levels by one exact property. Good shapes: "
                "which translator turns assembly into machine code; what a "
                "compiler produces before execution; why an interpreted "
                "script prints four lines and then stops at an error; which "
                "stage reports “undefined reference to calculateTotal”; what "
                "pass 1 of a two-pass assembler builds; what a disassembler "
                "cannot recover. Ask for the fixed order of a toolchain — "
                "preprocessing, compilation, assembly, linking, loading — and "
                "the artefact chain source code → object code → executable → "
                "loaded process. Name the program-development-cycle phase "
                "from a one-line scenario (algorithm design, integration "
                "testing, debugging, maintenance). Quote mnemonics such as "
                "`ADD R1, R2` and directives such as `.data` exactly as "
                "typed. Skip “what is a computer language”."
            ),
            traps=(
                "A card claiming an interpreted program produces no output "
                "when it hits an error. An interpreter executes statements "
                "one at a time, so everything before the bad statement has "
                "already run and its effects persist; only a compiler reports "
                "errors before any execution.",
                "A card asserting that one assembly statement always becomes "
                "exactly one machine instruction. Macros and "
                "pseudo-instructions can expand to several instructions or to "
                "none, so the mapping is close but not guaranteed one-to-one.",
                "A card treating “undefined reference to <name>” as a "
                "compiler or syntax error. Compilation of that translation "
                "unit succeeded; the missing symbol is found by the linker, "
                "so it is a link-time error.",
                "A card saying the compiler produces the executable directly. "
                "The compiler emits object code, the linker combines object "
                "files into an executable, and the loader places it in memory "
                "and prepares the process — three distinct steps.",
                "A card claiming high-level source is fully portable, or that "
                "compiled machine code is. Machine code is tied to one "
                "instruction set; source may compile on two implementations "
                "yet still behave differently where it relies on "
                "implementation-defined details.",
                "A card claiming a disassembler recovers the original "
                "program. It recovers instructions, but comments, macro "
                "structure and most original symbol names are gone — they "
                "were never in the executable.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that pin a generation to its switching "
                "technology, a characteristic to its one-line definition, and "
                "a functional unit to the one job only it does. Good shapes: "
                "which component defines the third generation; which "
                "characteristic “works for hours without tiring” names "
                "(diligence, not speed); which unit compares two values "
                "against which one sequences the operation; the fixed data "
                "flow input → memory → ALU → memory → output; the instruction "
                "cycle fetch → decode → fetch operand → execute → store. Ask "
                "what makes code firmware rather than application software, "
                "the boot order firmware → bootloader → kernel → "
                "applications, what the stored-program idea actually changed, "
                "and how much a byte-addressable machine with a 24-bit "
                "address bus can address (2²⁴ bytes = 16 MiB). Prefer a "
                "scenario that must be classified — embedded, hybrid, "
                "mainframe, server — over “define a computer”."
            ),
            traps=(
                "A card defining accuracy as “always gives correct results”. "
                "Accuracy means correct results when the data and the "
                "instructions are correct; wrong input still yields wrong "
                "output, and a fixed-width overflow still corrupts a correct "
                "program.",
                "A card swapping the characteristics. Diligence is working "
                "without fatigue or loss of concentration, versatility is "
                "handling different kinds of task, speed is throughput, and "
                "storage is retention — a card using one name for another's "
                "definition is wrong.",
                "Generation-to-technology mismatch. First generation vacuum "
                "tubes, second transistors, third integrated circuits, fourth "
                "microprocessors. A card placing ICs in the second "
                "generation, or transistors in the third, is wrong.",
                "A card that reports 2ⁿ address-bus capacity in the wrong "
                "unit convention. 2²⁴ bytes is 16 777 216 bytes = 16 MiB; "
                "writing it as 16 MB is acceptable only under the 1024-based "
                "convention, and a card must not mix that with the 1000-based "
                "storage-marketing convention.",
                "A card giving the CPU the whole DMA transfer. The CPU "
                "initialises the transfer and is then free; the DMA "
                "controller moves the block and signals completion.",
                "A card saying the MMU or the CPU services a page fault. The "
                "MMU detects that a valid virtual page has no physical "
                "mapping and raises the fault; the operating system is what "
                "loads the page and updates the tables.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "This unit is more computational than it looks — weight it "
                "toward small exact calculations and toward single-property "
                "distinctions. Good shapes: CPU time = instruction count × "
                "CPI × clock cycle time, so which of two processors finishes "
                "first given clock and CPI; maximum speedup on N cores with "
                "serial fraction s, 1/(s + (1 − s)/N); the offset and index "
                "bits of a direct-mapped cache from its capacity and block "
                "size; average memory access time = hit time + miss rate × "
                "miss penalty; addressable space from an n-bit byte address "
                "bus; write amplification = flash writes / host writes. "
                "Alongside those, ask what makes a workload suit a GPU rather "
                "than a CPU, why RAM loses its contents and ROM does not, "
                "where cache sits in the hierarchy, and what a clock speed "
                "alone does not tell you."
            ),
            traps=(
                "A card treating a higher clock speed as proof of higher "
                "performance. CPU time = instruction count × CPI × clock "
                "cycle time, so a slower clock with a lower CPI can win, and "
                "clock comparisons across different instruction sets prove "
                "nothing.",
                "Cache-bit arithmetic. For a direct-mapped cache, offset bits "
                "= log₂(block size in bytes) and index bits = log₂(capacity ÷ "
                "block size). A card computing index bits from the capacity "
                "without dividing by the block size, or reusing the offset "
                "width as the index width, is wrong.",
                "A card calling CPU cache non-volatile, or placing it in "
                "secondary storage. Cache is volatile SRAM inside or beside "
                "the processor, smaller and faster than main memory, and it "
                "loses its contents at power-off exactly as RAM does.",
                "Amdahl's law stated as 1/s or as N/(1 + s). The maximum "
                "speedup on N processors with serial fraction s is 1/(s + (1 "
                "− s)/N); 1/s is only the limit as N grows without bound, not "
                "the answer for a specific core count.",
                "Byte-unit convention mixed within one card. 1 KB = 1000 "
                "bytes and 1 KiB = 1024 bytes; drive and network capacities "
                "are quoted in the 1000-based units while memory sizes and "
                "OS-reported figures are usually 1024-based. A card "
                "converting an advertised drive size with 1024³, or a memory "
                "size with 10⁹, without saying which convention it uses, is "
                "wrong.",
                "A card claiming SECDED corrects two-bit errors. "
                "Single-error-correcting, double-error-detecting code "
                "corrects one bit error in a protected word and only detects "
                "a two-bit error.",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "This is the unit with real working, so make most cards a "
                "conversion carried out on one specific number, with the "
                "arithmetic shown. Good shapes: positional expansion (2AF₁₆ = "
                "2×16² + 10×16 + 15 = 687₁₀); repeated division with the "
                "remainders read bottom-up (725₁₀ = 1325₈); repeated "
                "multiplication by the base for fractions (0.625₁₀ = 0.101₂); "
                "direct grouping — three bits per octal digit, four per "
                "hexadecimal digit, grouped outward from the binary point; "
                "addition and subtraction inside a base, and mixed-base sums "
                "taken through decimal; the largest unsigned n-bit value 2ⁿ − "
                "1; the fewest bits that hold a given integer; which digits "
                "are legal in a base; solving (132)ᵦ = 42₁₀ for the base b. "
                "One number in, one exact answer out — never a method "
                "described in prose."
            ),
            traps=(
                "Remainder order in repeated division. Dividing by the base "
                "produces the least significant digit first, so the answer is "
                "the remainders read in reverse order of production. A card "
                "listing them in the order they came out has the digits "
                "backwards.",
                "Grouping direction and padding. Binary is grouped in threes "
                "(octal) or fours (hexadecimal) starting at the binary point "
                "and working outward — right-to-left across the integer part, "
                "left-to-right across the fraction — padding with zeros at "
                "the far end of each side. A card that groups or pads the "
                "fractional part from the right is wrong.",
                "Illegal digits. Binary admits only 0 and 1, octal only 0–7, "
                "hexadecimal 0–9 and A–F where A = 10 and F = 15. A card "
                "presenting 2080₂, 1928₈ or the digit G in hexadecimal as a "
                "valid numeral, or giving A the value 11, is wrong.",
                "Unsigned range off-by-one. n bits hold 0 to 2ⁿ − 1, so 10 "
                "bits reach 1023 and not 1024; and the minimum bits needed "
                "for an integer N is the smallest n with 2ⁿ > N — 1000 needs "
                "10 bits because 9 bits stop at 511. A card answering 2ⁿ, or "
                "reasoning 2ⁿ ≥ N, is wrong.",
                "Signed off-by-one, if a card ventures into two's complement "
                "(which is outside what this unit teaches, but which a writer "
                "may reach for). n bits cover −2ⁿ⁻¹ to 2ⁿ⁻¹ − 1 — an "
                "asymmetric range with one more negative value than positive. "
                "A card giving the maximum as 2ⁿ⁻¹, or the minimum as −2ⁿ⁻¹ + "
                "1, is wrong.",
                "Fraction termination. A decimal fraction has a finite binary "
                "(and hexadecimal) form only when its lowest-terms "
                "denominator is a power of 2: 0.375 = 0.011₂ terminates, "
                "while 0.1₁₀, 0.2₁₀ and 0.3₁₀ repeat forever. A card printing "
                "an exact finite binary expansion for 0.1₁₀ or 0.2₁₀ is "
                "wrong.",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Keep every claim true of real git, and quote commands "
                "exactly as they would be typed. This paper drills the "
                "beginner path, so favour: which command does one specific "
                "thing — `git init`, `git status`, `git add notes.txt`, `git "
                "commit -m \"Add notes\"`, `git log`, `git switch -c feature`, "
                "`git merge feature`, `git push -u origin feature`, `git "
                "clone <url>`; what the `.git` directory is; what “untracked” "
                "means; and above all the index — stage a file, edit it "
                "again, and the commit records the staged version. Then ask "
                "the lookalike pairs by their single difference: `git rm "
                "--cached` versus deleting the file, `git restore --staged` "
                "versus discarding changes, fetch versus pull, merge versus "
                "rebase, reset versus revert. Prefer a one-line situation "
                "whose answer is one command."
            ),
            traps=(
                "Staging semantics. `git commit` records what was in the "
                "index at the last `git add` for that file, and includes "
                "nothing from files that are modified but unstaged. A card "
                "saying a plain commit sweeps up every modified file, or that "
                "it commits the newest working-tree version of a file edited "
                "after staging, is wrong.",
                "`.gitignore` against an already-tracked file. Ignore rules "
                "apply to untracked files, so listing a tracked file in "
                "`.gitignore` does not stop git reporting its changes; `git "
                "rm --cached <file>` followed by a commit is what untracks it "
                "while leaving the working copy on disk.",
                "reset versus revert. `git revert` adds a new commit that "
                "undoes an earlier one and leaves history intact, which is "
                "why it is the safe choice on published commits. `git reset` "
                "moves the branch pointer: `--soft` leaves the changes "
                "staged, `--mixed` (the default) unstages them but keeps the "
                "working tree, `--hard` discards working-tree changes. A card "
                "that has revert deleting a commit, or reset creating one, or "
                "`--soft` discarding work, is wrong.",
                "fetch versus pull. `git fetch` updates remote-tracking "
                "references only and touches neither the current branch nor "
                "the working tree; `git pull` is a fetch followed by a merge, "
                "or a rebase where configured. A card claiming fetch updates "
                "the working copy, or that pull only downloads, is wrong.",
                "History rewriting. `git merge` keeps both lines of history "
                "and normally creates a merge commit; `git rebase` replays "
                "commits onto a new base, producing new commit objects with "
                "new hashes, which is why it must not be used on commits "
                "others have already pulled. `git commit --amend` likewise "
                "replaces the commit with a new object and a new hash. A card "
                "claiming rebase or amend preserves the original hashes, or "
                "that a detached HEAD is an error rather than HEAD pointing "
                "straight at a commit instead of at a branch, is wrong.",
                "Git versus GitHub, and fork versus branch. The full history "
                "is local, so `git init`, `git add`, `git commit`, `git log`, "
                "branching and merging all work with no network; GitHub hosts "
                "a copy and adds forks, pull requests and issues. A fork is a "
                "server-side copy of a whole repository under another "
                "account; a branch is a movable reference inside one "
                "repository. A card presenting `git fork` as a command, or "
                "claiming a commit needs an internet connection, is wrong.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Aim at facts that will still be true a year from now. Good "
                "shapes: what a token is (a sub-word chunk produced by a "
                "tokeniser, not a word); what changes during training and "
                "what does not change during inference; what a parameter "
                "count does and does not indicate; the one difference between "
                "generative and discriminative behaviour; supervised, "
                "unsupervised and reinforcement learning named from a "
                "one-line scenario; what few-shot prompting adds over "
                "zero-shot; what grounding an answer in supplied documents "
                "means and why it leaves the weights untouched; what a "
                "hallucinated citation is; why accuracy alone is a poor "
                "metric on an imbalanced spam set; the four things that make "
                "a prompt specific — audience, task, output format, length. "
                "Ask which category of tool fits a task, never a version "
                "number, a release date, a price or a benchmark score."
            ),
            traps=(
                "Training versus inference. Training adjusts the model's "
                "parameters from data; inference runs a fixed set of "
                "parameters on new input and changes none of them. A card "
                "claiming a deployed model learns from each conversation by "
                "default, or that chatting with it updates its weights, is "
                "wrong.",
                "Tokens. A token is a sub-word unit produced by a tokeniser, "
                "so a token count is neither a word count nor a character "
                "count, and the same text tokenises differently under "
                "different tokenisers. A card equating one token with one "
                "word, or with one character, is wrong.",
                "Parameter count. It measures model size and nothing else. A "
                "card presenting a larger parameter count as evidence of "
                "higher accuracy, more recent knowledge, better reasoning or "
                "fewer hallucinations is wrong.",
                "Retrieval and grounding. Supplying documents at query time "
                "places them in the model's context for that request; it does "
                "not retrain the model, does not permanently add the facts, "
                "and the facts are gone from the next unrelated request. A "
                "card saying retrieval “trains”, “fine-tunes” or “updates” "
                "the model is wrong.",
                "Perishable specifics. Any card carrying a model version "
                "number, a parameter count for a named product, a "
                "context-window size, a release date, a price, a benchmark "
                "score, or a “best” / “most advanced” ranking will be false "
                "within months and should be rejected even when it is "
                "accurate today.",
                "Hallucination and evaluation. Hallucination is fluent, "
                "confident output that is fabricated or unsupported — "
                "typically a reference that does not resolve — not a grammar "
                "mistake and not a refusal. Separately, on an imbalanced set "
                "a classifier that labels everything “not spam” can score "
                "high accuracy while its recall on spam is near zero; a card "
                "offering accuracy alone as proof of a good classifier is "
                "wrong.",
            ),
        ),
    ),
    "INT335": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Build every card on a named framework with a fixed count and "
                "a fixed order. Ask for the five d.school modes in sequence — "
                "Empathize, Define, Ideate, Prototype, Test — one mode per "
                "card, plus 'which mode comes after X' and 'which mode does "
                "this activity belong to'. Ask what each of the four VARK "
                "letters stands for. Ask for the three criteria a workable "
                "concept must balance (desirability, feasibility, viability) "
                "and which one a described failure breaks. Use "
                "single-contrast cards for creativity vs invention vs "
                "innovation, focused vs diffuse mode, and functional "
                "fixedness. Attach names to claims: Simon on design, Rittel "
                "on wicked problems, IDEO, Stanford d.school. Cloze suits "
                "stage lists and letter expansions. Keep answers to the bare "
                "term or the ordered list — no sentences."
            ),
            traps=(
                "The d.school model has exactly five modes, named Empathize, "
                "Define, Ideate, Prototype, Test, in that order. Reject any "
                "card that adds a sixth (Assess, Implement, Understand, "
                "Observe), drops one, or places Ideate before Define.",
                "IDEO's three phases exist in two different official versions "
                "and a card must not blur them: Inspiration / Ideation / "
                "Implementation (IDEO.org Field Guide) and Hear / Create / "
                "Deliver (earlier HCD Toolkit). The LPU unit notes teach "
                "Hear, Create, Deliver while the LPU MCQ bank uses "
                "Inspiration, Ideation, Implementation — a card asserting one "
                "as 'the' IDEO model without qualification is unsafe.",
                "Invention and innovation are not interchangeable. A card "
                "that calls a novel but never-adopted device an 'innovation', "
                "or that requires new technology for something to count as an "
                "innovation, is wrong: innovation is implementation that "
                "produces value, and can use existing technology (e.g. a new "
                "delivery or financing model).",
                "VARK expands to Visual, Aural (auditory), Read/write, "
                "Kinesthetic. Reject A = 'Analytical', R = 'Reflective' or "
                "'Rational', K = 'Knowledge'. Also reject any card asserting "
                "that matching instruction to a learner's VARK preference "
                "improves achievement — the evidence does not establish that; "
                "VARK justifies varied representation only.",
                "Focused and diffuse modes must not be inverted. Focused = "
                "deliberate concentration on a known approach, used for "
                "verification and precise work; diffuse = relaxed, broad, "
                "background association, used for novel connections. A card "
                "saying diffuse mode is best for checking a specification, or "
                "that focused mode generates original combinations, is "
                "reversed.",
                "Design thinking is iterative, not one-pass. Reject cards "
                "stating the five modes must be completed once in strict "
                "sequence, or that testing never sends a team back to "
                "Empathize/Define.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Make the tools distinguishable, not merely defined. Ask what "
                "each AEIOU letter stands for, and which AEIOU category a "
                "specific field note belongs to. Ask for the four empathy-map "
                "quadrants (Says, Thinks, Does, Feels) and where one given "
                "piece of evidence goes — a quotation, an observed action, an "
                "inferred worry. Ask what a persona contains that an empathy "
                "map does not. Ask which of a stated pair is qualitative and "
                "which quantitative, and which one a given finding is. Ask "
                "for the point-of-view template '[user] needs a way to [need] "
                "because [insight]'. Ask explicit vs implicit vs latent need "
                "for a described behaviour, and whether a given interview "
                "question is open, leading, or behaviour-anchored. Answers: "
                "one term or one short template."
            ),
            traps=(
                "AEIOU expands to Activities, Environments, Interactions, "
                "Objects, Users — five categories. Reject A = 'Attitudes', E "
                "= 'Emotions' or 'Experiences', I = 'Insights', O = "
                "'Observations', U = 'Understanding', and reject any card "
                "giving four or six categories.",
                "Empathy map, persona and journey map are three different "
                "artefacts. A card must not say an empathy map covers a "
                "sequence of stages over time (that is a journey map), or "
                "that a persona records what one specific interviewee said (a "
                "persona is a synthesised behavioural archetype). The "
                "LPU-taught empathy map has four quadrants "
                "Says/Thinks/Does/Feels; the original XPLANE/Dave Gray "
                "version has six sections (Think & Feel, Hear, See, Say & Do, "
                "Pain, Gain) — a card citing a count must say which version.",
                "Says vs Does vs Thinks must be assigned by evidence type: a "
                "direct quotation goes under Says, an observed action under "
                "Does, a cautiously inferred concern under Thinks. A card "
                "filing an observed behaviour under Says, or an inference "
                "under Does, is wrong.",
                "A problem statement is not a solution statement. Reject any "
                "'user need' phrased as a feature — 'needs a green "
                "confirmation button', 'needs a one-click export' — instead "
                "of the outcome ('needs to confirm the payment succeeded'). "
                "An explicit request stated as a solution is a known "
                "distractor, not the need.",
                "Qualitative and quantitative must not be swapped. "
                "Qualitative = descriptive, why, interviews and observation; "
                "quantitative = counted, how many, percentages and task "
                "times. A card calling '70% completed the task' a qualitative "
                "finding, or an interview transcript a quantitative one, is "
                "wrong.",
                "Explicit = stated by the user; implicit = inferred from "
                "behaviour, contradiction or workaround; latent = not "
                "recognised by the user until a new possibility exists. A "
                "card labelling a directly voiced request as an implicit "
                "need, or an inference as explicit, is wrong.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "This unit is counting, ordering and classifying — write for "
                "that. Ask which of divergent and convergent thinking a named "
                "activity belongs to, and which comes first in a cycle. Ask "
                "what each SCAMPER letter stands for, and which single "
                "SCAMPER operation a described product change uses. Ask for "
                "Osborn's four brainstorming rules one rule per card. Ask for "
                "the four Double Diamond phases in order (Discover, Define, "
                "Develop, Deliver) and which two are divergent. Ask what goes "
                "in the rows and what in the columns of an idea screening "
                "matrix, and set short weighted-score arithmetic using Total "
                "= Σ(wᵢ × rᵢ) with real numbers worked out in detail. Ask "
                "which quadrant of an impact–effort matrix is done first. Ask "
                "feasibility vs relevance for a described idea."
            ),
            traps=(
                "SCAMPER expands to Substitute, Combine, Adapt, Modify (also "
                "given as Magnify/Minify), Put to another use, Eliminate, "
                "Reverse (also given as Rearrange) — seven letters. Reject S "
                "= 'Simplify', C = 'Create', A = 'Add', M = 'Multiply', E = "
                "'Expand', R = 'Redesign' or 'Refine'. A card must not "
                "present 'Modify' and 'Magnify/Minify' or 'Reverse' and "
                "'Rearrange' as separate letters.",
                "The four Double Diamond phases are Discover, Define, "
                "Develop, Deliver (Design Council, 2004/2005). Discover and "
                "Develop are the divergent halves; Define and Deliver are "
                "convergent. Diamond 1 is the problem space, diamond 2 the "
                "solution space. Reject any card making Define divergent, "
                "Develop convergent, or renaming a phase 'Design', 'Decide' "
                "or 'Deploy'. Note this framework is NOT in the LPU INT335 "
                "unit notes or its question bank — include it only as the "
                "standard divergent/convergent model, never as 'the syllabus "
                "framework'.",
                "Divergent and convergent must not be inverted. Divergent = "
                "generate many options, defer judgment, seek quantity and "
                "variety; convergent = evaluate, narrow, select against "
                "criteria. A card calling ranking or feasibility screening "
                "'divergent', or idea generation 'convergent', is wrong. The "
                "normal order is diverge then converge.",
                "Osborn's four brainstorming rules are defer judgment (no "
                "criticism), strive for quantity, welcome wild ideas, and "
                "combine/build on others' ideas. 'One conversation at a "
                "time', 'be visual' and 'stay on topic' come from the "
                "d.school's seven rules, not Osborn's four — a card "
                "attributing them to Osborn, or giving a count other than "
                "four for Osborn, is wrong.",
                "Weighted screening-matrix arithmetic must actually be "
                "correct: check every total against Σ(wᵢ × rᵢ) digit by "
                "digit. A widely circulating LPU-style item asks for 0.5 × 8 "
                "+ 0.3 × 4 + 0.2 × 6 and gives 6.2; the correct value is 6.4. "
                "Also, in the standard layout ideas are the rows and criteria "
                "are the columns — reject a card that swaps them.",
                "Feasibility and relevance are different tests: feasibility "
                "asks whether the idea can be delivered with available "
                "technology, time and money; relevance asks whether it "
                "addresses the defined user problem. A card calling a cheap, "
                "buildable idea for a problem nobody has 'highly relevant', "
                "or a validated need with unavailable technology 'infeasible "
                "therefore irrelevant', confuses the two. A mandatory "
                "constraint such as safety is a gate, not a weighted "
                "criterion.",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Aim at purpose and choice, not description. Ask which "
                "prototype fidelity suits a stated uncertainty — layout and "
                "navigation versus timing, colour, trust and micro-feedback — "
                "and what question each fidelity answers. Ask what a "
                "prototype is for in one phrase (learning, exposing "
                "weakness), and what an MVP is in one phrase and what it is "
                "not. Ask the one-line difference between an MVP and a "
                "prototype, and between a concierge MVP and a Wizard of Oz "
                "prototype. Ask what a wireframe shows and what it "
                "deliberately omits. Ask what a storyboard shows that a "
                "wireframe does not. Ask what the MoSCoW letters stand for. "
                "Ask for the ordered happy path of a named flow. Keep answers "
                "to a term, a pair, or a short ordered list."
            ),
            traps=(
                "A prototype's purpose is to learn and to expose where an "
                "idea is weak, not to prove a chosen solution is correct or "
                "to demonstrate a finished build. Reject any card whose "
                "answer makes the prototype's goal 'to show the final "
                "product', 'to confirm the design works', or 'to impress "
                "stakeholders'.",
                "An MVP is the smallest coherent end-to-end product that "
                "reliably delivers the core value and generates evidence "
                "about one central hypothesis — not simply 'the version with "
                "the fewest features' and not 'a cheap or half-working "
                "product'. 'Viable' means it must work well enough for a real "
                "user to complete the core task. Reject cards defining MVP by "
                "feature count alone or permitting unusable quality.",
                "MVP and prototype must stay distinct: a prototype produces "
                "learning through simulation and is not given to real "
                "customers in a real operating context; an MVP is used by "
                "real customers to deliver real value. A card saying an MVP "
                "is 'a type of prototype' without this distinction, or that a "
                "prototype is released to the market, is wrong.",
                "Fidelity choice must match the uncertainty. Low fidelity "
                "(sketches, paper screens, grayscale wireframes) tests "
                "concept, information hierarchy and screen sequence and "
                "cannot test animation, response time, visual appeal or "
                "realistic data entry. High fidelity tests precise "
                "interaction, timing, visual credibility and accessibility. "
                "Reject a card recommending low fidelity to test whether "
                "users trust a visual identity, or high fidelity to compare "
                "three navigation structures before visual design exists.",
                "Wizard of Oz means the user believes the system is automated "
                "while a human is producing the responses behind the scenes; "
                "a concierge MVP means the service is openly delivered by "
                "hand. A card that swaps these, or that describes a human "
                "secretly driving responses as 'high-fidelity prototyping', "
                "is wrong. Note: Wizard of Oz is described but not named in "
                "the LPU INT335 material, so a card must define it, not "
                "assume the label.",
                "A wireframe communicates layout, content placement, "
                "hierarchy and interface structure — it deliberately omits "
                "final colour, typography and imagery, and is conventionally "
                "grayscale. Reject cards saying a wireframe shows the final "
                "visual design or brand styling, or that a storyboard is a "
                "set of screens (a storyboard shows the user's context, "
                "action, system response and outcome over time).",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Drill the distinctions and the fixed lists. Ask for the four "
                "Feedback Capture Matrix quadrants (Likes, Criticisms, "
                "Questions, Ideas) and which quadrant a given note belongs "
                "in. Ask the one-line difference between usability and "
                "customer experience, and which of the two a described "
                "complaint is about. Ask what a touchpoint is versus a pain "
                "point, and direct versus indirect touchpoints. Ask which "
                "layer of a journey map a given entry belongs to (actions, "
                "thoughts, emotions, channels, opportunities). Ask whether a "
                "given facilitator sentence is neutral or leading, and "
                "rewrite-shaped cards asking which task wording tests "
                "discoverability rather than obedience. Ask what 'Show, don't "
                "tell' means in one phrase. Ask one accessibility rule per "
                "card. Keep answers to a term or a short phrase."
            ),
            traps=(
                "The Feedback Capture Matrix (d.school feedback capture grid) "
                "has exactly four quadrants: Likes, Criticisms, Questions, "
                "Ideas. Reject 'Observations', 'Pros/Cons', "
                "'Strengths/Weaknesses' or a five-column 'issue / evidence / "
                "frequency / severity / follow-up' table presented as the "
                "matrix's quadrants — that last one is a prioritisation "
                "table, and the LPU MCQ bank is internally inconsistent on "
                "this point while its own unit notes give "
                "Likes/Criticisms/Questions/Ideas.",
                "Validation and verification are different: validation asks "
                "whether the design meets the real user need (building the "
                "right thing); verification asks whether it meets the "
                "specification (building the thing right). A card defining "
                "validation as conformance to requirements, or as checking "
                "that code runs correctly, is wrong.",
                "Usability is narrower than customer experience. Usability = "
                "effectiveness, efficiency and satisfaction of one product "
                "interaction; customer experience = the whole perception "
                "across advertising, purchase, delivery, support, refunds and "
                "communication. A card treating a usable interface as "
                "sufficient for good customer experience, or calling a "
                "delayed refund a 'usability problem', conflates them.",
                "Stated preference must not outrank observed behaviour. "
                "'Show, don't tell' means asking the participant to perform "
                "the task rather than say what they would do. Reject cards "
                "whose answer trusts a participant's claim ('I would use the "
                "filters') over the recorded behaviour, or that treat an "
                "opinion as evidence of discoverability.",
                "Neutral facilitation: a facilitator must not demonstrate the "
                "workflow, name the control, or embed a judgment. 'Find a way "
                "to pay the bill' is a valid task; 'Open Payments and select "
                "Bill Pay' tests obedience, and 'How useful was our "
                "convenient dashboard?' is leading. Reject a card presenting "
                "a step-by-step instruction or a positively loaded question "
                "as good testing practice.",
                "A touchpoint is any moment of contact between user and "
                "product/service/brand; a pain point is an obstacle that "
                "creates effort, delay, confusion or dissatisfaction at one. "
                "They are not synonyms, and journey-map stages are not a "
                "fixed canonical list — a card asserting 'the N stages of a "
                "customer journey map' as a memorised set is unsafe; the "
                "layers (actions, thoughts, emotions, channels, "
                "opportunities) are the stable part.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Anchor on NABC and on four terms students blur. Ask what "
                "each NABC letter stands for, in order, and which NABC "
                "element a given sentence from a pitch supplies — one letter "
                "per card. Ask the one-line difference between iteration, "
                "re-design, design refactoring and a strategic pivot, and ask "
                "which one a described change is. Ask what an elevator pitch "
                "must contain and roughly how long it runs. Ask for the "
                "ordered spine of a persuasive product presentation (problem, "
                "insight, solution, evidence, next step). Ask what a "
                "technical design case study documents that a demo does not — "
                "including rejected concepts and the evidence behind them. "
                "Ask one rule per card about attributing a measured effect "
                "when several changes were made at once. Answers: a term, a "
                "letter expansion, or a short ordered list."
            ),
            traps=(
                "NABC expands to Need, Approach, Benefits per costs, "
                "Competition — four elements, from SRI International. Reject "
                "B = 'Budget', 'Business model' or plain 'Benefits' without "
                "the per-costs sense, C = 'Cost', 'Customer' or 'Conclusion', "
                "A = 'Analysis' or 'Advantage', N = 'Novelty'. 'Why is this "
                "better than the alternatives?' is Competition, not Benefits.",
                "Refactoring, re-design and pivot are not the same. Design "
                "refactoring improves internal structure or consistency while "
                "preserving the design's purpose and behaviour; re-design "
                "changes the design of an existing product; a strategic pivot "
                "changes product direction — target user, problem, technology "
                "or delivery model. A card calling a navigation cleanup a "
                "'pivot', or a change of target market 'refactoring', is "
                "wrong.",
                "Iteration must be attributable. A card claiming an "
                "improvement is explained by a particular change, when "
                "several features changed between the two tests, states an "
                "unsupported conclusion — changing one variable at a time is "
                "the point.",
                "Severity is not the same as frequency. A card whose answer "
                "prioritises the most-requested feature over a rarer defect "
                "that blocks the core task, or that treats eight feature "
                "requests as outweighing two reports of critical errors, "
                "misapplies the prioritisation rule.",
                "A presentation claim needs evidence tied to the stated "
                "success criteria. Reject cards that treat a polished "
                "high-fidelity prototype, a positive audience reaction, or "
                "metrics unrelated to the original criteria as validation of "
                "a project.",
                "An elevator pitch is a short (roughly 30–60 second) "
                "statement of the user problem, the solution and the primary "
                "benefit — not a feature list, not a technical architecture "
                "summary, and not a demonstration. Reject a card whose 'best "
                "pitch' opens with technology rather than the user problem or "
                "benefit.",
            ),
        ),
    ),
    "CSE326": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask which element or attribute is correct for a stated job, "
                "and what a given snippet actually produces. Use shapes like "
                "'Which element marks up X?', 'What does this markup "
                "render?', 'A page omits <!DOCTYPE html> — what changes?', "
                "and 'From /docs/page.html, what does href=\"../img/a.png\" "
                "resolve to?'. Drill void elements (<br>, <img>, <hr>, "
                "<meta>, <link>, <input>), boolean attributes where presence "
                "alone means true, what belongs in <head> versus <body>, "
                "<meta charset=\"utf-8\">, semantic <strong>/<em> against "
                "presentational <b>/<i>, lists (<ul>, <ol start reversed>, "
                "<dl>/<dt>/<dd>), <a target=\"_blank\" rel=\"noopener "
                "noreferrer\">, <img src alt loading=\"lazy\"> and srcset, "
                "<audio>/<video> attributes controls, muted, autoplay, "
                "poster, <iframe>, inline SVG, and how <title> and the meta "
                "description feed SEO. Cloze cards suit exact attribute "
                "names. Never ask what an acronym stands for."
            ),
            traps=(
                "A card calling HTML a programming language, or claiming HTML "
                "tag and attribute names are case-sensitive. They are not; "
                "only certain attribute values, such as id and class, are.",
                "A card claiming a void element (<br>, <img>, <hr>, <meta>, "
                "<link>, <input>) requires a closing tag, or that the "
                "trailing slash in <br /> is required in HTML5. It is "
                "optional and has no effect on parsing.",
                "A card claiming disabled=\"false\", checked=\"false\" or "
                "required=\"no\" turns a feature off. For a boolean attribute "
                "the presence of the attribute is true regardless of its "
                "value; only removing the attribute disables it.",
                "A card saying <b> and <i> were removed or are invalid in "
                "HTML5. They remain valid with redefined semantics. The "
                "genuinely obsolete elements are <center>, <font>, <big>, "
                "<strike>, <marquee> and <frame>/<frameset>.",
                "A card claiming title can substitute for alt, or that every "
                "image must carry descriptive alt text. For a purely "
                "decorative image the correct value is alt=\"\", and omitting "
                "alt entirely is different from alt=\"\".",
                "A card that resolves ../ or a root-relative /path wrongly, "
                "or that says the fragment in page.html#top is sent to the "
                "server. Fragments are handled by the browser and never "
                "appear in the HTTP request target.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask which semantic element or form attribute the described "
                "situation requires, and what a given form actually submits. "
                "Use shapes like 'Which element for a self-contained blog "
                "post?', 'Given this markup, which name/value pairs are "
                "sent?', and 'How is this <label> tied to its input?'. Drill "
                "<article> versus <section> versus <aside> versus <div>, only "
                "one non-hidden <main>, <label for> matching an id, the form "
                "attribute on a control placed outside its <form>, name as "
                "the key that is submitted, method=\"get\" against "
                "method=\"post\" and enctype=\"multipart/form-data\" for <input "
                "type=\"file\">, input types (email, url, number, range, date, "
                "checkbox, radio), the constraint attributes required, "
                "pattern, min, max, step, minlength, readonly against "
                "disabled, and table markup <caption>, <thead>, <th scope>, "
                "colspan, rowspan, headers. One fact per card."
            ),
            traps=(
                "A card claiming a disabled control's value is submitted, or "
                "that a readonly control's value is not. Disabled controls "
                "are excluded from submission; readonly controls are "
                "submitted normally. Also watch for a card claiming a "
                "readonly control is still constraint-validated: readonly "
                "(like disabled) bars the element from constraint validation, "
                "so required and pattern on a readonly input never block "
                "submission.",
                "A card presenting placeholder as a replacement for <label>, "
                "or claiming placeholder text supplies an accessible name. It "
                "disappears on input and is not a label.",
                "A card saying an unchecked checkbox or radio is submitted as "
                "\"off\", \"false\" or an empty value. Unchecked controls are "
                "omitted from the submission entirely, and a checked box with "
                "no value attribute submits \"on\".",
                "A card describing a file upload without both method=\"post\" "
                "and enctype=\"multipart/form-data\", or claiming a GET form "
                "can carry file contents.",
                "A card writing pattern with regex delimiters, such as "
                "pattern=\"/^[0-9]+$/\", or claiming a substring match "
                "satisfies it. The pattern must match the entire value. Also "
                "watch for step being measured from zero when the step base "
                "is min.",
                "A card saying <section> is a generic container equivalent to "
                "<div>, that <header>, <footer> or <nav> may appear only once "
                "per page, or that client-side constraint validation is a "
                "security control rather than a usability one.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Make these cards computational and adversarial. Best shapes: "
                "'Two rules target the same element — which declaration "
                "wins?', 'What is the specificity of this selector?' answered "
                "as an (id, class, type) triple, 'With box-sizing: "
                "content-box, width: 200px, padding: 10px and a 5px border, "
                "what is the border-box width?', and 'Which axis does "
                "justify-content control here?'. Cover the three ways of "
                "attaching CSS, selectors (type, class, id, descendant, A > "
                "B, A + B, attribute, :hover, :nth-child, ::before), the "
                "cascade resolved by importance and origin first, then "
                "specificity, then source order, the box model and margin "
                "collapsing, position static/relative/absolute/fixed/sticky "
                "and what each offsets against, flexbox against grid, "
                "px/%/em/rem/vw/vh arithmetic, media queries, transitions, "
                "and var(--x, fallback)."
            ),
            traps=(
                "A card treating specificity as a single base-10 number, so "
                "that eleven class selectors outrank one id selector. The "
                "components are compared left to right and never carry. Also "
                "watch for a nonzero contribution given to * or to :where().",
                "A card claiming a more specific normal declaration beats an "
                "author !important declaration, or that an ordinary inline "
                "style attribute outranks an author !important rule. It does "
                "not.",
                "A card that counts margin inside the border-box width, or "
                "that with box-sizing: border-box still adds padding and "
                "border on top of the declared width. Also a card resolving a "
                "percentage top or bottom padding against the container's "
                "height; percentage padding and margin resolve against the "
                "containing block's width.",
                "A card claiming adjacent vertical margins add together "
                "rather than collapsing to the larger value, that horizontal "
                "margins collapse (they never do), or that collapsing occurs "
                "between flex or grid items.",
                "A card assigning justify-content to the cross axis or "
                "align-items to the main axis, one that ignores "
                "flex-direction: column swapping which visual direction each "
                "affects, or one expanding flex: 1 to anything other than 1 1 "
                "0%.",
                "A card claiming position: absolute is positioned against the "
                "page or <body> rather than the nearest positioned ancestor, "
                "that z-index takes effect on an ordinary static block box "
                "(it is ignored there, though it does apply to flex and grid "
                "items even when they are position: static), or that "
                "text-align: center centers a block-level box (it aligns "
                "inline content; margin: 0 auto centers a block with a set "
                "width).",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask for the printed output of a short snippet or for the "
                "exact type of a value. Shapes: 'What does console.log(...) "
                "print?', 'What is typeof x here?', 'true or false, and "
                "why?'. Drill typeof results, == against === coercion (\"5\" == "
                "5, 0 == false, null == undefined, NaN), the falsy set false, "
                "0, \"\", null, undefined and NaN with \"0\", [] and {} truthy, "
                "\"5\" + 2 against \"5\" - 2, operator precedence, var/let/const "
                "scope and redeclaration plus the temporal dead zone, const "
                "objects still being mutable, string immutability and methods "
                "returning new strings, array methods that mutate (push, "
                "splice, sort, reverse) against ones returning new arrays "
                "(map, filter, slice, concat), default sort() ordering, and "
                "what this refers to in a method call, a plain call and an "
                "arrow function. Loops belong to Unit 5; leave them there."
            ),
            traps=(
                "A card giving typeof null as \"null\" (it is \"object\"), typeof "
                "NaN as anything but \"number\", or typeof [] as \"array\" (it is "
                "\"object\"; Array.isArray is the correct test).",
                "A card claiming NaN === NaN or NaN == NaN evaluates to true, "
                "or that === is how you test whether a value is NaN. "
                "Number.isNaN is the test.",
                "A card saying const makes an object or array immutable. Only "
                "the binding is fixed; properties and elements can still be "
                "changed. Also a card claiming let and const are not hoisted "
                "at all rather than being hoisted into the temporal dead "
                "zone.",
                "A card calling \"0\", \"false\", [] or {} falsy, or getting the "
                "standard loose comparisons wrong: \"5\" == 5 is true, 0 == "
                "false is true, \"\" == 0 is true, null == undefined is true, "
                "null == 0 is false, and [] == false is true even though [] "
                "is truthy.",
                "A card claiming map, filter, slice or concat mutate the "
                "original array, that push, splice, sort or reverse return a "
                "new array without mutating, that forEach returns an array, "
                "or that sort() orders numbers numerically by default (it "
                "compares their string forms unless given a comparator).",
                "A card asserting that a string method such as toUpperCase() "
                "changes the original string, that 0.1 + 0.2 === 0.3 is true, "
                "or that an arrow function has its own this or arguments.",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask what a DOM call returns, what order handlers fire in, "
                "and what a fetch actually gives back. Shapes: 'What does "
                "document.querySelectorAll(\"li\") return, and can .map() be "
                "called on it?', 'In what order do these capture and bubble "
                "listeners log?', 'What does fetch(url) resolve to when the "
                "server answers 404?'. Cover getElementById, querySelector "
                "and querySelectorAll, a live HTMLCollection against a static "
                "NodeList, textContent against innerHTML, classList, "
                "createElement and append, addEventListener with capture, "
                "once and signal, event.target against event.currentTarget, "
                "preventDefault against stopPropagation, delegation with "
                "closest(), fetch resolving to a Response where response.ok "
                "must be checked and response.json() is a second promise, "
                "JSON.parse and JSON.stringify, localStorage against "
                "sessionStorage, for, while and do...while, "
                "map/filter/reduce, regex test(), and Date's zero-indexed "
                "months."
            ),
            traps=(
                "A card claiming the promise from fetch() rejects on a 404 or "
                "500. It resolves; response.ok or response.status must be "
                "checked. Rejection is for network-level failures. Also a "
                "card treating response.json() as returning the parsed object "
                "directly rather than another promise.",
                "A card saying querySelectorAll returns an array (it returns "
                "a static NodeList, so .map needs Array.from or a spread), "
                "that getElementsByClassName is static (it is live, which is "
                "why removing nodes in an index loop skips elements), or that "
                "getElementById returns a collection.",
                "A card claiming preventDefault() stops propagation, or that "
                "stopPropagation() cancels the browser's default action. The "
                "two are independent.",
                "A card claiming focus, blur, mouseenter, mouseleave or load "
                "bubble and can therefore be handled by delegation. The "
                "bubbling counterparts are focusin/focusout and "
                "mouseover/mouseout.",
                "A card claiming localStorage stores objects or numbers as-is "
                "(every value is a string, so JSON.stringify is required), "
                "that it is sent to the server with each request (cookies "
                "are, web storage is not), that it expires on its own, or "
                "that sessionStorage is shared between tabs.",
                "A card treating Date months as one-indexed (new Date(2026, "
                "0, 1) is 1 January) or getDay() as 1 = Monday (0 = Sunday), "
                "or recommending innerHTML for untrusted text where "
                "textContent is the safe default.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Keep every card checkable; refuse anything shaped like "
                "'explain hosting'. Shapes: 'Which git command does X?', 'A "
                "deployed project site loads with no CSS — which path is "
                "wrong?', 'What does fetch do on a 500?', 'Which DevTools "
                "panel shows a request's status code?', 'Which error type "
                "does this snippet throw?'. Cover git init, status, add, "
                "commit -m, remote add origin, push -u origin main and "
                ".gitignore; GitHub Pages serving static files only with "
                "index.html as the entry file; the project-site URL "
                "https://user.github.io/repo/ against the user-site root and "
                "what that does to /style.css; the Elements, Console, Sources "
                "and Network panels; SyntaxError against ReferenceError "
                "against TypeError; syntax against runtime against logic "
                "errors; try/catch/finally; .catch() and Promise.allSettled; "
                "checking response.ok; common status codes; CORS preflight; "
                "and LCP, INP and CLS."
            ),
            traps=(
                "A card claiming GitHub Pages can run PHP, Node, Python or a "
                "database, or process a form submission server-side. It "
                "serves static files only.",
                "A card saying a root-absolute path such as /style.css "
                "resolves inside https://user.github.io/repo/. On a project "
                "site it resolves at the account root, which is the standard "
                "cause of a page that works locally but deploys unstyled; "
                "relative paths or a configured base path are the fix.",
                "A card claiming a synchronous try...catch catches an error "
                "thrown later inside a setTimeout callback or an unawaited "
                "promise rejection, or that finally is skipped when the try "
                "block returns or throws. finally runs either way.",
                "A card attaching the wrong meaning to 200, 301, 302, 304, "
                "400, 401, 403, 404 or 500, or claiming a 304 response "
                "carries a body. A 304 tells the client its cached copy is "
                "still valid.",
                "A card telling the client to send "
                "Access-Control-Allow-Origin as a request header, or claiming "
                "mode: \"no-cors\" lets JavaScript read the response body. CORS "
                "headers come from the server's response. Also watch for a "
                "wrong account of what is preflighted: only GET, HEAD and "
                "POST carrying just CORS-safelisted headers are simple, so a "
                "preflight OPTIONS is triggered by any other method, by a "
                "custom request header, and by a Content-Type outside "
                "application/x-www-form-urlencoded, multipart/form-data and "
                "text/plain — which is why a POST of JSON is preflighted.",
                "A card whose answer is generic advice — 'follow best "
                "practices', 'explain hosting', 'Copilot generates correct "
                "code' — instead of a checkable fact such as what a specific "
                "git command does, what a named DevTools panel shows, or "
                "which error type a given snippet throws.",
            ),
        ),
    ),
    "INT108": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Assume Python 3 and say so wherever a version matters. "
                "Favour one-line evaluation cards: give an expression and ask "
                "for its value, or ask for the result of type(...). Drill "
                "10/3 against 10//3 against 10%3, the fact that / always "
                "yields a float, ** being right-associative, unary minus "
                "against **, and mixed int/float promotion. Ask which "
                "exception a bad conversion raises and what input() returns. "
                "Use cloze cards for operator precedence order, the reserved "
                "keywords, and the identifier rules. Quote code exactly as "
                "typed, with real quotes and underscores. Keep every answer "
                "to one value, one type name, or one exception name. Never "
                "ask for Python's history, its features, or a comparison of "
                "IDEs."
            ),
            traps=(
                "Python 2 semantics presented as current. In Python 3: 10/3 "
                "is 3.3333333333333335 and 10/2 is 5.0 (a float, not 5); "
                "print is a function and needs parentheses; input() replaces "
                "raw_input(); raw_input and xrange do not exist. A card "
                "claiming / truncates integers, or writing print 'x', is "
                "describing Python 2.",
                "Claiming input() returns a number. input() always returns a "
                "str in Python 3, so x = input() followed by x + 1 raises "
                "TypeError; int(input()) is required. Related: int('3.5') "
                "raises ValueError (only int('3') works), while int(3.99) is "
                "3 because int() truncates toward zero rather than rounding.",
                "Getting floor division or modulo wrong on negatives. // "
                "floors toward −∞, so -7//2 is -4 (not -3) and 7//-2 is -4. "
                "The remainder takes the sign of the divisor: -7 % 2 is 1 and "
                "7 % -2 is -1.",
                "Precedence errors on **. It is right-associative, so 2**3**2 "
                "is 512, not 64. Unary minus binds more loosely than **, so "
                "-2**2 is -4, not 4. Also (2+3)*4 is 20 while 2+3*4 is 14.",
                "Asserting exact float equality. 0.1 + 0.2 is "
                "0.30000000000000004, so 0.1 + 0.2 == 0.3 is False. Any card "
                "presenting that comparison as True, or printing 0.1 + 0.2 as "
                "0.3, is wrong.",
                "Misstating round() or bool(). round() rounds halves to even: "
                "round(0.5) is 0, round(1.5) is 2, round(2.5) is 2 — not 1 "
                "and 3. And bool is a subclass of int, so True + True is 2 "
                "and isinstance(True, int) is True; every non-empty string is "
                "truthy, so bool('False') and bool('0') are both True.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour a 3 to 6 line snippet in the question and ask for the "
                "exact output, the number of times a line runs, or the final "
                "value of one variable. Keep loops to at most six iterations "
                "so the trace is checkable. Drill range boundaries with real "
                "arguments: list(range(1, 10, 2)), an empty range, a negative "
                "step. Ask what break, continue and pass each do, and when "
                "the else attached to a for or a while actually runs. Ask "
                "what and and or return, not just whether a condition is "
                "true. Use if/elif/else chains where only one branch may "
                "fire. Write the indentation exactly, since it defines the "
                "block. Never ask a student to describe the syntax of a loop "
                "in words."
            ),
            traps=(
                "range boundary errors. range(a, b) stops before b, so "
                "range(5) is 0,1,2,3,4 and list(range(1, 10, 2)) is [1, 3, 5, "
                "7, 9]. range(5, 0) with the default step +1 is empty — "
                "counting down needs range(5, 0, -1). range() takes ints "
                "only: range(1.5) raises TypeError.",
                "Inverting loop-else. The else attached to a for or a while "
                "runs when the loop finishes WITHOUT executing break — so a "
                "loop that never breaks does run its else. A card saying else "
                "runs only when the loop breaks, or only when the body never "
                "executed, has it backwards.",
                "Confusing break, continue and pass. break leaves only the "
                "innermost enclosing loop, not all of them. continue jumps to "
                "the next iteration, so in a while loop any increment written "
                "after continue is skipped and the loop never terminates. "
                "pass does nothing whatsoever — it is a placeholder, not a "
                "skip.",
                "Claiming and/or evaluate to True or False. They return one "
                "of their operands: 3 and 5 is 5, 0 or 'a' is 'a', '' or 0 is "
                "0. Short-circuiting means the right operand may never be "
                "evaluated at all.",
                "Mutating a list while iterating over it, and reporting the "
                "naive answer. The iterator advances by index, so elements "
                "get skipped: L = [1, 2, 2, 3, 4] with for x in L: if x % 2 "
                "== 0: L.remove(x) leaves [1, 2, 3] — one 2 survives — not "
                "[1, 3].",
                "Scope claims about the loop variable. After for i in "
                "range(3): pass the name i still exists and equals 2. A "
                "comprehension's variable does NOT leak: [q for q in "
                "range(3)] leaves q undefined. Also = is assignment and == is "
                "comparison; if x = 5 is a SyntaxError, not a true condition.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Put a literal in the question and ask for the printed "
                "result. Drill slicing with real values — s[1:4], s[::-1], "
                "s[-2:], an out-of-range slice — and ask which of str, list, "
                "tuple and dict is mutable. Show two names bound to one list "
                "and ask what the first prints after the second is changed. "
                "Ask what a method RETURNS as well as what it does, since "
                "sort(), append() and reverse() return None while sorted() "
                "returns a list. Ask which exception a bad index or a missing "
                "dict key raises. Use cloze cards for the one-element tuple "
                "comma, for {} being a dict, and for dict keys having to be "
                "hashable. Never ask a student to list every string method."
            ),
            traps=(
                "Conflating index and slice bounds. 'python'[10] raises "
                "IndexError, but the out-of-range SLICE 'python'[10:20] "
                "quietly returns '' — it does not raise. 'python'[::-1] is "
                "'nohtyp' and 'python'[1:4] is 'yth'.",
                "Getting immutability the wrong way round. s[0] = 'x' on a "
                "str raises TypeError and t[0] = 5 on a tuple raises "
                "TypeError; string methods return NEW strings, so "
                "'ab'.replace('a', 'z') leaves the original 'ab' untouched. "
                "But a tuple's immutability is shallow: t = (1, [2]) then "
                "t[1].append(3) succeeds and t becomes (1, [2, 3]).",
                "Treating an in-place method as returning the result. "
                "list.sort(), .append(), .reverse(), .extend() and .clear() "
                "all return None, so x = [3, 1].sort() makes x None. "
                "sorted([3, 1, 2]) returns [1, 2, 3] and leaves the original "
                "alone.",
                "Ignoring aliasing and shallow copy. b = a binds a second "
                "name to the SAME list, so b.append(4) changes a. b = a[:] "
                "(or list(a), or copy.copy(a)) copies one level only, so "
                "nested lists stay shared. [[0]*3]*3 makes three references "
                "to ONE row: setting x[0][0] = 1 gives [[1, 0, 0], [1, 0, 0], "
                "[1, 0, 0]]. Also a += [3] mutates the list in place so an "
                "alias sees it, while a = a + [3] rebinds to a new list and "
                "the alias does not.",
                "Missing the tuple comma or the empty-set literal. (5) is "
                "just the int 5; a one-element tuple is (5,). {} is an empty "
                "DICT — an empty set is written set().",
                "Dictionary claims. d['z'] on a missing key raises KeyError "
                "while d.get('z') returns None. Keys must be hashable, so "
                "{[1]: 2} raises TypeError. A duplicate key keeps the LAST "
                "value: {'a': 1, 'a': 2} is {'a': 2}, and 1, 1.0 and True are "
                "the same key. Since Python 3.7 a dict preserves INSERTION "
                "order — it is not sorted, so list({'b':1,'a':2,'c':3}) is "
                "['b', 'a', 'c']. Finally, 'x' in d tests keys, never values.",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Define a short function in the question and ask what a "
                "specific call returns or what a sequence of calls prints. "
                "Drill default arguments by asking for the result of three "
                "consecutive calls. Ask what a function with no return "
                "statement gives back. Show a mutable and an immutable "
                "argument passed to the same function and ask which of the "
                "caller's variables changed. Ask which exception a scope "
                "mistake raises. On recursion, ask for the value of a small "
                "call traced by hand (factorial or Fibonacci with n ≤ 7), for "
                "the base case that stops it, or for the number of calls made "
                "— never for a definition of recursion. Name the default "
                "recursion limit as a number. Quote def lines, indentation "
                "and parameter lists exactly as typed."
            ),
            traps=(
                "Claiming a default argument is re-created on every call. It "
                "is evaluated ONCE, at def time. With def f(a, L=[]): "
                "L.append(a); return L, the calls f(1), f(2), f(3) return "
                "[1], then [1, 2], then [1, 2, 3] — the same list object, "
                "never resetting to []. An immutable default such as n=0 "
                "shows no such effect.",
                "Assuming a function returns something it does not. A "
                "function with no return statement, or a bare return, gives "
                "None. print() itself returns None, so x = print('hi') sets x "
                "to None while still printing hi.",
                "Getting argument passing backwards. Rebinding a parameter "
                "inside the function never touches the caller's variable, but "
                "mutating a mutable argument does: after def g(x, lst): x = "
                "99; lst.append(99) called with an int 1 and a list [1], the "
                "caller still has 1 and now has [1, 99].",
                "Naming the wrong exception for a scope error. Assigning to a "
                "name anywhere inside a function makes it local for the WHOLE "
                "function, so reading it before that assignment raises "
                "UnboundLocalError — not NameError, and it does not fall back "
                "to the global value. Rebinding an outer name needs global or "
                "nonlocal; reading one does not.",
                "Parameter-order and packing errors. A parameter without a "
                "default may not follow one that has a default — def d(a=1, "
                "b): is a SyntaxError. Extra positional arguments collect "
                "into *args as a TUPLE and extra keyword arguments into "
                "**kwargs as a DICT: with def kw(a, b=2, *args, **kwargs), "
                "the call kw(1, 2, 3, 4, x=5) gives a=1, b=2, args=(3, 4), "
                "kwargs={'x': 5}.",
                "Wrong recursion facts. Missing base case raises "
                "RecursionError at the default limit, which "
                "sys.getrecursionlimit() reports as 1000 — it is not an "
                "infinite hang and not a segfault. Fibonacci defined as "
                "fib(0)=0, fib(1)=1 gives 0, 1, 1, 2, 3, 5, 8, so fib(6) is "
                "8, and factorial(5) is 120. Separately, closures capture the "
                "VARIABLE not its value: [lambda: i for i in range(3)] called "
                "back gives [2, 2, 2], not [0, 1, 2].",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Write a class of five or six lines in the question and ask "
                "what a specific print statement outputs, or which exception "
                "a call raises. Contrast a class attribute with an instance "
                "attribute by creating two objects and changing one. Ask what "
                "self is and what happens when it is left out of a method "
                "signature. On inheritance, ask which version of an "
                "overridden method runs, and what a child forgetting "
                "super().__init__() loses. Ask for the difference between "
                "isinstance(obj, Parent) and type(obj) == Parent by giving "
                "both and asking for each value. Use cloze cards for the "
                "vocabulary the paper actually names — class, object, "
                "instance, attribute, method, constructor, inheritance, "
                "overriding, encapsulation, polymorphism. Keep answers to a "
                "single value, a class name, or one exception name."
            ),
            traps=(
                "Confusing class and instance attributes. A class attribute "
                "is shared by all instances. Assigning through an instance "
                "(a.count = 5) creates a NEW instance attribute and leaves "
                "the class attribute alone, so another instance still sees "
                "the old value. But MUTATING a shared mutable class attribute "
                "(self.items.append(1) where items = [] sits in the class "
                "body) is visible from every instance.",
                "Dropping self. self is an explicit first parameter of every "
                "instance method; a method written def m(): and called as "
                "obj.m() raises TypeError because the instance is still "
                "passed. self is a naming convention, not a keyword, but "
                "omitting the parameter is an error.",
                "Assuming a parent's __init__ runs automatically. If the "
                "child defines its own __init__ and never calls "
                "super().__init__() (or Parent.__init__(self)), the parent's "
                "attributes are never created and reading one raises "
                "AttributeError.",
                "Claiming two objects with the same attribute values are "
                "equal. Without a defined __eq__, == falls back to identity, "
                "so Eq(1) == Eq(1) is False. Likewise print(obj) shows "
                "<__main__.Class object at 0x...> unless __str__ or __repr__ "
                "is defined.",
                "Mixing up isinstance and type. For a child instance, "
                "isinstance(obj, Parent) is True but type(obj) == Parent is "
                "False, because type() reports the exact class and ignores "
                "inheritance.",
                "Overstating privacy. A leading double underscore is name "
                "mangling, not access control: __x inside class Priv becomes "
                "_Priv__x, so obj.__x raises AttributeError from outside but "
                "obj._Priv__x returns the value. A single leading underscore "
                "is only a convention and is not mangled. Also, an overriding "
                "method in the child always wins for a child instance, and "
                "for class W(Y, Z) the MRO is W, Y, Z, then the common base, "
                "then object — left to right.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask which exception a named line raises, in what order a "
                "try/except/else/finally block prints its parts, what a file "
                "contains after a given mode, and what a regex call returns. "
                "Pair each operation with its exception by name. Give the "
                "file's contents in the question, then ask what read(), "
                "readline() or readlines() returns, including the trailing "
                "newline characters. Drill the file modes 'r', 'w', 'a' on a "
                "file that does and does not exist. On regular expressions "
                "ask for the value of a concrete call — re.match, re.search, "
                "re.findall, re.sub, re.split — on a short string, quoting "
                "the raw-string pattern exactly as typed. Ask what greedy "
                "versus lazy quantifiers match on the same string. Never ask "
                "for a general account of error handling."
            ),
            traps=(
                "Pairing an operation with the wrong exception. 1/0 raises "
                "ZeroDivisionError; int('abc') raises ValueError; 'a' + 1 "
                "raises TypeError; [1, 2][5] raises IndexError; {'a': 1}['z'] "
                "raises KeyError; opening a missing file for reading raises "
                "FileNotFoundError; using an undefined name raises NameError; "
                "calling a missing attribute raises AttributeError.",
                "Getting else and finally wrong. else runs only when NO "
                "exception was raised; finally runs either way, and it runs "
                "even when the try block executes a return. A return placed "
                "inside finally REPLACES the value the try was going to "
                "return.",
                "Ignoring except-clause order. The first matching clause "
                "wins, so except Exception: written above except "
                "ZeroDivisionError: swallows everything and the specific "
                "handler is unreachable — Python raises no warning. The "
                "specific exception must be listed first.",
                "File-mode errors. 'w' TRUNCATES an existing file to empty on "
                "open (and creates it if absent); 'a' appends and never "
                "truncates; 'r' on a missing file raises FileNotFoundError. "
                "f.write() accepts a str only, so f.write(42) raises "
                "TypeError, and it returns the number of characters written "
                "(3 for 'abc'), not None. with open(...) as f: closes the "
                "file automatically, so no explicit close() is needed.",
                "Misdescribing the read methods. read() returns the whole "
                "file as ONE string; readline() returns one line INCLUDING "
                "its trailing '\\n'; readlines() returns a list of lines, each "
                "keeping its '\\n' EXCEPT the last one when the file does not "
                "end in a newline — on a file holding 'one\\ntwo\\nthree' "
                "readlines() is ['one\\n', 'two\\n', 'three']. After a read() "
                "the cursor sits at end of file, so a following readline() "
                "returns '' — not the first line again.",
                "Regex errors. re.match() anchors at the START, so "
                "re.match('b', 'abc') is None while re.search('b', 'abc') "
                "finds it. Both return None on failure — not '' — so calling "
                ".group() on a failed match raises AttributeError. re.findall "
                "returns whole matches only when the pattern has no groups; "
                "with one group it returns that group's text and with several "
                "it returns tuples, so re.findall('a(b)', 'abab') is ['b', "
                "'b']. Quantifiers are greedy by default: on 'aXbYb', a.*b "
                "matches 'aXbYb' while a.*?b matches 'aXb'. And . does not "
                "match '\\n' unless re.DOTALL is passed.",
            ),
        ),
    ),
    "MEC103": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Treat this unit as the subject's store of conventions and "
                "numbers, because none of its constructions can be performed "
                "on a card. Favour: the mm size of a named A-series sheet; "
                "the order of pencil grades and the grades used for technical "
                "drawing; which line type carries a given job (visible "
                "outline, hidden edge, centre line, cutting plane, hatching); "
                "the height-to-width ratios of single-stroke vertical Gothic "
                "lettering; aligned versus unidirectional dimensioning and "
                "the numbered dimensioning rules; the Ø and R prefixes; "
                "one-step RF and length-of-scale calculations that carry "
                "their own numbers; how many decimal places a plain and a "
                "diagonal scale each read to; and eccentricity values and "
                "cutting planes for the conics. Ask 'What are the dimensions "
                "of an A3 sheet in mm?' or 'If 1 m is represented by 2.5 cm, "
                "what is the RF?'. Never ask the student to construct, letter "
                "or draw anything."
            ),
            traps=(
                "A-series sheet sizes must be exactly A0 841 × 1189 mm, A1 "
                "594 × 841, A2 420 × 594, A3 297 × 420, A4 210 × 297 (all "
                "mm), each obtained by halving the next larger size across "
                "its longer side. Pencil grades run 9H (hardest) through H, "
                "F, HB, B to 7B (softest), with H, 2H and HB recommended for "
                "technical drawing. Reject transposed or invented sheet "
                "figures, and reject any card making 9H the softest, 7B the "
                "hardest, extending the range to 9B, or calling HB harder "
                "than H.",
                "Line-type assignments must not be swapped: visible outlines "
                "are continuous thick; hidden edges are dashed (short "
                "dashes), never a chain line; centre lines, lines of symmetry "
                "and pitch circles are long-dash dotted (chain) thin; the "
                "cutting-plane line is chain thin with thick ends; hatching "
                "and dimension, extension and leader lines are continuous "
                "thin. Reject 'hatching is drawn with thick lines' and reject "
                "a hidden edge shown as a chain line.",
                "Aligned and unidirectional dimensioning must not be "
                "interchanged: aligned places the figure above and parallel "
                "to the dimension line so it reads from the bottom or the "
                "right-hand side; unidirectional places every figure to read "
                "from the bottom edge only, inserted by breaking the "
                "dimension line, and the two systems are never mixed on one "
                "drawing. Chain (continuous) dimensioning is "
                "arrowhead-to-arrowhead in series; parallel (progressive) "
                "dimensioning takes every dimension from one common reference "
                "line. Ø prefixes a diameter and R a radius. Reject swapped "
                "definitions of any of these pairs.",
                "Reject any card stating that the unit (mm) is written after "
                "each dimension — the rule is that the unit is stated once in "
                "a note below the drawing — and reject cards allowing two "
                "dimension lines between the same pair of extension lines, "
                "crossing dimension lines, or repeated (redundant) "
                "dimensions. Single-stroke vertical Gothic lettering has "
                "uniform stroke thickness; the height-to-width ratio is 7:5 "
                "for all letters except I, J, L, M and W, 7:4 for all "
                "numerals except 1, 7:1 for I, 7:3 for the numeral 1, 7:4 for "
                "L and J, 7:6 for M and 7:8 for W. Reject any other ratio and "
                "reject 'Gothic lettering uses thick and thin strokes'.",
                "RF is a pure ratio and both lengths must be converted to the "
                "same unit before dividing — reject any RF carrying a unit or "
                "dividing unlike units, e.g. '2.5 cm / 1 m = 2.5' instead of "
                "2.5 cm / 100 cm = 1/40. Length of scale is RF × the maximum "
                "length the scale must measure (1/40 × 6 m = 1/40 × 600 cm = "
                "15 cm), not RF × the object's actual length. A plain scale "
                "shows two units and reads to one decimal place; a diagonal "
                "scale shows three units and reads to two, and rests on "
                "similar triangles. A reducing scale has RF < 1 and an "
                "enlarging scale RF > 1; full scale is 1:1. Reject any swap "
                "and reject '1:2 means twice actual size'.",
                "Eccentricity values must be exact: circle e = 0, ellipse e < "
                "1, parabola e = 1, hyperbola e > 1, e being the distance "
                "from the focus divided by the distance from the directrix. "
                "Cone-section origins must match: a plane parallel to the "
                "base gives a circle; a plane inclined to the axis cutting "
                "all generators gives an ellipse; a plane parallel to one "
                "generator gives a parabola; a plane making a smaller angle "
                "with the axis than the generator does gives a hyperbola; a "
                "plane through the apex gives a triangle. For an ellipse the "
                "SUM of the distances from the two foci is constant and equal "
                "to the major axis; the constant difference belongs to the "
                "hyperbola. The normal to an involute of a circle is tangent "
                "to the base circle, and the base length of an involute of a "
                "circle of diameter d is πd; one arc of a cycloid has base "
                "length πd and height d, the diameter, with its normal "
                "passing through the instantaneous point of contact of the "
                "rolling circle and the directing line. An epicycloid is "
                "traced by a point on a circle rolling OUTSIDE a directing "
                "circle and a hypocycloid INSIDE. Reject any swap of these, "
                "any inverted eccentricity ratio, 'equal to the minor axis', "
                "2πd, πr, and a height given as the radius.",
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Ask when a view is true, never how to draw it, and pitch "
                "these at mid-term standard since this unit is examinable "
                "there. Favour: where a point's front and top views sit for "
                "each position relative to the HP and VP, including a point "
                "lying in either plane; the condition for true length, so a "
                "line parallel to the HP is true length in the top view and "
                "one parallel to the VP in the front view; what a line "
                "perpendicular to a plane projects as on that plane; that a "
                "line inclined to both shows true length in neither view and "
                "that both apparent inclinations exceed the true ones; the "
                "definitions of horizontal and vertical trace and when a line "
                "has none; and that a plane shows true shape only when "
                "parallel to a plane of projection. Keep every answer to one "
                "condition or one term."
            ),
            traps=(
                "For a point in the first quadrant the front view lies above "
                "XY by its height above the HP and the top view lies below XY "
                "by its distance in front of the VP. A point lying IN the HP "
                "has its front view ON XY; a point lying IN the VP has its "
                "top view ON XY. Reject cards that swap which view falls on "
                "XY, and reject a first-quadrant point whose top view is "
                "placed above XY.",
                "A line shows true length only in the view on the plane it is "
                "parallel to: parallel to the HP gives a true-length top "
                "view, parallel to the VP a true-length front view, parallel "
                "to both gives true length in both views. Reject any card "
                "claiming true length in a view for a line inclined to that "
                "plane.",
                "A line perpendicular to a plane projects as a POINT on that "
                "plane and as a true-length line perpendicular to XY on the "
                "other plane. Reject cards that make a perpendicular line "
                "project as a line on the plane it is perpendicular to.",
                "For a line inclined to both planes, both views are shorter "
                "than the true length, the apparent inclinations α and β are "
                "each GREATER than the true inclinations θ and φ, and θ + φ "
                "can never exceed 90°. Reject 'the apparent angle is smaller' "
                "and reject any pair of true inclinations summing above 90°.",
                "The horizontal trace is where the line, produced if "
                "necessary, meets the HP, and the vertical trace where it "
                "meets the VP; a line parallel to the HP has no HT and a line "
                "parallel to the VP has no VT; a line parallel to both has "
                "neither. Reject swapped definitions and reject 'a line "
                "parallel to the HP has no VT'.",
                "A plane appears as a straight line (edge view) in the view "
                "on the plane it is perpendicular to, and shows true shape "
                "only in a view on a plane it is parallel to; a plane "
                "inclined to both shows true shape in neither view. Reject 'a "
                "plane perpendicular to the HP shows true shape in the top "
                "view' and reject any card promising true shape for a plane "
                "inclined to the plane of projection.",
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "This unit carries the single highest-value distinction in "
                "the subject and it sits in the mid-term, so drill first- "
                "versus third-angle projection from several directions rather "
                "than once. Favour view placement: in first angle the top "
                "view goes below the front view and the view from the left "
                "goes to its right; third angle is the mirror of all four. "
                "Ask it as a placement question, as a cloze on one view, and "
                "as 'Which angle of projection does India follow?'. Also ask "
                "what makes a projection orthographic, which plane carries "
                "the front, top and side view, the alternative names "
                "elevation, plan and end view, why the second and fourth "
                "quadrants are unused, and which view of a solid is drawn "
                "first for a given axis position. Never ask for a drawn view."
            ),
            traps=(
                "First-angle placement must be exact: top view BELOW the "
                "front view, bottom view above, the view from the left placed "
                "on the RIGHT and the view from the right on the LEFT. Third "
                "angle is the mirror of all four. Reject any card that gives "
                "first angle the third-angle arrangement or vice versa.",
                "India follows first-angle projection (BIS convention); the "
                "USA and Canada use third angle. Reject any card that assigns "
                "third angle to India or to BIS/IS practice. The projection "
                "symbol is a frustum of a cone shown in two views — reject "
                "any card that identifies the angle of projection by whether "
                "the larger or smaller circle is drawn on the left or the "
                "right, because sources disagree on that layout.",
                "In first angle the object lies between the observer and the "
                "plane of projection; in third angle the plane, assumed "
                "transparent, lies between the observer and the object. "
                "Reject the swap and reject 'the object is behind the plane "
                "in first angle'.",
                "The second and fourth quadrants are unused because on "
                "rotating the horizontal plane into the vertical plane the "
                "two views would overlap or coincide. Reject cards claiming "
                "they are unused because the object cannot be placed there, "
                "or that all four quadrants are in use.",
                "Orthographic projection has parallel projectors "
                "perpendicular to the plane of projection — reject "
                "descriptions of projectors converging at the observer's eye "
                "(perspective) or parallel but oblique to the plane (oblique "
                "projection). The front view is projected onto the vertical "
                "plane, the top view onto the horizontal plane and the side "
                "view onto the profile plane; elevation = front view, plan = "
                "top view, end view = side view. Reject swapped plane-to-view "
                "assignments.",
                "For a solid, the view on the plane the axis is perpendicular "
                "to is drawn FIRST: top view first when the axis is "
                "perpendicular to the HP (a solid resting on its base on the "
                "HP), front view first when the axis is perpendicular to the "
                "VP. Reject the reverse order. Solid nomenclature must also "
                "hold: a right regular prism has two identical polygonal ends "
                "and n rectangular faces, a pyramid has n triangular faces "
                "meeting at an apex, a tetrahedron has four equal equilateral "
                "triangular faces, and a hexagonal prism has 8 faces, 18 "
                "edges and 12 vertices. A frustum is what remains after a cut "
                "PARALLEL to the base; a truncated solid is cut by an "
                "inclined plane — reject that swap.",
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Aim at sectioning conventions and terminology; the sectioned "
                "views themselves cannot be produced on a card. Favour: what "
                "distinguishes a full, half, offset, revolved and removed "
                "section; that hatching is continuous thin at 45°, evenly "
                "spaced, and reversed or respaced for adjacent parts; which "
                "features stay unhatched when the cutting plane passes along "
                "their length; the cutting-plane line's own line type and "
                "what its arrows mean; which portion of the object is treated "
                "as removed; where the true shape of a section appears; and "
                "that hidden lines are normally omitted in a sectional view. "
                "Ask 'Which features are never hatched when the cutting plane "
                "passes along their length?' or 'At what angle are section "
                "lines normally drawn?'. Never ask the student to section a "
                "solid or to draw the resulting view."
            ),
            traps=(
                "Section (hatching) lines are continuous THIN, drawn at 45° "
                "to the principal outline and evenly spaced, with adjacent "
                "parts hatched in opposite directions or at different "
                "spacing; where a 45° line would run parallel to the outline, "
                "30° or 60° is used instead. Reject thick hatching, reject "
                "'adjacent parts are hatched identically', and reject any "
                "angle offered as the normal one other than 45°.",
                "Ribs, webs, spokes, shafts, bolts, nuts, screws, keys, pins "
                "and rivets are NOT hatched when the cutting plane passes "
                "ALONG their length; they are hatched normally when cut "
                "across. Reject 'webs are hatched in longitudinal section' "
                "and reject any card that lists a shaft or a bolt as hatched "
                "when sectioned lengthwise.",
                "A full section has the cutting plane pass right through the "
                "object; a half section removes one QUARTER of a symmetrical "
                "object so half appears in section and half in outside view, "
                "the two halves separated by a centre line, not a solid line; "
                "an offset section uses a stepped cutting plane to catch "
                "features not in one straight line; a revolved section is "
                "drawn in place on the view; a removed section is drawn away "
                "from it. Reject 'a half section removes half the object' and "
                "reject any swap among these five.",
                "The cutting-plane line is a long-dash dotted (chain) thin "
                "line made thick at its ends and at every change of "
                "direction, with arrows at the ends showing the direction of "
                "SIGHT, lettered with capitals and named as, for example, "
                "SECTION A-A. Reject a continuous thick or dashed "
                "cutting-plane line, and reject 'the arrows point away from "
                "the retained portion'.",
                "The material between the observer and the cutting plane is "
                "removed; hatching is applied only where the plane actually "
                "cuts material, so holes, voids and the space beyond a cut "
                "stay unhatched. Reject any card that hatches a hole or the "
                "whole outline of the view.",
                "The true shape of a section appears in a view projected on a "
                "plane PARALLEL to the cutting plane — reject 'perpendicular "
                "to the cutting plane'. Hidden lines behind the cutting plane "
                "are normally omitted in the sectional view, while the "
                "remaining, unsectioned views of the object are still drawn "
                "complete. Reject cards claiming hidden lines must be shown "
                "in a sectional view or that the other views are also cut.",
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Only the formulas, the method-to-solid mapping and a few "
                "definitions survive on a card here, so aim squarely at "
                "those. Favour: which development method suits prisms and "
                "cylinders as against pyramids and cones, and which suits "
                "transition pieces; that every line in a development is a "
                "true length and a development shows the surface's true area; "
                "the πd × h rectangle for a cylinder; the base-perimeter × "
                "height rectangle for a prism; the cone's sector of radius "
                "equal to the slant height with θ = (r/L) × 360°; that a "
                "pyramid develops into triangles built on the true length of "
                "the slant edge; and that a sphere is not truly developable. "
                "Ask for a formula, a method name or a definition, and never "
                "for a laid-out development."
            ),
            traps=(
                "Method-to-solid mapping must hold: parallel-line development "
                "suits prisms and cylinders, radial-line development suits "
                "pyramids and cones, and triangulation suits transition "
                "pieces and oblique forms. Reject the parallel/radial swap. A "
                "sphere and other double-curved surfaces are NOT truly "
                "developable and are only approximated (zone or lune methods) "
                "— reject any card claiming an exact development of a sphere.",
                "A cylinder's lateral development is a rectangle πd wide by h "
                "high, where d is the diameter. Reject 2πd, πr, πd² or πdh "
                "given as the width.",
                "A right prism's lateral development is a rectangle whose "
                "length equals the base PERIMETER (number of sides × side "
                "length) and whose height equals the prism's height, divided "
                "by fold lines at the vertical edges. Reject a length based "
                "on one side, on the base area, or on the diagonal.",
                "A cone's lateral development is a sector of radius equal to "
                "the SLANT height L, with included angle θ = (r/L) × 360°, "
                "where r is the base radius. Reject the use of the vertical "
                "height in place of the slant height, reject θ = (L/r) × "
                "360°, and reject a sector radius equal to r or to the axis "
                "length.",
                "A pyramid develops into triangles whose sloping sides are "
                "the TRUE LENGTH of the slant edge — not the vertical height "
                "and not the slant height of a face unless the face's "
                "altitude is what is being asked. For a truncated or cut "
                "solid, the true lengths of the cut edges must be obtained by "
                "rotating them parallel to a plane of projection; reject any "
                "card that reads those lengths straight off the front view.",
                "Every line in a development is a true length and the "
                "development represents the true area of the surface; it is "
                "laid out from a single seam, conventionally the shortest "
                "edge, and covers the LATERAL surface only unless the ends "
                "are explicitly included. Reject 'a development may be drawn "
                "to a reduced length for the sloping edges' and reject any "
                "card asserting that the base and top are always part of the "
                "development.",
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Isometric is unusually card-friendly because it rests on "
                "fixed numbers — use them. Favour: the three axes 120° apart "
                "with two of them 30° to the horizontal and one vertical; the "
                "isometric scale ratio 0.816; the difference between an "
                "isometric view, drawn to true lengths, and an isometric "
                "projection, drawn to the isometric scale and therefore the "
                "smaller of the two; isometric versus non-isometric lines and "
                "why an inclined line cannot be measured directly; that "
                "angles never appear in true size; that a circle becomes an "
                "ellipse drawn by the four-centre method; and where isometric "
                "sits among the axonometric and oblique projections. Ask for "
                "a number, a ratio or a one-word distinction, never for a "
                "pictorial view."
            ),
            traps=(
                "The three isometric axes are 120° apart, with two of them at "
                "30° to the horizontal and the third vertical. Reject 90°, "
                "60° or 45° in either statement, and reject '45° to the "
                "horizontal'.",
                "The isometric scale ratio is 0.816 (≈ 9/11, from √2/√3) of "
                "true length. Reject 0.866, 0.707 and 0.5, and reject any "
                "card that inverts it.",
                "An isometric VIEW (isometric drawing) is made with true "
                "lengths; an isometric PROJECTION is made with the isometric "
                "scale and is therefore about 0.816 times the view, the view "
                "being about 1.22 times the projection. Reject the swap and "
                "reject 'the isometric projection is the larger of the two'.",
                "Only lines PARALLEL to the isometric axes (isometric lines) "
                "are drawn to measured length; non-isometric lines — inclined "
                "edges, diagonals — are not true length and must be located "
                "by their end points using offsets along the axes. Angles "
                "never appear in true size in isometric, so reject any card "
                "that has an angle set off with a protractor or a 60° corner "
                "drawn as 60°.",
                "A circle on an isometric plane appears as an ELLIPSE, "
                "normally constructed by the four-centre method, with its "
                "minor axis along the isometric axis normal to that face and "
                "its major axis perpendicular to it. In an isometric "
                "projection of a circle of diameter D the ellipse has major "
                "axis D and minor axis 0.577D; in an isometric drawing these "
                "become about 1.22D and 0.7D. Reject a circle drawn as a "
                "circle on an isometric face, and reject a major axis placed "
                "along the normal axis.",
                "Isometric is the axonometric case with all three axes "
                "equally inclined and equally foreshortened; dimetric has two "
                "equal and trimetric none. It is NOT oblique projection — "
                "cavalier and cabinet keep one face true and set the receding "
                "axis at an angle, cabinet halving its depth. Reject any card "
                "that calls isometric a form of oblique or perspective "
                "projection, or that gives isometric unequal foreshortening.",
            ),
        ),
    ),
}


def guidance_for(topic_code: str, unit_number: int) -> UnitGuidance | None:
    """`unit_number` is 1-based, as shown to the student."""
    units = _UNITS.get((topic_code or "").strip().upper())
    if not units or not 1 <= unit_number <= len(units):
        return None
    return units[unit_number - 1]


def guidance_text(topic_code: str, unit_number: int) -> str:
    """The block to splice into a generation prompt, or "" when unresearched.

    Returns a leading blank line with the text so the prompt reads correctly
    either way — an empty slot leaves no gap, a filled one is its own
    paragraph.
    """
    g = guidance_for(topic_code, unit_number)
    return f"\n{g.guidance}\n" if g else ""


def traps_text(topic_code: str, unit_number: int) -> str:
    """The fact checker's per-unit checklist, or "" when unresearched."""
    g = guidance_for(topic_code, unit_number)
    if g is None or not g.traps:
        return ""
    listed = "\n".join(f"- {t}" for t in g.traps)
    return ("\nMistakes that are common in this unit specifically. Check every "
            "card against this list; a card that makes one of these is "
            '"wrong":\n' + listed + "\n")
