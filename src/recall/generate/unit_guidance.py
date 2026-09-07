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

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitGuidance:
    """One unit's worth of "write cards like this"."""

    guidance: str
    """A paragraph, in the imperative, spliced into the generation prompt."""

    traps: tuple[str, ...] = ()
    """The specific errors students (and models) make in this unit. Shown to
    the fact checker as a checklist, not to the writer — telling a model
    "don't say X" is a reliable way to make it say X.

    Which means a trap can only catch a card that is WRONG. "Never write cards
    about the Double Diamond, it is not on this syllabus" is not a trap: the
    writer never sees it, and a Double Diamond card is off-syllabus rather
    than incorrect, so the checker will pass it. Every exclusion belongs in
    `guidance`, where the writer reads it. A verification pass caught exactly
    that mistake sitting in INT335's list."""

    examples: tuple["WorkedExample", ...] = ()
    """Two genuinely hard worked examples for this unit, shown to the writer
    as few-shot calibration.

    A paragraph can describe difficulty; only an example can show it. Telling
    the model "favour multi-step derivations" produces a card that mentions
    steps. Showing it one real multi-step derivation, done correctly, at the
    depth an end-term actually demands, produces cards that look like it.

    Exactly two per unit, not more: enough to fix a level without being long
    enough for the model to start reproducing their SUBJECT MATTER rather than
    their SHAPE — a card about eigenvalues of THIS matrix teaches nothing
    about eigenvalues of a different one if the model just varies numbers, so
    the examples are deliberately drawn from different corners of the unit."""


@dataclass(frozen=True)
class WorkedExample:
    """One hard card, in the exact shape a real one takes.

    This is not a description of a good card, it IS one — question, short
    answer, and the numbered-steps detail — because it is spliced into the
    prompt as a few-shot example. Every field follows the same contract
    `_CARD_CONTRACT` states, and violating that contract here would teach the
    model to violate it everywhere this example is shown."""

    question: str
    answer: str
    detail: str


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
            examples=(
                WorkedExample(
                    question=(
                        "For the system x + y + z = 6, x + 2y + 3z = 14, 2x + 3y + kz = 20, find the value of k for which the solution is not unique, and state how many solutions the system has for that k."
                    ),
                    answer=(
                        "k = 4; the system is then consistent with infinitely many solutions (one free parameter)."
                    ),
                    detail=(
                        "1. Coefficient matrix A = [[1, 1, 1], [1, 2, 3], [2, 3, k]]. Expand det A along the first row: 1(2k − 9) − 1(k − 6) + 1(3 − 4).\n"
                        "2. Simplify: det A = 2k − 9 − k + 6 − 1 = k − 4.\n"
                        "3. A square system has a unique solution only when det A ≠ 0, so uniqueness can fail only at k = 4.\n"
                        "4. Put k = 4 and row-reduce the augmented matrix [A | b] = [[1, 1, 1 | 6], [1, 2, 3 | 14], [2, 3, 4 | 20]].\n"
                        "5. R2 → R2 − R1 gives [0, 1, 2 | 8]; R3 → R3 − 2R1 gives [0, 1, 2 | 8]; then R3 → R3 − R2 gives [0, 0, 0 | 0].\n"
                        "6. So rank A = 2 and rank [A | b] = 2. They are equal, so the system is consistent — a solution exists.\n"
                        "7. Now compare that common rank with n, the number of unknowns: n = 3 and r = 2, so r < n and there are n − r = 1 free parameters. Infinitely many solutions.\n"
                        "8. Explicitly, take z = t: then y = 8 − 2t and x = 6 − y − z = −2 + t. Check in equation 2: (−2 + t) + 2(8 − 2t) + 3t = 14 for every t. ✓\n"
                        "Most likely mistake: seeing rank A = rank [A | b] at k = 4 and calling the solution unique. Consistency only says a solution exists; uniqueness needs r = n as well."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Using the Cayley–Hamilton theorem, find A⁻¹ for the square matrix A = [[1, 2, 3], [2, 4, 5], [3, 5, 6]]."
                    ),
                    answer=(
                        "A⁻¹ = [[1, −3, 2], [−3, 3, −1], [2, −1, 0]]"
                    ),
                    detail=(
                        "1. S₁ = trace A = 1 + 4 + 6 = 11.\n"
                        "2. S₂ = sum of the three principal 2×2 minors = (4·6 − 5·5) + (1·6 − 3·3) + (1·4 − 2·2) = (−1) + (−3) + 0 = −4.\n"
                        "3. S₃ = det A = 1(24 − 25) − 2(12 − 15) + 3(10 − 12) = −1 + 6 − 6 = −1. This is non-zero, so A is non-singular and A⁻¹ exists — without that check the last step below is invalid.\n"
                        "4. Characteristic equation λ³ − S₁λ² + S₂λ − S₃ = 0, i.e. λ³ − 11λ² − 4λ + 1 = 0 (note −S₃ = +1).\n"
                        "5. Cayley–Hamilton says A satisfies its own characteristic equation: A³ − 11A² − 4A + I = O.\n"
                        "6. Multiply throughout by A⁻¹: A² − 11A − 4I + A⁻¹ = O, hence A⁻¹ = −A² + 11A + 4I.\n"
                        "7. A² = [[14, 25, 31], [25, 45, 56], [31, 56, 70]].\n"
                        "8. Form −A² + 11A + 4I entry by entry: (1,1) = −14 + 11 + 4 = 1, (1,2) = −25 + 22 = −3, (1,3) = −31 + 33 = 2, (2,2) = −45 + 44 + 4 = 3, (2,3) = −56 + 55 = −1, (3,3) = −70 + 66 + 4 = 0, and A⁻¹ is symmetric like A.\n"
                        "9. A⁻¹ = [[1, −3, 2], [−3, 3, −1], [2, −1, 0]]. Check row 1 of A·A⁻¹: (1 − 6 + 6, −3 + 6 − 3, 2 − 2 + 0) = (1, 0, 0). ✓\n"
                        "Most likely mistake: dropping S₂ or flipping the alternating signs in λ³ − S₁λ² + S₂λ − S₃ = 0. Here S₃ = −1, so the constant term is +1; that constant term is exactly what the A⁻¹ step divides by, and it vanishes precisely when det A = 0."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "Evaluate lim(x→0) (sin x / x)^(1/x²)."
                    ),
                    answer=(
                        "e^(−1/6)"
                    ),
                    detail=(
                        "1. As x → 0 the base sin x / x → 1 and the exponent 1/x² → ∞, so this is the form 1^∞. L'Hospital's rule applies only to 0/0 or ∞/∞, so it cannot be used on this expression as it stands.\n"
                        "2. Put L = lim(x→0) (sin x / x)^(1/x²) and take logarithms: ln L = lim(x→0) ln(sin x / x) / x². Now the numerator → ln 1 = 0 and the denominator → 0, a genuine 0/0.\n"
                        "3. Differentiate numerator and denominator SEPARATELY (not with the quotient rule): d/dx[ln sin x − ln x] = cot x − 1/x, and d/dx[x²] = 2x.\n"
                        "4. ln L = lim(x→0) (cot x − 1/x)/(2x) = lim(x→0) (x cos x − sin x)/(2x² sin x), still 0/0.\n"
                        "5. Apply L'Hospital again: d/dx[x cos x − sin x] = cos x − x sin x − cos x = −x sin x, and d/dx[2x² sin x] = 4x sin x + 2x² cos x.\n"
                        "6. ln L = lim(x→0) (−x sin x)/(4x sin x + 2x² cos x) = lim(x→0) (−sin x)/(4 sin x + 2x cos x) after cancelling one x.\n"
                        "7. Divide numerator and denominator by x and use (sin x)/x → 1: ln L = −1/(4 + 2) = −1/6.\n"
                        "8. Therefore L = e^(−1/6) ≈ 0.8465.\n"
                        "Most likely mistake: differentiating the power form directly without first taking logarithms, or getting ln L = −1/6 and reporting −1/6 as the answer instead of exponentiating back."
                    ),
                ),
                WorkedExample(
                    question=(
                        "For the curve x = a cos³θ, y = a sin³θ with a > 0, find d²y/dx² at θ = π/4."
                    ),
                    answer=(
                        "d²y/dx² = 4√2/(3a)"
                    ),
                    detail=(
                        "1. Differentiate each coordinate with respect to the parameter: dx/dθ = −3a cos²θ sin θ and dy/dθ = 3a sin²θ cos θ.\n"
                        "2. dy/dx = (dy/dθ)/(dx/dθ) = (3a sin²θ cos θ)/(−3a cos²θ sin θ) = −sin θ/cos θ = −tan θ, valid wherever dx/dθ ≠ 0, i.e. sin θ cos θ ≠ 0.\n"
                        "3. The second derivative is d²y/dx² = [d/dθ(dy/dx)]/(dx/dθ). It is NOT (d²y/dθ²)/(d²x/dθ²).\n"
                        "4. d/dθ(−tan θ) = −sec²θ.\n"
                        "5. d²y/dx² = (−sec²θ)/(−3a cos²θ sin θ) = sec²θ/(3a cos²θ sin θ) = 1/(3a cos⁴θ sin θ).\n"
                        "6. At θ = π/4: cos θ = sin θ = 1/√2, so cos⁴θ = 1/4 and the denominator is 3a·(1/4)·(1/√2) = 3a/(4√2).\n"
                        "7. Hence d²y/dx² = 4√2/(3a) ≈ 1.8856/a, which is positive, so the curve is concave up there.\n"
                        "Most likely mistake: writing d²y/dx² as (d²y/dθ²)/(d²x/dθ²). The first derivative must be re-differentiated with respect to θ and then divided by dx/dθ once more."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "Evaluate ∫₀^π x sin x/(1 + cos²x) dx."
                    ),
                    answer=(
                        "π²/4"
                    ),
                    detail=(
                        "1. Call the integral I. King's property on a general interval is ∫ₐᵇ f(x) dx = ∫ₐᵇ f(a + b − x) dx; here a = 0 and b = π, so x is replaced by π − x — not by −x.\n"
                        "2. sin(π − x) = sin x and cos(π − x) = −cos x, so cos²(π − x) = cos²x. Only the factor x changes.\n"
                        "3. I = ∫₀^π (π − x) sin x/(1 + cos²x) dx.\n"
                        "4. Add the two expressions for I: 2I = ∫₀^π [x + (π − x)]·sin x/(1 + cos²x) dx = π∫₀^π sin x/(1 + cos²x) dx.\n"
                        "5. In the remaining integral substitute u = cos x, so du = −sin x dx, and convert the limits: x = 0 gives u = 1, x = π gives u = −1. Convert the limits and stop — do not go back to x.\n"
                        "6. ∫₀^π sin x/(1 + cos²x) dx = −∫ du/(1 + u²) from u = 1 to u = −1 = ∫ du/(1 + u²) from u = −1 to u = 1 = [tan⁻¹u] from −1 to 1 = π/4 − (−π/4) = π/2.\n"
                        "7. So 2I = π·(π/2) = π²/2, giving I = π²/4 ≈ 2.4674. No + C: the integral is definite.\n"
                        "Most likely mistake: using f(a − x) = f(−x) instead of f(a + b − x) = f(π − x), or evaluating the u-antiderivative tan⁻¹u at the original x-limits 0 and π."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Evaluate ∫₀¹ dx/((x + 1)(x + 2)²)."
                    ),
                    answer=(
                        "ln(4/3) − 1/6  (≈ 0.1210)"
                    ),
                    detail=(
                        "1. The fraction is proper (degree 0 over degree 3), so no division is needed; but (x + 2) is a repeated factor, so the decomposition needs three terms: 1/((x + 1)(x + 2)²) = A/(x + 1) + B/(x + 2) + C/(x + 2)².\n"
                        "2. Multiply through by (x + 1)(x + 2)²: 1 = A(x + 2)² + B(x + 1)(x + 2) + C(x + 1).\n"
                        "3. Put x = −1: 1 = A(1)², so A = 1.\n"
                        "4. Put x = −2: 1 = C(−1), so C = −1.\n"
                        "5. Compare coefficients of x²: 0 = A + B, so B = −1.\n"
                        "6. Integrand = 1/(x + 1) − 1/(x + 2) − 1/(x + 2)².\n"
                        "7. Antiderivative = ln|x + 1| − ln|x + 2| + 1/(x + 2). The third term is a power −2, not a logarithm: ∫(x + 2)⁻² dx = −(x + 2)⁻¹, and the leading minus sign turns it into +1/(x + 2).\n"
                        "8. At x = 1: ln 2 − ln 3 + 1/3. At x = 0: ln 1 − ln 2 + 1/2 = −ln 2 + 1/2.\n"
                        "9. I = (ln 2 − ln 3 + 1/3) − (−ln 2 + 1/2) = 2 ln 2 − ln 3 − 1/6 = ln(4/3) − 1/6 ≈ 0.1210.\n"
                        "Most likely mistake: writing only C/(x + 2)² for the repeated factor and omitting B/(x + 2) — with two unknowns the identity cannot be satisfied — or integrating 1/(x + 2)² as a logarithm."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "If u = sin⁻¹((x² + y²)/(x + y)), find the value of x(∂u/∂x) + y(∂u/∂y)."
                    ),
                    answer=(
                        "x(∂u/∂x) + y(∂u/∂y) = tan u"
                    ),
                    detail=(
                        "1. u itself is not homogeneous, so Euler's theorem cannot be applied to u directly. Isolate the part that is: sin u = (x² + y²)/(x + y).\n"
                        "2. Test homogeneity of F = sin u: replace x by tx and y by ty. (t²x² + t²y²)/(tx + ty) = t(x² + y²)/(x + y) = t¹·sin u. So F is homogeneous of degree n = 1 — for a quotient the degrees subtract, 2 − 1 = 1.\n"
                        "3. Euler's theorem: if F(x, y) is homogeneous of degree n and its first-order partial derivatives exist, then x F_x + y F_y = n F.\n"
                        "4. Here F = sin u, so by the chain rule F_x = cos u·(∂u/∂x) and F_y = cos u·(∂u/∂y).\n"
                        "5. Substitute: x cos u (∂u/∂x) + y cos u (∂u/∂y) = 1·sin u.\n"
                        "6. Divide through by cos u (non-zero wherever the expression is defined and u ≠ ±π/2): x(∂u/∂x) + y(∂u/∂y) = sin u/cos u = tan u.\n"
                        "Most likely mistake: answering n·u, i.e. just u. When u is an inverse-trig or log wrapper the correct result is n·F(u)/F′(u) = 1·sin u/cos u = tan u; the answer n·u holds only when u itself is the homogeneous function."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Find and classify all stationary points of f(x, y) = x³ + y³ − 3xy."
                    ),
                    answer=(
                        "Saddle point at (0, 0); local minimum with f = −1 at (1, 1)."
                    ),
                    detail=(
                        "1. f_x = 3x² − 3y and f_y = 3y² − 3x. Stationary points need both to vanish.\n"
                        "2. From f_x = 0: y = x². Substitute into f_y = 0: 3(x²)² − 3x = 0, i.e. x⁴ − x = 0.\n"
                        "3. Factor: x(x³ − 1) = 0, so the real roots are x = 0 and x = 1.\n"
                        "4. Stationary points: x = 0 gives y = 0, so (0, 0); x = 1 gives y = 1, so (1, 1).\n"
                        "5. Second-order partials: f_xx = 6x, f_yy = 6y, f_xy = −3 (a constant), and D = f_xx·f_yy − (f_xy)².\n"
                        "6. At (0, 0): D = 0·0 − (−3)² = −9 < 0, so (0, 0) is a saddle point. D < 0 is a definite verdict, not a failure of the test.\n"
                        "7. At (1, 1): D = 6·6 − 9 = 36 − 9 = 27 > 0, and f_xx = 6 > 0, so (1, 1) is a local minimum. (Had f_xx been negative it would have been a local maximum with the same D.)\n"
                        "8. Value there: f(1, 1) = 1 + 1 − 3·1·1 = −1.\n"
                        "Most likely mistake: quoting D > 0 without also reporting the sign of f_xx, which is what separates maximum from minimum — or reading D < 0 as \"inconclusive\". Only D = 0 is inconclusive."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "Evaluate ∫₀¹ ∫ₓ¹ (sin y)/y dy dx by first changing the order of integration."
                    ),
                    answer=(
                        "1 − cos 1  (≈ 0.4597)"
                    ),
                    detail=(
                        "1. (sin y)/y has no elementary antiderivative, so the inner integral cannot be done in the order given. The order must be reversed.\n"
                        "2. Read the region from the limits: x runs from 0 to 1, and for each x, y runs from y = x up to y = 1. That is the triangle bounded by y = x, y = 1 and x = 0, with vertices (0, 0), (0, 1) and (1, 1).\n"
                        "3. Re-derive the limits with y outside, from the region rather than by swapping symbols: y takes every value from 0 to 1, and for a fixed y the horizontal strip runs from the left edge x = 0 across to the line y = x, i.e. x = y. So x goes from 0 to y.\n"
                        "4. Reversed integral: ∫₀¹ ∫₀^y (sin y)/y dx dy. The outer limits 0 and 1 are pure constants — no x or y survives in them.\n"
                        "5. Inner integral: (sin y)/y is constant with respect to x, so ∫₀^y (sin y)/y dx = (sin y)/y·(y − 0) = sin y. The awkward 1/y cancels.\n"
                        "6. Outer integral: ∫₀¹ sin y dy = [−cos y]₀¹ = −cos 1 + cos 0 = 1 − cos 1 ≈ 0.4597.\n"
                        "Most likely mistake: swapping the limit expressions mechanically to get \"x from x to 1, y from 0 to 1\", which leaves the variable x inside its own limit. The reversed limits must come from a sketch of the region."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Evaluate ∫₀² ∫₀^√(2x − x²) (x² + y²) dy dx by changing to polar coordinates."
                    ),
                    answer=(
                        "3π/4  (≈ 2.3562)"
                    ),
                    detail=(
                        "1. Identify the region: 0 ≤ y ≤ √(2x − x²) means y² ≤ 2x − x², i.e. x² + y² ≤ 2x, with y ≥ 0 and 0 ≤ x ≤ 2.\n"
                        "2. Complete the square: (x − 1)² + y² ≤ 1. The region is the UPPER half of the disc of radius 1 centred at (1, 0).\n"
                        "3. Put x = r cos θ, y = r sin θ (plane polars). The boundary x² + y² = 2x becomes r² = 2r cos θ, so r = 2 cos θ.\n"
                        "4. Limits: for a fixed θ, r runs from 0 to 2 cos θ; and θ runs from 0 to π/2, since 2 cos θ is negative beyond π/2 and the upper half-disc lies entirely in the first quadrant.\n"
                        "5. The area element is r dr dθ, not dr dθ, and the integrand x² + y² becomes r².\n"
                        "6. I = ∫₀^(π/2) ∫₀^(2 cos θ) r²·r dr dθ = ∫₀^(π/2) [r⁴/4]₀^(2 cos θ) dθ = ∫₀^(π/2) (2 cos θ)⁴/4 dθ = ∫₀^(π/2) 4 cos⁴θ dθ.\n"
                        "7. By Wallis' formula ∫₀^(π/2) cos⁴θ dθ = (3·1)/(4·2)·(π/2) = 3π/16.\n"
                        "8. I = 4·(3π/16) = 3π/4 ≈ 2.3562. The outer limits are constants and no x or y remains — as required of a definite double integral.\n"
                        "Most likely mistake: writing dx dy = dr dθ and losing the factor r, which gives ∫₀^(π/2) (8 cos³θ)/3 dθ = 16/9 instead of 3π/4 — or letting θ run 0 to 2π for a region that occupies only 0 ≤ θ ≤ π/2."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A function of period 2π is defined by f(x) = 0 for −π < x < 0 and f(x) = x for 0 ≤ x < π. Writing its Fourier series as a₀/2 + Σ(aₙ cos nx + bₙ sin nx), find the constant term of the series."
                    ),
                    answer=(
                        "Constant term = a₀/2 = π/4  (here a₀ = π/2)"
                    ),
                    detail=(
                        "1. The period is 2L = 2π, so L = π, and on a full interval of length 2L the Euler factor is 1/L = 1/π: a₀ = (1/π)·∫ f(x) dx taken over (−π, π).\n"
                        "2. f is piecewise, so split the integral at the breakpoint x = 0 rather than pushing one formula across the whole period: a₀ = (1/π)[∫ 0 dx over (−π, 0) + ∫₀^π x dx].\n"
                        "3. The first piece is 0. The second piece is [x²/2]₀^π = π²/2.\n"
                        "4. a₀ = (1/π)·(π²/2) = π/2.\n"
                        "5. In the convention a₀/2 + Σ(aₙ cos nx + bₙ sin nx) the constant term of the series is a₀/2, not a₀: constant term = (π/2)/2 = π/4 ≈ 0.7854.\n"
                        "6. Check: the constant term of any Fourier series is the mean value of f over one period, (1/2π)·∫ f dx over (−π, π) = (1/2π)(π²/2) = π/4. ✓\n"
                        "Most likely mistake: reporting a₀ = π/2 as the constant term. With a₀ = (1/L)∫ over one period, a₀ is twice the mean value; halving it is exactly what makes a₀/2 the constant term. Also note the even/odd shortcut is unavailable here — this f is neither even nor odd."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Find the Fourier series of f(x) = x² on −π < x < π (period 2π), and hence evaluate 1 + 1/2² + 1/3² + 1/4² + ⋯"
                    ),
                    answer=(
                        "x² = π²/3 + 4Σ(−1)ⁿ(cos nx)/n²; the sum is π²/6."
                    ),
                    detail=(
                        "1. Here 2L = 2π so L = π; the Euler factor on this full interval is 1/π.\n"
                        "2. f(−x) = (−x)² = x² = f(x), and the interval (−π, π) IS symmetric about the origin, so f is even and every bₙ = 0. (The shortcut is legitimate only because of that symmetry — it would not apply on, say, (0, 2π).)\n"
                        "3. a₀ = (1/π)·∫ x² dx over (−π, π) = (1/π)·(2π³/3) = 2π²/3, so the constant term a₀/2 = π²/3.\n"
                        "4. aₙ = (1/π)·∫ x² cos nx dx over (−π, π) = (2/π)∫₀^π x² cos nx dx, since x² cos nx is even.\n"
                        "5. Integrate by parts with u = x², dv = cos nx dx: ∫₀^π x² cos nx dx = [x² sin nx/n]₀^π − (2/n)∫₀^π x sin nx dx. The bracket vanishes because sin nπ = 0.\n"
                        "6. By parts again: ∫₀^π x sin nx dx = [−x cos nx/n]₀^π + (1/n)∫₀^π cos nx dx = −π(−1)ⁿ/n + 0 = π(−1)^(n+1)/n, using cos nπ = (−1)ⁿ and sin nπ = 0.\n"
                        "7. So ∫₀^π x² cos nx dx = −(2/n)·π(−1)^(n+1)/n = 2π(−1)ⁿ/n², and aₙ = (2/π)·2π(−1)ⁿ/n² = 4(−1)ⁿ/n². Check: a₁ = −4, a₂ = 1, a₃ = −4/9.\n"
                        "8. Series: x² = π²/3 + 4Σ from n = 1 to ∞ of (−1)ⁿ(cos nx)/n², for −π < x < π.\n"
                        "9. Substitute x = π. This is legitimate because the periodic extension of x² is CONTINUOUS at x = π: f(π⁻) = π² and f(−π⁺) = π² agree, so the series converges to π² there, not to a mean of two different values.\n"
                        "10. cos nπ = (−1)ⁿ, so (−1)ⁿ·cos nπ = (−1)²ⁿ = 1: π² = π²/3 + 4Σ 1/n².\n"
                        "11. Hence 4Σ 1/n² = π² − π²/3 = 2π²/3, giving 1 + 1/2² + 1/3² + ⋯ = π²/6 ≈ 1.6449.\n"
                        "Most likely mistake: substituting a point where the periodic extension jumps and equating the series to f there. Here x = π is safe, but for f(x) = x on (−π, π) the same substitution is invalid — the series converges to ½[f(π⁻) + f(−π⁺)] = 0 at that endpoint."
                    ),
                ),
            ),
        ),
    ),
    "CSE111": (
        # --- 1 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that separate one translator, one language "
                "level, or one error category by a single exact property. "
                "Good shapes: which translator turns assembly into machine "
                "code; what a compiler produces before execution; what an "
                "interpreted program has already done when it stops at a bad "
                "statement; what pass 1 of a two-pass assembler records and "
                "what pass 2 replaces; which of compilation error, runtime "
                "error and logic error a one-line symptom is. Ask for the "
                "fixed order source → preprocessing → compilation → assembly "
                "→ linking → loading → CPU execution, and the phases of the "
                "program development cycle in order: problem definition, "
                "analysis, algorithm design, coding, translation, testing and "
                "debugging, documentation, maintenance. Quote mnemonics such "
                "as `MOV R1, #5` and statements such as `total = price * "
                "quantity` exactly as typed. Skip “what is a computer "
                "language”."
            ),
            traps=(
                "A card claiming an interpreted program produces no output "
                "when it reaches an error. An interpreter translates and "
                "executes statement by statement, so everything before the "
                "bad statement has already run and its effects persist; "
                "errors in later statements stay undiscovered until those "
                "statements are reached.",
                "A card asserting that one assembly statement always becomes "
                "exactly one machine instruction. The taught wording is that "
                "one assembly statement corresponds CLOSELY to one machine "
                "instruction, although pseudo-instructions may expand into "
                "several — so a card promising a guaranteed one-to-one "
                "mapping is wrong, and so is a card denying the close "
                "correspondence outright.",
                "Error-category confusion. Compilation errors are reported "
                "before an executable is produced, runtime errors occur "
                "during execution (division by zero), and logic errors let "
                "the program run successfully while producing the wrong "
                "result. A card calling division by zero a compile-time "
                "error, or a wrong-average bug a runtime error, is wrong.",
                "A card saying the compiler produces the executable directly, "
                "or that the linker loads the program. The compiler emits "
                "object or intermediate code, the linker combines object "
                "files and libraries (a call such as `printf()` is resolved "
                "here), and the operating system loader places the executable "
                "in memory and prepares its execution environment — three "
                "distinct steps.",
                "Two-pass assembler direction. Pass 1 records labels and "
                "instruction locations; pass 2 converts symbolic references "
                "into final machine addresses. A card that has pass 1 "
                "producing final addresses, or pass 2 building the symbol "
                "table, has the passes reversed.",
                "Portability claims. High-level source can often be used on "
                "different systems after translation by an appropriate "
                "compiler or interpreter; machine and assembly language are "
                "tied to one processor's instruction set, so a program "
                "encoded for x86 need not run on ARM. A card calling compiled "
                "machine code portable, or claiming high-level source runs "
                "without translation, is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "The same five-line program is written twice: once in a compiled language such as C, once in an interpreted language. Lines 1 to 3 print output; line 4 uses a variable `total` that was never declared or assigned; line 5 prints again. One team compiles their version and runs it, the other runs theirs through an interpreter. Which team sees any output on screen?"
                    ),
                    answer=(
                        "Only the interpreted run — the compiled one never produces an executable."
                    ),
                    detail=(
                        "1. The compiler reads the WHOLE program before anything is executed, so it meets the undeclared `total` on line 4 while still translating.\n"
                        "2. An undeclared identifier is a compilation error, and a compilation error means no object code and no executable is produced.\n"
                        "3. Nothing was ever run, so lines 1 to 3 never executed: the screen shows the error list and no program output at all.\n"
                        "4. The interpreter instead translates and executes one statement at a time: line 1 runs and prints, then line 2, then line 3, and those effects persist.\n"
                        "5. At line 4 the interpreter finds `total` undefined and stops there, so the three lines already printed stay on screen.\n"
                        "6. Line 5 is never reached, so any error in it stays undiscovered.\n"
                        "Most likely mistake: assuming an interpreted program prints nothing once it hits an error — everything before the bad statement has already run."
                    ),
                ),
                WorkedExample(
                    question=(
                        "An assembly source file contains the instruction `JMP LOOP`, and the label `LOOP:` is defined twenty instructions further down the file. A two-pass assembler translates it. In which pass is the address of `LOOP` recorded, and in which pass is the operand of `JMP` replaced by that address?"
                    ),
                    answer=(
                        "Recorded in pass 1; substituted in pass 2."
                    ),
                    detail=(
                        "1. On pass 1 the assembler scans the source from top to bottom keeping a location counter, and enters every label it meets into the symbol table with the address it is defined at.\n"
                        "2. When pass 1 reaches `JMP LOOP`, `LOOP` has not been defined yet — this is a forward reference — so no address can be filled in; pass 1 only advances the location counter past the instruction.\n"
                        "3. Twenty instructions later pass 1 meets `LOOP:` and records `LOOP` with its address in the symbol table.\n"
                        "4. On pass 2 the assembler re-reads the source. Every symbol is now known, so it looks `LOOP` up and replaces the symbolic operand with the final machine address.\n"
                        "5. So the address is recorded in pass 1 and substituted in pass 2 — the forward reference is the entire reason a second pass exists.\n"
                        "Most likely mistake: reversing the passes, having pass 1 emit the final addresses and pass 2 build the symbol table."
                    ),
                ),
            ),
        ),
        # --- 2 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Favour cards that pin a generation to its switching "
                "technology and dates, a characteristic to its one-line "
                "definition, a functional unit to the one job only it does, "
                "and a machine type to a described scenario. Good shapes: "
                "which technology defines the third generation; who built the "
                "Pascaline and in what year; which characteristic “repeats an "
                "operation without fatigue or loss of concentration” names; "
                "which bus carries read, write and interrupt signals; the "
                "cycle fetch → decode → execute → store → advance; for 8 + 5, "
                "which unit produces 13 and which unit directed it; what "
                "makes code firmware rather than application software; "
                "whether a described machine is a supercomputer, mainframe, "
                "server, workstation, embedded system or hybrid. Ask what the "
                "stored-program idea changed. Prefer a scenario that must be "
                "classified over “define a computer”."
            ),
            traps=(
                "A card defining accuracy as “always gives correct results”. "
                "Accuracy means correct results when the hardware, data and "
                "instructions are correct — the taught phrase is “garbage in, "
                "garbage out”, so wrong input still yields wrong output.",
                "Characteristic swap. Diligence is repeating an operation "
                "without fatigue or loss of concentration, versatility is "
                "supporting different kinds of task, speed is operations per "
                "second, storage is retention and rapid retrieval. A card "
                "using one name for another's definition is wrong. So is a "
                "card crediting a computer with judgment, common sense or "
                "moral responsibility.",
                "Generation-to-technology mismatch. First generation vacuum "
                "tubes (approximately 1940-1956, ENIAC, machine language), "
                "second transistors (approximately 1956-1963, FORTRAN and "
                "COBOL), third integrated circuits (approximately 1964-1971, "
                "operating systems and multiprogramming), fourth "
                "microprocessors (from 1971, Intel 4004). A card placing "
                "integrated circuits in the second generation, or transistors "
                "in the third, is wrong; and the fifth generation is an "
                "ongoing direction (AI, natural-language processing, machine "
                "learning, robotics, parallel processing), not a sharply "
                "dated hardware generation.",
                "Bus roles. The data bus carries the data, the address bus "
                "identifies a memory location or device, and the control bus "
                "carries commands such as read, write and interrupt. A card "
                "giving the address bus the data, or the data bus the "
                "read/write signals, is wrong.",
                "Primary against secondary, and volatility. Registers, cache, "
                "RAM and ROM are primary memory; solid-state drives, hard "
                "disks, optical discs and flash drives are secondary storage "
                "with greater capacity and slower access. RAM is volatile, "
                "ROM is non-volatile. A card calling a hard disk primary "
                "memory, or ROM volatile, is wrong.",
                "Software categories. System software (the operating system, "
                "device drivers, utility programs) manages hardware; "
                "application software performs user tasks; programming "
                "software builds programs; firmware is held in non-volatile "
                "memory and controls hardware at a low level, with BIOS or "
                "UEFI beginning startup. A card calling a device driver "
                "application software, or an operating system firmware, is "
                "wrong — and proprietary, open source and freeware are "
                "licensing categories, not technical ones.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "A running program reaches the statement `total = 8 + 5`. Name the functional unit that actually produces 13, and the functional unit that fetched the instruction, decoded it, and signalled the first unit to act."
                    ),
                    answer=(
                        "The ALU produces 13; the control unit directed it."
                    ),
                    detail=(
                        "1. The instruction sits in main memory. The control unit fetches it and decodes it, working out that an addition is required.\n"
                        "2. The control unit then issues the signals that route the operands 8 and 5 from registers into the arithmetic and logic unit.\n"
                        "3. The ALU performs the addition and produces 13 — it is the only unit that carries out arithmetic and logical operations.\n"
                        "4. The result is placed back in a register and then stored, again under the control unit's direction, and the program counter advances.\n"
                        "5. So the split is: ALU computes, control unit coordinates; the machine cycle is fetch → decode → execute → store → advance.\n"
                        "Most likely mistake: answering \"the CPU\" for both halves, or crediting the control unit with the arithmetic — it directs, it does not calculate."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Two pieces of code on the same laptop both control hardware directly: the graphics device driver that the operating system loads at startup, and the UEFI code that runs before any operating system starts. Which of the two is firmware, and which property decides it?"
                    ),
                    answer=(
                        "The UEFI code — it is held in non-volatile memory on the hardware itself."
                    ),
                    detail=(
                        "1. Sort by where the code lives and what it is for, not by how low-level it feels — both of these control hardware, so \"low-level\" cannot separate them.\n"
                        "2. The graphics driver is loaded from secondary storage by the operating system after startup. It belongs to system software, the category that also holds the operating system and utility programs.\n"
                        "3. The UEFI code is stored in non-volatile memory on the motherboard, is present before any operating system exists on the machine, and controls the hardware at a low level. That is the definition of firmware.\n"
                        "4. UEFI (or BIOS) is what begins startup and then hands control to the operating system.\n"
                        "5. So the driver is system software and the UEFI code is firmware; neither is application software, which performs user tasks.\n"
                        "Most likely mistake: calling a device driver application software, or calling the operating system firmware, because both \"control the hardware\"."
                    ),
                ),
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Keep this unit descriptive and comparative, not quantitative "
                "— it is scoped as CPU and GPU, input and output devices, and "
                "memory devices. Good shapes: which of CPU and GPU suits a "
                "stated workload, and why (few versatile low-latency cores "
                "against many simple parallel units); what the control unit, "
                "the ALU, the program counter and the instruction register "
                "each do; the hierarchy registers → cache → RAM → secondary "
                "storage → archival storage, fastest and smallest first; L1 "
                "against L3; DRAM against SRAM; RAM against ROM against "
                "flash; HDD against SSD by moving parts, speed and wear; "
                "whether a scanner, touchscreen, actuator or projector is "
                "input, output or both; one capacity conversion built on 1 "
                "KiB = 1 024 bytes, such as 4 GiB = 4 × 1 024³ = 4 294 967 "
                "296 bytes. Never build a card on clock speed alone."
            ),
            traps=(
                "A card treating a higher clock rate as proof of higher "
                "performance. Architecture, core efficiency, cache, memory "
                "bandwidth, software and thermal limits all decide the "
                "outcome, and one clock cycle does not necessarily equal one "
                "completed instruction — a 3.5 GHz clock produces about 3.5 "
                "billion cycles per second and nothing more can be read off "
                "it.",
                "Cache placement and volatility. Cache is fast volatile "
                "memory inside or beside the processor and counts as primary "
                "memory; it loses its contents at power-off exactly as RAM "
                "does. L1 is usually smallest and fastest, L2 larger and "
                "slower, L3 larger again and often shared among cores. A card "
                "calling cache non-volatile, placing it in secondary storage, "
                "or making L1 the largest, is wrong.",
                "Dual-role and mis-sorted peripherals. A touchscreen is both "
                "an input and an output device because it also displays "
                "information. A card presenting it as input only, or listing "
                "a printer, projector, speaker, actuator or haptic device as "
                "an input device, or a scanner, microphone or barcode reader "
                "as an output device, is wrong.",
                "Byte-unit convention mixed inside one card. This unit's own "
                "material uses IEC units — 1 byte = 8 bits, 1 KiB = 1 024 "
                "bytes, 1 MiB = 1 024 KiB, 1 GiB = 1 024 MiB — while a 1 TB "
                "drive is described as approximately one trillion bytes under "
                "the decimal convention. A card that converts an advertised "
                "drive capacity with 1 024³, or a memory size with 10⁹, or "
                "that switches convention part-way through a calculation "
                "without saying so, is wrong.",
                "SSD and HDD claims. An HDD stores data magnetically on "
                "rotating platters using a moving read/write head, giving "
                "high capacity at low cost but slower access and "
                "vulnerability to shock; an SSD uses flash with no moving "
                "parts, is faster, silent and shock-resistant, and its cells "
                "tolerate a finite number of write cycles which "
                "wear-levelling spreads out. A card calling an SSD immune to "
                "wear, or claiming either drive loses its contents at "
                "power-off, is wrong.",
                "GPU over-claim. A GPU accelerates work that divides into "
                "many similar operations on a large dataset and gains little "
                "where operations must run strictly in sequence or branch "
                "unpredictably; it does not replace the CPU, which directs "
                "general computation, branching logic and operating-system "
                "control. An integrated GPU is built into the processor "
                "package and normally shares system RAM, while a discrete GPU "
                "has its own VRAM. A card saying a GPU is simply faster than "
                "a CPU, or that a discrete card shares system RAM, is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "Two jobs each perform 8 000 000 operations. Job A multiplies every one of an image's 8 000 000 pixels by the same brightness factor. Job B follows a chain of 8 000 000 pointers, where each next address can only be read after the previous one has been loaded. Which job is the one a GPU accelerates, and why?"
                    ),
                    answer=(
                        "Job A — its 8 000 000 operations are independent, so they can run in parallel."
                    ),
                    detail=(
                        "1. Count the work first: both jobs are 8 000 000 operations, so the amount of work does not decide anything.\n"
                        "2. Ask whether the operations depend on one another. In job A a pixel's new value needs only that pixel's own old value, so all 8 000 000 multiplications could in principle be done at the same time.\n"
                        "3. In job B step n + 1 needs the address produced by step n, so the steps must happen strictly one after another however many units are available.\n"
                        "4. A GPU is many simple units applying the same operation across a large dataset, which fits job A exactly and gains nothing on job B, where the dependency chain and memory latency set the pace.\n"
                        "5. Job B stays on the CPU, whose few versatile low-latency cores are built for sequential and unpredictably branching work; the GPU does not replace the CPU in any case.\n"
                        "Most likely mistake: treating \"millions of operations\" as proof that a GPU will help, without checking whether those operations are independent of one another."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A drive is advertised as 1 TB under the decimal convention, where 1 TB = 10¹² bytes. The operating system reports capacity in GiB, where 1 GiB = 1 024³ bytes. What capacity does the operating system show, to one decimal place?"
                    ),
                    answer=(
                        "About 931.3 GiB"
                    ),
                    detail=(
                        "1. Write the advertised size in bytes under its own convention: 1 TB = 10¹² = 1 000 000 000 000 bytes.\n"
                        "2. Write the reporting unit in bytes: 1 GiB = 1 024³ = 1 073 741 824 bytes.\n"
                        "3. Divide the one by the other: 1 000 000 000 000 ÷ 1 073 741 824 = 931.322 574 6…\n"
                        "4. Round to one decimal place: 931.3 GiB.\n"
                        "5. No capacity has gone missing — the same count of bytes is being named in two different units, which is exactly why an advertised 1 TB drive reports about 931 GiB.\n"
                        "Most likely mistake: switching convention part-way through — converting the advertised figure with 1 024³ as though it were 1 TiB, and answering 1 024 GiB, or concluding the manufacturer overstated the size."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "Find the base b for which (144)ᵦ = 49₁₀."
                    ),
                    answer=(
                        "b = 5"
                    ),
                    detail=(
                        "1. Expand the numeral positionally: (144)ᵦ = 1×b² + 4×b + 4.\n"
                        "2. Set it equal to the decimal value: b² + 4b + 4 = 49.\n"
                        "3. Rearrange into standard form: b² + 4b − 45 = 0.\n"
                        "4. Factorise: (b + 9)(b − 5) = 0, so b = −9 or b = 5.\n"
                        "5. Reject b = −9: a number base must be an integer greater than 1.\n"
                        "6. Check digit legality in base 5: the numeral uses only the digits 1 and 4, and base 5 admits 0–4, so every digit is legal.\n"
                        "7. Verify: 1×25 + 4×5 + 4 = 25 + 20 + 4 = 49 ✓, so b = 5.\n"
                        "Most likely mistake: stopping at the algebra and never checking that every digit of the numeral is smaller than the base — a root that satisfies the equation is still wrong if the numeral contains a digit that base does not have."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Convert 1101.1011₂ to octal."
                    ),
                    answer=(
                        "15.54₈"
                    ),
                    detail=(
                        "1. Octal takes three bits per digit, grouped outward from the binary point in BOTH directions.\n"
                        "2. Integer part, grouped right-to-left from the point: 1 | 101, then pad the leftmost group with zeros → 001 101.\n"
                        "3. Convert each group: 001 = 1 and 101 = 5, so the integer part is 15₈.\n"
                        "4. Fractional part, grouped LEFT-TO-RIGHT from the point: 101 | 1, then pad the last group with zeros on the RIGHT → 101 100.\n"
                        "5. Convert each group: 101 = 5 and 100 = 4, so the fractional part is .54₈.\n"
                        "6. Therefore 1101.1011₂ = 15.54₈.\n"
                        "7. Check in decimal: 1101.1011₂ = 8 + 4 + 1 + 0.5 + 0.125 + 0.0625 = 13.6875, and 15.54₈ = 8 + 5 + 5/8 + 4/64 = 13.6875 ✓.\n"
                        "Most likely mistake: grouping the fraction from the RIGHT instead of from the point — that reads 1011 as 1 | 011, pads to 001 011, and gives .13₈ = 1/8 + 3/64 = 0.171875 instead of the correct .54₈ = 5/8 + 4/64 = 0.6875."
                    ),
                ),
            ),
        ),
        # --- 5 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Stay on the beginner path the syllabus names — install, "
                "local repository, add a file, commit, branch — and quote "
                "commands exactly as they would be typed. Good shapes: which "
                "command does one specific thing, among `git --version`, `git "
                "config --global user.name \"Amina Yusuf\"`, `git init`, `git "
                "status`, `git add README.md`, `git commit -m \"Add project "
                "README\"`, `git log --oneline`, `git switch -c "
                "feature/profile`, `git push -u origin feature/profile`, `git "
                "clone URL`; what the hidden `.git` directory holds and what "
                "deleting it removes; what “untracked” means; what `git add` "
                "does and does not do; and above all the staging area — stage "
                "a file, edit it again, and only another `git add` puts the "
                "new content into the commit. Ask fetch against pull, and Git "
                "against GitHub."
            ),
            traps=(
                "Saving, committing and pushing treated as one act. Saving a "
                "file does not create a commit, `git add` stages content "
                "without recording it in history, and a commit stays local "
                "until it is pushed to a configured remote. A card saying a "
                "commit uploads to GitHub, or that `git add` saves the change "
                "permanently, is wrong.",
                "Restaging. A commit records what was in the staging area for "
                "that file; if a staged file is edited again, the new content "
                "needs another `git add` before it can enter the commit, and "
                "modifications that were never staged stay in the working "
                "directory. A card saying a plain commit sweeps up every "
                "modified file, or records the newest working-tree version of "
                "a file edited after staging, is wrong.",
                "Unstaging against discarding. `git restore --staged "
                "README.md` removes the file from the staging area and leaves "
                "the working-directory copy untouched. A card claiming it "
                "deletes the file, reverts the edits, or removes the file "
                "from the project is wrong.",
                "fetch against pull against clone. `git fetch` downloads "
                "remote history without automatically integrating it into the "
                "current branch; `git pull` normally fetches and then "
                "integrates; `git clone URL` copies an existing remote "
                "repository and its history into a new local directory. A "
                "card claiming fetch updates the working copy, or that pull "
                "only downloads, is wrong.",
                "Git against GitHub, and what needs a network. Git is "
                "software installed on the machine; GitHub is a web platform "
                "that hosts Git repositories and adds pull requests, issue "
                "tracking, code review and team permissions — it is not Git "
                "itself. `git init`, `git add`, `git commit`, `git status`, "
                "`git log` and branching all work with no internet "
                "connection. GitHub command-line access uses browser-based "
                "authentication, personal access tokens or SSH keys rather "
                "than the account password. A card requiring a network for a "
                "commit is wrong.",
                "Branch facts. A branch is a movable pointer to a commit; "
                "`git switch -c feature/profile` creates and switches in one "
                "step and `git checkout -b feature/profile` is the older "
                "equivalent; the slash in `feature/profile` is a naming "
                "convention and not a directory; `git branch` lists local "
                "branches and marks the current one with an asterisk; the "
                "`-u` in `git push -u origin feature/profile` records the "
                "tracking relationship so later updates can go with a bare "
                "`git push`. A GitHub user profile is not a Git branch, and "
                "“branch profile” is not a formal Git object. A card treating "
                "the slash as a folder, or a profile page as repository "
                "history, is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "In a repository you run `git add report.txt`, then open report.txt and change a line, then run `git commit -m \"Add report\"`, with no other commands in between. Which version of report.txt does that commit record, and what does `git status` say afterwards?"
                    ),
                    answer=(
                        "The version as it was when `git add` ran; status still lists it as modified."
                    ),
                    detail=(
                        "1. `git add report.txt` copies the file's content AS IT IS AT THAT MOMENT into the staging area. It does not register a live link that keeps up with later edits.\n"
                        "2. Editing report.txt afterwards changes only the working-directory copy; the staged snapshot is untouched.\n"
                        "3. `git commit` records what is in the staging area, so the commit stores the pre-edit content that `git add` captured.\n"
                        "4. The working-directory copy and the committed copy now differ, so `git status` still shows report.txt as modified.\n"
                        "5. Getting the newer content into history needs another `git add report.txt` followed by another commit.\n"
                        "Most likely mistake: assuming a plain commit sweeps up the newest working-directory version of every file it has seen — a commit records the staging area, not the working directory."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A teammate has pushed three commits to the branch you are on. You run `git fetch origin` and nothing else. Do the three commits now show up in `git log --oneline`, and have the files in your working directory changed?"
                    ),
                    answer=(
                        "No to both — only the remote-tracking branch `origin/master` moved."
                    ),
                    detail=(
                        "1. `git fetch origin` downloads the new commits and their objects from the remote into your repository, so the history is now present locally.\n"
                        "2. It updates only the remote-tracking branch, so `git log --oneline origin/master` does show the three commits.\n"
                        "3. It does not move your own branch pointer, so a plain `git log --oneline` still ends at your last commit.\n"
                        "4. It does not touch the working directory either, so the files on disk are byte-for-byte what they were before.\n"
                        "5. `git status -sb` reports the gap explicitly as `## master...origin/master [behind 3]`.\n"
                        "6. `git pull` is the command that fetches AND THEN integrates: after it, the branch pointer moves and the working files carry the teammate's changes.\n"
                        "Most likely mistake: treating fetch and pull as the same command — fetch downloads history, pull downloads it and then integrates it into your branch."
                    ),
                ),
            ),
        ),
        # --- 6 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Aim at what the syllabus actually names: the tools, what "
                "each one is for, and the ethics. Good shapes: which named "
                "tool fits a stated job — ChatGPT or Gemini for drafting and "
                "explanation, Perplexity for web discovery with citations, "
                "NotebookLM for answers grounded in sources added to a "
                "notebook, JenniAI for academic drafting and paraphrasing; "
                "which company provides a named tool; which sector a "
                "described application belongs to (healthcare, education, "
                "transport, finance, e-commerce, agriculture); inpainting "
                "against outpainting; what training does that inference does "
                "not; what hallucination is; which single element a poor "
                "prompt is missing, scored against role, context, task, "
                "constraints and output format; which ethical principle a "
                "described misuse breaks. Never ask for a version number, a "
                "price, a benchmark score or a “best” tool."
            ),
            traps=(
                "Training against inference. Training adjusts a model's "
                "parameters using data; inference applies the trained model "
                "to a new input, such as answering a question. A card "
                "claiming a deployed assistant learns from each conversation "
                "by default, or that chatting with it updates its weights, is "
                "wrong.",
                "Hallucination. It is fluent but false output — invented "
                "statements, quotations or nonexistent citations — produced "
                "because the model predicts plausible patterns rather than "
                "verifying truth. A card calling a grammar mistake, a "
                "refusal, a slow response or an off-topic answer a "
                "hallucination is wrong.",
                "Citations and grounding treated as proof. A Perplexity "
                "citation may not fully support the sentence it is attached "
                "to, so the original page, author, date and context still "
                "have to be checked; NotebookLM's answers are tied to the "
                "sources added to the notebook and are only as complete as "
                "those sources. A card presenting either tool's output as "
                "verified, or NotebookLM as a general web search engine, is "
                "wrong.",
                "Perishable specifics. Any card carrying a model version "
                "number, a parameter count for a named product, a "
                "context-window size, a price, a release date, a benchmark "
                "score, or a “best” / “most advanced” ranking will be false "
                "within months and should be rejected even when it is "
                "accurate today — the unit's own material says exact models, "
                "features, access limits and connected services differ by "
                "version.",
                "Tokens. The taught definition is that a token may be a word, "
                "part of a word, or punctuation. A card asserting that one "
                "token is always exactly one word, always one character, or "
                "always a fixed number of characters is wrong.",
                "Inpainting against outpainting, and the scale of current AI. "
                "Inpainting replaces a selected region inside an existing "
                "image; outpainting extends the image beyond its original "
                "borders. Separately, current consumer AI systems are narrow "
                "AI, and an AI prediction is probabilistic rather than "
                "guaranteed, which is why high-impact decisions need human "
                "review. A card swapping the two editing terms, or presenting "
                "a chat assistant as human-level general intelligence, is "
                "wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "A student uploads the twelve PDFs of her own course notes and wants a tool that answers her questions from those twelve documents only, showing which document each answer came from. Among the tools this unit names, which one is built for that, and which one would answer from the open web instead?"
                    ),
                    answer=(
                        "NotebookLM for the uploaded sources; Perplexity searches the open web."
                    ),
                    detail=(
                        "1. Both tools attach sources to their answers, so \"it gives citations\" cannot tell them apart — the deciding detail is WHERE the sources come from.\n"
                        "2. NotebookLM grounds its answers in the sources the user adds to a notebook, so its scope here is exactly those twelve PDFs and its answers point back into them.\n"
                        "3. Perplexity is a web-discovery tool: it searches and returns an answer citing pages it found, which is the opposite of restricting the answer to a fixed set the user supplied.\n"
                        "4. The student's requirement is \"these twelve documents and nothing else\", so NotebookLM is the fit and NotebookLM is not a general web search engine.\n"
                        "5. In either tool a citation is a pointer, not a proof — the cited page, author and date still have to be opened and checked, because a citation may not fully support the sentence attached to it.\n"
                        "Most likely mistake: choosing the web-search tool because it also shows citations, for a question that must stay inside the user's own documents."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A student tells a chat assistant that one of its answers is wrong; it accepts the correction and answers correctly for the rest of that conversation. A week later a different student asks the same question in a new conversation and gets the original wrong answer back. Why?"
                    ),
                    answer=(
                        "The correction changed only that conversation, not the model's parameters."
                    ),
                    detail=(
                        "1. Separate the two things a model does. Training is the process that adjusts the model's parameters from data; inference is applying the already-trained model to a new input to produce an answer.\n"
                        "2. Chatting with a deployed assistant is inference. The correction became part of the context of that one conversation, which is why the rest of that conversation improved.\n"
                        "3. Nothing in that exchange rewrote any parameter, so the model itself is exactly as it was.\n"
                        "4. A new conversation begins with none of that context, so the same question meets the same unchanged model and reproduces the same answer.\n"
                        "5. That original answer is a hallucination — fluent but false output, produced because the model predicts plausible patterns rather than verifying truth — which is why its output needs checking rather than correcting.\n"
                        "Most likely mistake: assuming a deployed assistant learns from every conversation by default, so that correcting it once fixes it for everyone."
                    ),
                ),
            ),
        ),
        # --- 7 ---------------------------------------------------------
        # This sub-unit exists on the syllabus but has never had its own
        # guidance pass — it was added to the registry once the syllabus PDF
        # turned out to list seven sub-headings, not six, after the guidance
        # rewrite that produced units 1-6 had already run against the old
        # six-unit list. It is inherently thin: a named list of platforms,
        # not a body of technique, so the guidance says that plainly rather
        # than manufacturing false depth.
        UnitGuidance(
            guidance=(
                "This sub-unit is a named list of platforms, not a technique "
                "— do not manufacture depth it does not have. The only "
                "examinable fact is WHICH platform a described need actually "
                "fits: Figma for an interactive interface mock-up, GitHub for "
                "source code and its commit history, Stack Overflow for one "
                "specific coding problem answered by other programmers, "
                "GeeksforGeeks for a written tutorial on a topic, and "
                "HackerRank / HackerEarth / LeetCode for solving set coding "
                "problems to build a solved-problem record. Write cards as a "
                "short scenario needing exactly one of these, never a bare "
                "'what is X for' definition. Never ask the student to rank "
                "the platforms or to name a feature no course material gives."
            ),
            traps=(
                "Confusing a design tool with a code host: Figma is for "
                "interface mock-ups and prototypes, not for hosting or "
                "version-controlling source code — that is GitHub's job.",
                "Confusing a curated tutorial site with a Q&A site: "
                "GeeksforGeeks publishes pre-written articles explaining a "
                "topic; Stack Overflow answers one specific problem someone "
                "is stuck on right now. A general 'explain X' request belongs "
                "on the former, a specific error message on the latter.",
                "Treating HackerRank, HackerEarth and LeetCode as "
                "interchangeable with Stack Overflow. All three are for "
                "solving set coding problems to build a track record, not "
                "for asking or answering an open-ended question.",
                "Routing an entire portfolio through one platform because it "
                "is the one the course spends the most time on elsewhere — "
                "each of the five serves a distinct artefact, and a card "
                "that lets one substitute for another is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "A first-year student is building an online profile. She needs two links: one where a reviewer can click through the screens of her app's interface design in a browser with nothing installed, and one that shows the app's source code together with its commit history. Which platform named in this unit serves each?"
                    ),
                    answer=(
                        "Figma for the clickable screens; GitHub for the code and commit history."
                    ),
                    detail=(
                        "1. Sort the two artefacts by what they actually are: one is an interface design, the other is source code with a recorded history.\n"
                        "2. Figma is the browser-based interface design tool, so the screens and the links between them are made there and shared as a link the reviewer simply opens.\n"
                        "3. GitHub hosts Git repositories, so it is where the source itself lives along with commits, branches and the profile page built from that activity.\n"
                        "4. Neither substitutes for the other: a design file is not version-controlled source code, and a repository is not an interactive mock-up.\n"
                        "5. So the first link is Figma and the second is GitHub.\n"
                        "Most likely mistake: routing the whole portfolio through GitHub because it is the platform the course spends most time on, and presenting static exported images as an interactive design."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A student wants two different things. First, a written tutorial explaining how a hash table works, with worked examples she can read start to finish. Second, a specific answer from other programmers to the exact error message her own code is producing. Which platform named in this unit fits each?"
                    ),
                    answer=(
                        "GeeksforGeeks for the tutorial; Stack Overflow for the specific error."
                    ),
                    detail=(
                        "1. Separate a curated learning resource from a question-and-answer service — they look alike because both end up as pages of text about code.\n"
                        "2. GeeksforGeeks publishes structured articles and tutorials on topics, written in advance, so it answers \"explain this topic to me\".\n"
                        "3. Stack Overflow is a Q&A platform: one specific programming problem is posted and other programmers answer it, and a profile there is built from reputation earned by asking and answering.\n"
                        "4. An exact error message out of one person's own code is a specific problem nobody has written a tutorial for, so it belongs on Stack Overflow.\n"
                        "5. The practice platforms this unit also names — HackerRank, HackerEarth and LeetCode — are for solving set coding problems and building a solved-problem profile, so neither request goes there.\n"
                        "Most likely mistake: posting a general \"teach me hash tables\" question on Stack Overflow, whose content and profile model are built around one specific answerable problem."
                    ),
                ),
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
                "card, plus “which mode comes after X” and “which mode does "
                "this activity belong to”. Ask what each of the four VARK "
                "letters stands for. Use single-contrast cards for creativity "
                "against invention against innovation, focused against "
                "diffuse mode, functional fixedness against other cognitive "
                "blocks, and an iterative design workflow against a linear "
                "engineering pipeline. Given a one-line account of a design "
                "that failed, ask which step was skipped — user research, "
                "prototyping or testing. Attach names to claims: Simon on "
                "design, Rittel on wicked problems, IDEO, Stanford d.school. "
                "Cloze suits stage lists and letter expansions. Keep answers "
                "to the bare term or the ordered list."
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
            examples=(
                WorkedExample(
                    question=(
                        "A team has finished Empathize and holds forty pages of interview notes from hostel students. In the next session they open a whiteboard and begin sketching app screens. Working in the d.school model, which mode have they skipped, and what should that mode have produced?"
                    ),
                    answer=(
                        "Define — one focused point-of-view problem statement."
                    ),
                    detail=(
                        "1. The d.school model has exactly five modes, in this order: Empathize, Define, Ideate, Prototype, Test.\n"
                        "2. The team has completed Empathize, and sketching screens is Ideate spilling into Prototype.\n"
                        "3. The mode sitting between Empathize and Ideate is Define, so Define is the one that was skipped.\n"
                        "4. Define's job is to turn the raw notes into ONE focused, actionable problem statement — a point of view naming the user, the need and the insight behind it — so that ideation has a target.\n"
                        "5. Skip it and the team generates ideas for a problem it never agreed on, which surfaces later as prototypes that each solve something different.\n"
                        "Most likely mistake: placing Ideate straight after Empathize because gathering notes feels like understanding already — and treating the five modes as one strict pass, when testing routinely sends a team back to Define or Empathize."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A company sells the same solar home system it always has, built from components that already existed. It changes one thing: customers now pay in small weekly instalments by mobile money instead of a single lump sum, and sales rise sharply among households that could never pay upfront. Is this an invention or an innovation?"
                    ),
                    answer=(
                        "An innovation."
                    ),
                    detail=(
                        "1. Check what is actually new. No new device and no new technology has been created here, so nothing in this story is an invention.\n"
                        "2. Invention is the creation of something new; innovation is implementation that produces value.\n"
                        "3. What is new is a payment and delivery model, and it has been put into practice with real customers rather than proposed.\n"
                        "4. It produces value: households previously excluded by the lump-sum price now own the system, and the company sells more of them.\n"
                        "5. Implementation plus value, using existing technology, is precisely what innovation means — so this is an innovation.\n"
                        "Most likely mistake: requiring new technology before something counts as an innovation, which leads to calling a novel but never-adopted device an innovation while denying the label to a business-model change that actually worked."
                    ),
                ),
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
                "for the point-of-view template “[user] needs a way to [need] "
                "because [insight]”. Ask explicit against implicit need for a "
                "described behaviour, and whether a described friction is a "
                "pain point or a solution request. Ask whether a given "
                "interview question is open, leading, or behaviour-anchored. "
                "Answers: one term or one short template."
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
                "behaviour, a contradiction or a workaround. The syllabus "
                "names only these two (“Explicit and Implicit User Needs”), "
                "so a card built on a three-way explicit/implicit/latent "
                "choice is out of scope, even though the unit notes mention "
                "latent needs once in passing as needs that “remain "
                "unrecognized until a new possibility appears”. A card "
                "labelling a directly voiced request as an implicit need, or "
                "an inference as explicit, is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "In one session a researcher records three things: (a) the participant's exact words, \"the app is fine, honestly\"; (b) the participant closing and reopening the app three times to check a saved draft; (c) the researcher's own cautious inference that she does not believe the app has saved her work. On a four-quadrant empathy map (Says, Thinks, Does, Feels), which quadrant does each item belong in?"
                    ),
                    answer=(
                        "(a) Says, (b) Does, (c) Thinks."
                    ),
                    detail=(
                        "1. Assign by the TYPE OF EVIDENCE, not by the topic — all three items are about the same worry, so the topic cannot separate them.\n"
                        "2. (a) is a direct quotation, words the participant actually spoke, so it goes under Says.\n"
                        "3. (b) is an action the researcher watched happen, so it goes under Does.\n"
                        "4. (c) was neither spoken nor observed; it is the researcher's cautious inference about what is going on in the participant's head, so it goes under Thinks.\n"
                        "5. Notice that (a) and (c) contradict one another — a stated \"it's fine\" against an inferred distrust — and surfacing that contradiction is exactly what the map is for.\n"
                        "Most likely mistake: filing the observed behaviour under Says because the researcher wrote it down in words, or promoting the inference into Does as though it had been observed."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Asked what she needs from the billing software, a shop assistant says, \"the font should be bigger.\" The researcher then watches her keep a handwritten notebook beside the till and copy every day's total into it before going home; she never mentions the notebook. Which observation reveals an implicit need, and how should that need be written down?"
                    ),
                    answer=(
                        "The notebook: she needs a way to confirm the day's totals are right."
                    ),
                    detail=(
                        "1. An explicit need is one the user states. \"The font should be bigger\" was stated out loud, so it is explicit — and it is stated as a solution rather than as a need.\n"
                        "2. An implicit need is one inferred from behaviour, from a contradiction, or from a workaround the user has built for herself.\n"
                        "3. The notebook is a workaround: she does extra work every single day that the software was supposed to remove, and she did not raise it when asked.\n"
                        "4. Ask what the workaround buys her. Copying the totals by hand gives her a record she can check against, so the underlying need is confidence that the day's totals are correct.\n"
                        "5. Write the need as an outcome, not a feature: \"needs a way to confirm the day's totals are right\", not \"needs a printed daily summary\" — the second names one solution and closes off every other.\n"
                        "Most likely mistake: taking the spoken request as the need because it was said aloud, and then writing the need as the feature the user asked for."
                    ),
                ),
            ),
        ),
        # --- 3 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "This unit is counting, ordering and classifying — write for "
                "that. Ask which of divergent and convergent thinking a named "
                "activity belongs to, and which comes first. Ask what each "
                "SCAMPER letter stands for, and which single SCAMPER prompt a "
                "described product change uses. Ask one brainstorming rule "
                "per card, unattributed. Ask what sits at the centre of a "
                "mind map and what its branches carry; ask what reverse "
                "thinking asks first and what is then done with the answers. "
                "Ask what affinity clustering groups by and what it produces. "
                "Ask what forms the rows and what the columns of an idea "
                "screening matrix, and set short weighted-score arithmetic "
                "using Total = Σ(wᵢ × rᵢ) with real numbers worked out in "
                "detail. Ask which impact–effort quadrant a described idea "
                "falls in, and feasibility against relevance."
            ),
            traps=(
                "SCAMPER expands to Substitute, Combine, Adapt, Modify, Put "
                "to another use, Eliminate, Reverse or rearrange — seven "
                "letters, with “Reverse or rearrange” counting as one. Reject "
                "S = 'Simplify', C = 'Create', A = 'Add', M = 'Multiply', E = "
                "'Expand', R = 'Redesign' or 'Refine'. A card presenting "
                "Reverse and Rearrange as two separate letters, or splitting "
                "Modify from Magnify/Minify, is wrong.",
                "Brainstorming rule counts and attributions. The unit's own "
                "notes give FIVE core rules — defer criticism, seek quantity, "
                "welcome unusual ideas, build on others' contributions, keep "
                "one conversation active — and give them unattributed. "
                "Osborn's original set is four and does not include “one "
                "conversation at a time”, which comes from the d.school's "
                "list. A card that fixes a count, or that attributes the "
                "five-rule list to Osborn, is unsafe: the rule itself is "
                "examinable, the count and the name are not.",
                "Divergent and convergent must not be inverted. Divergent "
                "generates, suspends judgment and values quantity, variety "
                "and novelty; convergent evaluates, narrows and values "
                "relevance, coherence and justified choice. A card calling "
                "ranking or feasibility screening 'divergent', or idea "
                "generation 'convergent', is wrong, and the normal order is "
                "diverge then converge — evaluation begins only once enough "
                "variety exists.",
                "The Double Diamond by name. The unit notes describe a "
                "lowercase “double-diamond pattern” (diverge and converge "
                "while understanding the problem, then repeat while "
                "developing solutions) but never name its phases, and "
                "Discover / Define / Develop / Deliver appear nowhere in the "
                "INT335 syllabus, unit notes or question bank. Reject a card "
                "asking for the four named phases or treating them as the "
                "syllabus framework; a card on the diverge-converge-twice "
                "pattern itself is in scope.",
                "Weighted screening-matrix arithmetic and layout. Check every "
                "total against Σ(wᵢ × rᵢ) digit by digit. A widely "
                "circulating LPU-style item asks for 0.5 × 8 + 0.3 × 4 + 0.2 "
                "× 6 and keys 6.2; the correct value is 6.4, and the item's "
                "own explanation ends by saying none of its listed values is "
                "correct. Ideas form the rows and criteria the columns, "
                "ratings commonly 1 to 5 — reject a card that swaps them. A "
                "mandatory constraint such as safety, legality or ethical "
                "acceptability is a gate applied before scoring, not one more "
                "weighted column.",
                "Clustering against screening, and feasibility against "
                "relevance. Affinity clustering groups ideas by natural "
                "similarity without imposing categories in advance, names "
                "each cluster by its shared principle and produces a "
                "shortlist of concept families; it does not rank or score, "
                "and one idea may sit in more than one cluster. Feasibility "
                "asks whether an idea can be delivered with available "
                "technology, skills, time, budget and regulation; relevance "
                "asks whether it addresses the defined user problem. A card "
                "that has clustering pick a winner, or that calls a cheap, "
                "buildable idea for a problem nobody has 'highly relevant', "
                "is wrong.",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "Three ideas are screened on three criteria with weights impact 0.4, feasibility 0.35, relevance 0.25, each rated out of 10. Idea A is rated 9, 3, 8. Idea B is rated 7, 5, 9. Idea C is rated 10, 8, 9 but requires storing customer data in a way the law does not permit. Which idea goes forward, and with what weighted total?"
                    ),
                    answer=(
                        "Idea B, with a weighted total of 6.80."
                    ),
                    detail=(
                        "1. Apply the mandatory constraint FIRST. Legality is a gate, not one more weighted column, so Idea C is excluded before any scoring — no total can buy back a rule that must be met.\n"
                        "2. Score Idea A with Total = Σ(wᵢ × rᵢ): 0.4 × 9 = 3.60; 0.35 × 3 = 1.05; 0.25 × 8 = 2.00.\n"
                        "3. Add: 3.60 + 1.05 + 2.00 = 6.65.\n"
                        "4. Score Idea B: 0.4 × 7 = 2.80; 0.35 × 5 = 1.75; 0.25 × 9 = 2.25.\n"
                        "5. Add: 2.80 + 1.75 + 2.25 = 6.80.\n"
                        "6. Compare: 6.80 > 6.65, so Idea B wins even though Idea A carries the single highest rating on the heaviest criterion.\n"
                        "7. Check the weights sum to 1: 0.40 + 0.35 + 0.25 = 1.00 ✓.\n"
                        "Most likely mistake: scoring Idea C anyway and choosing it because its ratings are the highest, or picking Idea A on the strength of its 9 — the two admissible totals differ by only 0.15 and have to be worked out digit by digit."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Ten minutes into an idea-generation session, a member answers a suggestion with \"that will never get past the safety review.\" Which brainstorming rule has been broken, and at what point does that judgement properly belong?"
                    ),
                    answer=(
                        "Defer criticism; the judgement belongs in the convergent screening step."
                    ),
                    detail=(
                        "1. Idea generation is a divergent activity: it suspends judgement and values quantity, variety and novelty.\n"
                        "2. The rule the remark breaks is defer criticism — evaluation is held back so that unfinished and unusual ideas still get said out loud.\n"
                        "3. The real cost is not the one idea killed; it is the ideas nobody offers afterwards, because members start filtering themselves.\n"
                        "4. The safety objection is not wrong, it is early. Once enough variety exists the team converges: it applies mandatory constraints such as safety as gates, then screens and scores what survives.\n"
                        "5. So the order is diverge, then converge, and this remark dragged a convergent judgement into the divergent half of the session.\n"
                        "Most likely mistake: defending the objection as good convergent thinking and allowing it into the generation session, or treating it later as a permanent veto rather than a criterion to apply at screening."
                    ),
                ),
            ),
        ),
        # --- 4 ---------------------------------------------------------
        UnitGuidance(
            guidance=(
                "Aim at purpose and choice, not description. Ask which "
                "prototype fidelity suits a stated uncertainty — layout and "
                "navigation against timing, colour, trust and micro-feedback "
                "— and what question each fidelity answers. Ask what a "
                "prototype is for in one phrase (learning, exposing "
                "weakness). Ask what an MVP is in one phrase, what it is not, "
                "and the one-line difference between an MVP and a prototype. "
                "Ask what paper prototyping lets a team test in minutes and "
                "what it cannot show. Ask what a wireframe shows and what it "
                "deliberately omits, and one wireframing convention per card. "
                "Ask what a storyboard shows that a wireframe does not. Ask "
                "for the ordered happy path of a named user flow, and whether "
                "a described feature is core or peripheral. Keep answers to a "
                "term, a pair, or a short ordered list."
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
                "Out-of-scope prototyping frameworks. MoSCoW appears nowhere "
                "in the INT335 syllabus, unit notes or question bank, and "
                "neither does Wizard of Oz — reject cards built on either. "
                "Concierge appears only in the unit's question bank, defined "
                "there as manual delivery that validates demand and value but "
                "not scalability or the usability of automation; it is not a "
                "syllabus sub-topic. If a concierge card survives at all, it "
                "must not say the manual work is hidden from the user — that "
                "is the Wizard of Oz idea, and the two are opposites.",
                "A wireframe communicates layout, content placement, "
                "hierarchy and interface structure — it deliberately omits "
                "final colour, typography and imagery, and is conventionally "
                "grayscale. Reject cards saying a wireframe shows the final "
                "visual design or brand styling, or that a storyboard is a "
                "set of screens (a storyboard shows the user's context, "
                "action, system response and outcome over time).",
            ),
            examples=(
                WorkedExample(
                    question=(
                        "A paper prototype of a seat-booking flow tested well: every participant found the seat-selection step unaided. The team now needs to know whether the flow still works when the seat map takes about two seconds to load and the Confirm button greys out while it waits. Can the paper prototype answer that, and what is needed instead?"
                    ),
                    answer=(
                        "No — timing and micro-feedback need a higher-fidelity prototype."
                    ),
                    detail=(
                        "1. Match the artefact to the uncertainty being tested, not to the stage of the project.\n"
                        "2. A paper prototype tests concept, information hierarchy and screen sequence — whether people understand what the screens are and in what order they come. That is exactly the question it already answered.\n"
                        "3. The new question is about a delay, about a control changing state, and about whether the user still believes the system is working. None of that exists on paper: a person moving sheets by hand supplies the response instantly and cannot reproduce a two-second wait.\n"
                        "4. So the low-fidelity result stands for what it tested and simply does not extend to timing, response or visual credibility.\n"
                        "5. Answering the new question needs a higher-fidelity interactive prototype in which the delay and the disabled state are real.\n"
                        "Most likely mistake: reading a successful low-fidelity test as evidence that the design works overall, when it only answers the questions that fidelity was able to ask."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Team A builds one working feature, releases it, and forty paying customers use it for their real work. Team B builds a clickable mock-up of the whole app and watches eight users attempt set tasks with it in a lab. Which team has an MVP, and what does the other team have?"
                    ),
                    answer=(
                        "Team A has the MVP; Team B has a prototype."
                    ),
                    detail=(
                        "1. Ask who uses it, and for what. A prototype simulates an experience so the team can learn and find where the idea is weak; it is not handed to real customers in a real operating context.\n"
                        "2. Team B's mock-up is used in a lab, on tasks the team set, and delivers no value to the participants. That is a prototype, and covering the whole app does not change what it is.\n"
                        "3. An MVP is the smallest coherent end-to-end product that reliably delivers the core value to real users and generates evidence about one central hypothesis.\n"
                        "4. Team A's single feature is used by real customers, in their real context, and does real work for them — so it is an MVP despite being far smaller in scope.\n"
                        "5. Scope is therefore not the discriminator. \"Viable\" means it must work well enough for a real user to complete the core task, so an MVP is neither \"the version with fewest features\" nor a half-working one.\n"
                        "Most likely mistake: deciding by size — calling the whole-app mock-up the MVP because it covers more, and the one shipped feature \"just a prototype\"."
                    ),
                ),
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
                "complaint is about. Ask what a touchpoint is against a pain "
                "point, and direct against indirect touchpoints. Ask which "
                "layer of a journey map a given entry belongs to (actions, "
                "thoughts, emotions, channels, opportunities). Ask whether a "
                "given facilitator sentence is neutral or leading, and which "
                "task wording tests discoverability rather than obedience. "
                "Ask what “Show, don't tell” means in one phrase. Ask one "
                "navigation rule and one accessibility rule per card. Keep "
                "answers to a term or a short phrase."
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
            examples=(
                WorkedExample(
                    question=(
                        "A release passes every acceptance criterion in the requirements document and every test the specification asked for. In the field, users abandon the task within a week because the product solves a problem they turn out not to have. Which of verification and validation succeeded, and which failed?"
                    ),
                    answer=(
                        "Verification succeeded; validation failed."
                    ),
                    detail=(
                        "1. Verification asks whether the product meets its specification — building the thing right.\n"
                        "2. Every acceptance criterion and specified test passed, so verification succeeded: nothing in the build is defective against what was written down.\n"
                        "3. Validation asks whether the product meets the real user need — building the right thing.\n"
                        "4. Users abandoning the task because they do not have that problem is a failure of the need itself, so validation failed.\n"
                        "5. The two are independent, which is the point: a product can be built exactly to a specification that was wrong, so validation has to be done with real users and not against the document.\n"
                        "Most likely mistake: defining validation as conformance to requirements, which collapses it into verification and makes the pair impossible to tell apart."
                    ),
                ),
                WorkedExample(
                    question=(
                        "During a usability test the facilitator reads out: \"Open the Payments tab and choose Bill Pay.\" Every participant completes it. What has this task actually tested, and how should it be worded to test what the team wanted to learn?"
                    ),
                    answer=(
                        "Obedience; word it \"Pay your electricity bill.\""
                    ),
                    detail=(
                        "1. The team wanted to know whether people can find the bill-payment feature by themselves — that is discoverability.\n"
                        "2. The wording names the control and gives the route, so the participant is handed the answer before starting. A perfect completion rate proves only that the instruction was followed.\n"
                        "3. Neutral facilitation means giving the participant a goal, not a procedure: the facilitator must not demonstrate the workflow, name the control, or embed a judgement.\n"
                        "4. \"Pay your electricity bill\" states the outcome and leaves the route to the participant, so hesitations, wrong turns and failures now carry information.\n"
                        "5. The same rule rules out loaded questions afterwards: \"How useful was our convenient dashboard?\" carries its answer inside the question.\n"
                        "Most likely mistake: reading a high completion rate on a step-by-step task as evidence that the interface is discoverable."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "In a pitch a team says: \"Two other apps already send bill reminders, but neither of them works when the phone has no data connection.\" Which element of NABC does this sentence supply?"
                    ),
                    answer=(
                        "Competition."
                    ),
                    detail=(
                        "1. NABC is Need, Approach, Benefits per costs, Competition.\n"
                        "2. Need would state the user's problem; this sentence names rival products, not the problem.\n"
                        "3. Approach would state how the team solves it; no mechanism at all is described.\n"
                        "4. Benefits per costs would state the gain relative to what it costs. \"Works without data\" sounds like a benefit, but the sentence is built as a comparison against what already exists.\n"
                        "5. A sentence answering \"why is this better than the alternatives?\" is Competition, so that is the element supplied.\n"
                        "Most likely mistake: filing anything that sounds positive under Benefits, and expanding C as \"Cost\" or \"Customer\" — the cost idea already sits inside \"Benefits per costs\"."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Between test round 1 and test round 2 a team rewrote the onboarding copy, added a progress bar, and recruited its participants from a different course. Task completion rose from 55% to 80%. What may the team conclude about the progress bar?"
                    ),
                    answer=(
                        "Nothing — three things changed at once, so the rise is unattributable."
                    ),
                    detail=(
                        "1. List what changed between the two measurements: the copy, the progress bar, and the participant group. That is three variables.\n"
                        "2. The 80% is a real figure, but it is the joint result of all three changes together with whatever differs between the two groups of people.\n"
                        "3. Any single one of them could account for the whole rise; two could even be pulling in opposite directions with the third carrying it.\n"
                        "4. Nothing in the data separates the three, so no claim about the progress bar specifically is supported by it.\n"
                        "5. To attribute the effect the team must change one variable at a time — hold the copy and the recruitment fixed and test the progress bar alone.\n"
                        "Most likely mistake: reporting \"the progress bar raised completion by 25 points\" because it is the change the team is proudest of, when the design of the comparison cannot support any per-change claim."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "An HTML page contains:\n"
                        "\n"
                        "<ol reversed start=\"10\">\n"
                        "  <li>alpha</li>\n"
                        "  <li>beta</li>\n"
                        "  <li value=\"4\">gamma</li>\n"
                        "  <li>delta</li>\n"
                        "</ol>\n"
                        "\n"
                        "What marker number does the browser render beside each of the four items, in order?"
                    ),
                    answer=(
                        "10, 9, 4, 3"
                    ),
                    detail=(
                        "1. start=\"10\" sets the list's ordinal counter to 10, so the first item, alpha, is numbered 10.\n"
                        "2. reversed makes the counter step by -1 instead of +1, so beta is 10 - 1 = 9.\n"
                        "3. The third li carries value=\"4\", which overrides the counter for that item outright: gamma is numbered 4.\n"
                        "4. A value attribute also resets the counter, so counting resumes from 4 and still steps by -1: delta is 4 - 1 = 3.\n"
                        "5. Rendered markers, top to bottom: 10, 9, 4, 3.\n"
                        "Most likely mistake: reading reversed as \"display the list bottom-up\" and answering 3, 4, 9, 10, or ignoring the value attribute and answering 10, 9, 8, 7."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A page served at https://example.com/docs/guide/page.html contains <a href=\"../img/a.png?size=big#top\">. What absolute URL does that link resolve to, and what request target does the server receive when it is clicked?"
                    ),
                    answer=(
                        "Resolves to https://example.com/docs/img/a.png?size=big#top; server sees GET /docs/img/a.png?size=big"
                    ),
                    detail=(
                        "1. Relative URLs resolve against the base URL's directory, not its filename, so drop page.html: https://example.com/docs/guide/ .\n"
                        "2. The leading ../ climbs exactly one directory: https://example.com/docs/ .\n"
                        "3. Append the remainder of the relative path, img/a.png: https://example.com/docs/img/a.png .\n"
                        "4. Query and fragment ride along unchanged: https://example.com/docs/img/a.png?size=big#top .\n"
                        "5. The browser strips the fragment before it builds the request, so the request line is GET /docs/img/a.png?size=big HTTP/1.1 - the query is sent, #top is not.\n"
                        "6. Contrast: href=\"/img/a.png\" would ignore /docs/guide/ entirely and resolve to https://example.com/img/a.png .\n"
                        "Most likely mistake: counting ../ from the page file rather than from its directory, which wrongly gives /docs/guide/img/a.png, or assuming #top reaches the server."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "The user clicks the Save button in this form:\n"
                        "\n"
                        "<form action=\"/save\" method=\"get\">\n"
                        "  <input name=\"user\" value=\"ada\">\n"
                        "  <input name=\"role\" value=\"admin\" disabled>\n"
                        "  <input name=\"id\" value=\"007\" readonly>\n"
                        "  <input value=\"ghost\">\n"
                        "  <input type=\"checkbox\" name=\"news\">\n"
                        "  <input type=\"checkbox\" name=\"terms\" checked>\n"
                        "  <button type=\"submit\" name=\"action\" value=\"save\">Save</button>\n"
                        "</form>\n"
                        "\n"
                        "What exact URL does the browser request?"
                    ),
                    answer=(
                        "/save?user=ada&id=007&terms=on&action=save"
                    ),
                    detail=(
                        "1. user: an ordinary named control with a value, so it is sent as user=ada.\n"
                        "2. role: disabled controls are barred from submission entirely, so role=admin is NOT sent - even though its value is still sitting in the DOM.\n"
                        "3. id: readonly only blocks editing; the control is still submitted, so id=007 is sent.\n"
                        "4. The fourth input has a value but no name attribute. A control with no name is never submitted, so \"ghost\" is dropped.\n"
                        "5. news: an unchecked checkbox is omitted from the submission completely - it is not sent as news=off or news=.\n"
                        "6. terms: checked but with no value attribute, so it submits the default string \"on\": terms=on.\n"
                        "7. The button that was actually clicked is the submitter, and it contributes its own pair: action=save. (Calling form.submit() from script has no submitter, so action would be missing.)\n"
                        "8. Pairs are joined in document order: /save?user=ada&id=007&terms=on&action=save\n"
                        "Most likely mistake: swapping disabled and readonly - sending role=admin and dropping id=007 - or sending news=off for the unchecked box."
                    ),
                ),
                WorkedExample(
                    question=(
                        "Given <input type=\"number\" min=\"3\" max=\"20\" step=\"5\">, decide for each entered value 8, 10, 20 and 23 whether checkValidity() returns true, and name the ValidityState flag set for each failure."
                    ),
                    answer=(
                        "8 valid; 10 stepMismatch; 20 stepMismatch; 23 rangeOverflow"
                    ),
                    detail=(
                        "1. When min is present it becomes the step base, so the allowed values are 3 + 5k: 3, 8, 13, 18, 23, 28, ...\n"
                        "2. 8 = 3 + 5x1, so it is on step, and 3 <= 8 <= 20, so checkValidity() is true.\n"
                        "3. 10 - 3 = 7, and 7 is not a multiple of 5, so 10 is off step: stepMismatch is true (the browser's message names 8 and 13 as the two nearest valid values).\n"
                        "4. 20 is inside the range, but 20 - 3 = 17 is not a multiple of 5, so 20 is off step too: stepMismatch is true and rangeOverflow is false. The nearest valid value below it is 18.\n"
                        "5. 23 - 3 = 20 IS a multiple of 5, so 23 is on step - but 23 > max = 20, so stepMismatch is false and rangeOverflow is true.\n"
                        "Most likely mistake: measuring step from 0 instead of from min, which reverses the verdicts on 8 and 10, and assuming 23 fails on step when it actually fails on range."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "The pointer is hovering over the link. Which colour does it render, and what is each selector's specificity?\n"
                        "\n"
                        "<style>\n"
                        "  #main a                    { color: red; }\n"
                        "  div.card ul li a.btn:hover { color: green; }\n"
                        "  :where(#main .card) a.btn  { color: blue; }\n"
                        "</style>\n"
                        "<div id=\"main\"><div class=\"card\"><ul><li>\n"
                        "  <a href=\"#\" class=\"btn\">Docs</a>\n"
                        "</li></ul></div></div>"
                    ),
                    answer=(
                        "red - #main a scores (0,1,0,1) and wins"
                    ),
                    detail=(
                        "1. Score each selector as (a, b, c, d): a = 1 only for a style attribute, b = ID selectors, c = class, attribute and pseudo-class selectors, d = type selectors and pseudo-elements.\n"
                        "2. #main a - one ID (#main), no classes, one type (a): (0, 1, 0, 1).\n"
                        "3. div.card ul li a.btn:hover - no ID; .card, .btn and :hover give c = 3; div, ul, li and a give d = 4: (0, 0, 3, 4).\n"
                        "4. :where(#main .card) a.btn - :where() always contributes zero, so #main and .card count for nothing and only a.btn is scored: (0, 0, 1, 1).\n"
                        "5. Compare component by component from the left, with no carrying between components: b is 1 against 0 against 0, so #main a wins there and c and d are never even compared.\n"
                        "6. The element renders red, despite the other two rules appearing later in the stylesheet - source order is only consulted when specificity ties.\n"
                        "Most likely mistake: collapsing the tuple into one number (0+1+0+1 = 2 losing to 0+0+3+4 = 7) and answering green, or counting #main .card inside :where() toward the third rule's specificity."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What rendered width does each of the three flex items get?\n"
                        "\n"
                        "<style>\n"
                        "  * { margin: 0; padding: 0; }\n"
                        "  .row { display: flex; width: 600px; box-sizing: border-box; padding: 0 20px; }\n"
                        "  .row div { height: 50px; }\n"
                        "  .a { flex: 2 1 100px; }\n"
                        "  .b { flex: 1 1 100px; }\n"
                        "  .c { flex: 1 1 0%; }\n"
                        "</style>\n"
                        "<div class=\"row\"><div class=\"a\"></div><div class=\"b\"></div><div class=\"c\"></div></div>"
                    ),
                    answer=(
                        ".a = 280px, .b = 190px, .c = 90px"
                    ),
                    detail=(
                        "1. box-sizing: border-box means the declared width: 600px already includes the 20px of padding on each side, so the container's content box is 600 - 40 = 560px. That 560px, not 600px, is what gets distributed.\n"
                        "2. The third value in the flex shorthand is flex-basis, so the base sizes are 100px, 100px and 0.\n"
                        "3. Sum of base sizes = 100 + 100 + 0 = 200px, so the free space is 560 - 200 = 360px.\n"
                        "4. flex-grow factors are 2, 1 and 1, totalling 4, so one unit of growth = 360 / 4 = 90px.\n"
                        "5. .a = 100 + 2x90 = 280px; .b = 100 + 1x90 = 190px; .c = 0 + 1x90 = 90px.\n"
                        "6. Check the total: 280 + 190 + 90 = 560px, exactly filling the content box. flex-shrink never acts here, because there is free space to give out rather than an overflow to absorb.\n"
                        "Most likely mistake: splitting the free space equally (120px each) instead of in proportion to flex-grow, or distributing 600px because the padding was not subtracted first."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does console.log(null == 0, null > 0, null >= 0) print, and why is the third result different from the first two?"
                    ),
                    answer=(
                        "false false true"
                    ),
                    detail=(
                        "1. null == 0: loose equality carries a special rule for null and undefined - null is loosely equal only to null and undefined, and no numeric conversion is performed at all. So null == 0 is false.\n"
                        "2. null > 0: the relational operators have no such special rule. Both operands are converted with ToNumber, and Number(null) is 0.\n"
                        "3. So null > 0 becomes 0 > 0, which is false.\n"
                        "4. null >= 0 is specified as the negation of the corresponding less-than comparison: x >= y is true unless x < y is true.\n"
                        "5. That comparison is 0 < 0, which is false, so its negation makes null >= 0 true.\n"
                        "6. Printed: false false true.\n"
                        "Most likely mistake: reasoning that null >= 0 being true forces null == 0 to be true as well - == and the relational operators use different coercion rules, which is exactly why null == undefined is true while null == 0 is false."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A classic (non-module) <script> runs this. What does it print?\n"
                        "\n"
                        "const obj = {\n"
                        "  n: 42,\n"
                        "  reg() { return this.n; },\n"
                        "  arrow: () => this.n\n"
                        "};\n"
                        "const f = obj.reg;\n"
                        "console.log(obj.reg(), obj.arrow(), f(), f.call(obj));"
                    ),
                    answer=(
                        "42 undefined undefined 42"
                    ),
                    detail=(
                        "1. obj.reg() is a method call, so this is whatever sits to the left of the dot: obj. this.n is 42.\n"
                        "2. arrow is an arrow function, which has no this of its own - it captures this from the enclosing scope. An object literal is not a scope, so the enclosing scope is the top level of the script, where this is window.\n"
                        "3. window.n was never assigned (const obj does not create a window property either), so obj.arrow() returns undefined.\n"
                        "4. const f = obj.reg copies only the function object; the receiver is not copied with it. Calling f() is a plain call, so in this sloppy-mode classic script this is window again, and window.n is undefined. (In strict mode or an ES module this would be undefined and the line would throw a TypeError instead.)\n"
                        "5. f.call(obj) sets this explicitly to obj, so this.n is 42.\n"
                        "6. Printed: 42 undefined undefined 42.\n"
                        "Most likely mistake: expecting obj.arrow() to give 42 because the arrow is written inside the object literal - the call form, not the source position, decides this for a normal function, and an arrow ignores the call form entirely."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "The user clicks the button. In what order do the six handlers log?\n"
                        "\n"
                        "<div id=\"outer\"><div id=\"mid\"><button id=\"btn\">Go</button></div></div>\n"
                        "<script>\n"
                        "  const outer = document.getElementById(\"outer\");\n"
                        "  const mid   = document.getElementById(\"mid\");\n"
                        "  const btn   = document.getElementById(\"btn\");\n"
                        "\n"
                        "  outer.addEventListener(\"click\", () => console.log(\"outer capture\"), true);\n"
                        "  outer.addEventListener(\"click\", () => console.log(\"outer bubble\"));\n"
                        "  mid.addEventListener(\"click\", () => console.log(\"mid capture\"), true);\n"
                        "  mid.addEventListener(\"click\", () => console.log(\"mid bubble\"));\n"
                        "  btn.addEventListener(\"click\", () => console.log(\"btn one\"));\n"
                        "  btn.addEventListener(\"click\", () => console.log(\"btn two\"), true);\n"
                        "</script>"
                    ),
                    answer=(
                        "outer capture, mid capture, btn two, btn one, mid bubble, outer bubble"
                    ),
                    detail=(
                        "1. Dispatch builds the path window > document > ... > outer > mid > btn, then walks it twice: once downwards as the capturing pass, once upwards as the bubbling pass.\n"
                        "2. Capturing pass on the way down: only listeners registered with capture = true run, so outer logs \"outer capture\" and mid logs \"mid capture\". Their non-capture listeners are skipped on this pass.\n"
                        "3. At btn, event.eventPhase is 2 (AT_TARGET) - but the capturing pass still arrives there first, and on that pass only the capture-flagged listener runs. So \"btn two\" logs before \"btn one\", even though \"btn one\" was registered first.\n"
                        "4. The bubbling pass then reaches btn and runs its non-capture listener: \"btn one\".\n"
                        "5. Bubbling continues upwards through the ancestors: \"mid bubble\", then \"outer bubble\".\n"
                        "6. Final order: outer capture, mid capture, btn two, btn one, mid bubble, outer bubble. Throughout, event.target stays btn while event.currentTarget is whichever element the running listener is attached to - that difference is what makes delegation work.\n"
                        "Most likely mistake: assuming that at the target the capture flag is ignored and the two btn listeners simply run in registration order, giving \"btn one\" first. The flag still decides which pass a listener belongs to, even on the target itself."
                    ),
                ),
                WorkedExample(
                    question=(
                        "The server answers GET /api/user.json with status 404 and the body {\"error\":\"not found\"}. What does this print?\n"
                        "\n"
                        "fetch(\"/api/user.json\")\n"
                        "  .then(res  => { console.log(\"1\", res.ok, res.status); return res.json(); })\n"
                        "  .then(data => console.log(\"2\", data.error))\n"
                        "  .catch(err => console.log(\"3\", err.message))\n"
                        "  .finally(()  => console.log(\"4\"));"
                    ),
                    answer=(
                        "1 false 404, then 2 not found, then 4 - line 3 never runs"
                    ),
                    detail=(
                        "1. A 404 is a completed HTTP exchange, so the promise returned by fetch() FULFILS with a Response. Only a network-level failure - DNS failure, refused connection, a CORS block - rejects it, and that rejection is a TypeError: Failed to fetch.\n"
                        "2. So the first .then runs. res.ok is true only for statuses 200-299, so here it is false, and res.status is 404: logs \"1 false 404\".\n"
                        "3. res.json() does not hand back the parsed object; it returns a SECOND promise. Returning it from inside .then makes the chain wait for that promise to settle.\n"
                        "4. The 404 response still carries a JSON body, so that second promise fulfils with the object {error: \"not found\"}, and data.error is the string \"not found\": logs \"2 not found\".\n"
                        "5. Nothing threw and nothing rejected anywhere in the chain, so the .catch is skipped entirely - \"3\" is never logged.\n"
                        "6. .finally runs on either settle path: logs \"4\". Output is 1 false 404, then 2 not found, then 4.\n"
                        "Most likely mistake: expecting the .catch to receive the 404. To route it there you must add an explicit guard, if (!res.ok) throw new Error(\"HTTP \" + res.status); inside the first .then."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A page served from https://app.example.com makes these four calls to https://api.example.org. Which of them cause the browser to send a preflight OPTIONS request first, and why?\n"
                        "\n"
                        "1. fetch(API + \"/items\")\n"
                        "2. fetch(API + \"/items\", { method: \"POST\", headers: { \"Content-Type\": \"application/json\" }, body: JSON.stringify(item) })\n"
                        "3. fetch(API + \"/items\", { method: \"POST\", headers: { \"Content-Type\": \"application/x-www-form-urlencoded\" }, body: \"a=1\" })\n"
                        "4. fetch(API + \"/items/3\", { method: \"DELETE\" })"
                    ),
                    answer=(
                        "Calls 2 and 4 only - JSON Content-Type, and a non-safelisted method"
                    ),
                    detail=(
                        "1. A cross-origin request skips the preflight only if it is a simple request: the method is GET, HEAD or POST, AND every header the author set is CORS-safelisted.\n"
                        "2. The safelisted request headers are Accept, Accept-Language, Content-Language and Content-Type - and Content-Type counts as safelisted only when its value is application/x-www-form-urlencoded, multipart/form-data or text/plain.\n"
                        "3. Call 1 - GET with no author-set headers, so both conditions hold: simple, no OPTIONS, the GET goes straight out.\n"
                        "4. Call 2 - POST is an allowed method, but application/json is not one of the three allowed media types, so the header is not safelisted. The browser sends OPTIONS /items carrying Access-Control-Request-Method: POST and Access-Control-Request-Headers: content-type, and only sends the real POST if the server's reply approves them.\n"
                        "5. Call 3 - POST with application/x-www-form-urlencoded: method allowed and Content-Type safelisted, so it is simple. No OPTIONS, despite it being a POST with a body.\n"
                        "6. Call 4 - DELETE is not GET, HEAD or POST, so it preflights on the method alone, even though it sets no headers at all.\n"
                        "Most likely mistake: believing every POST is simple - the Content-Type value decides - or expecting the client to send Access-Control-Allow-Origin. That header comes back on the server's response; it is never a request header. A custom header such as X-Api-Key also forces a preflight, on GET as much as on POST."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this print, and in what order?\n"
                        "\n"
                        "function load() {\n"
                        "  try   { console.log(\"A\"); return \"from try\"; }\n"
                        "  catch (e) { return \"from catch\"; }\n"
                        "  finally { console.log(\"B\"); }\n"
                        "}\n"
                        "function save() {\n"
                        "  try   { throw new Error(\"disk full\"); }\n"
                        "  finally { return \"from finally\"; }\n"
                        "}\n"
                        "console.log(load());\n"
                        "console.log(save());"
                    ),
                    answer=(
                        "A, B, from try, from finally"
                    ),
                    detail=(
                        "1. load() runs its try block and logs \"A\".\n"
                        "2. return \"from try\" does not leave the function immediately: the return value is evaluated and held while the finally block is run.\n"
                        "3. finally logs \"B\", so \"B\" appears before the returned value is ever printed.\n"
                        "4. Nothing was thrown, so the catch block is skipped; load() returns \"from try\" and the outer console.log prints it. Order so far: A, B, from try.\n"
                        "5. save() throws inside try and has no catch, so the Error is on its way out of the function - but finally still runs, exactly as it does on a normal return.\n"
                        "6. That finally block executes return \"from finally\", and a return in finally replaces whatever the function was already doing, including an in-flight exception. save() therefore returns normally and the Error is discarded silently.\n"
                        "7. Full output: A, B, from try, from finally - nothing is ever thrown out of save().\n"
                        "Most likely mistake: printing \"from try\" before \"B\", or expecting save() to throw \"disk full\". Returning from finally swallowing a live exception is why linters flag it as a bug rather than a technique."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "print(-3 ** 2 // 2 + 7 % -3)"
                    ),
                    answer=(
                        "-7"
                    ),
                    detail=(
                        "1. ** binds tighter than unary minus, so -3 ** 2 means -(3 ** 2) = -9, not 9.\n"
                        "2. // and % bind tighter than +, so the expression is (-9 // 2) + (7 % -3).\n"
                        "3. -9 // 2 floors toward -infinity: the exact quotient is -4.5 and floor(-4.5) is -5, not -4.\n"
                        "4. 7 % -3 takes the sign of the DIVISOR: 7 = (-3) * (-3) + (-2), so the result is -2.\n"
                        "5. Add the two parts: -5 + (-2) = -7.\n"
                        "Most likely mistake: reading -3 ** 2 as 9, or truncating -4.5 toward zero to -4 - either slip on its own changes the printed value."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "a = 0.1 + 0.2\n"
                        "print(a == 0.3, round(a, 1) == 0.3, round(2.5) + True)"
                    ),
                    answer=(
                        "False True 3"
                    ),
                    detail=(
                        "1. Binary floating point cannot store 0.1 or 0.2 exactly, so a is 0.30000000000000004, not 0.3.\n"
                        "2. That value differs from the float literal 0.3 in the last bits, so a == 0.3 is False.\n"
                        "3. round(a, 1) rounds to one decimal place and produces exactly the float 0.3, so the second test is True.\n"
                        "4. round() with no second argument rounds halves to the nearest EVEN integer, so round(2.5) is 2, not 3 (and round(3.5) would be 4).\n"
                        "5. bool is a subclass of int, so True counts as 1 and 2 + True = 3.\n"
                        "6. print joins the three values with single spaces: False True 3.\n"
                        "Most likely mistake: asserting 0.1 + 0.2 == 0.3 is True, and expecting round(2.5) to be 3."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "for i in range(2):\n"
                        "    for j in range(3):\n"
                        "        if j == 1:\n"
                        "            break\n"
                        "        print(i, j)\n"
                        "    else:\n"
                        "        print('inner else')\n"
                        "else:\n"
                        "    print('outer else')"
                    ),
                    answer=(
                        "Three lines: 0 0, then 1 0, then outer else"
                    ),
                    detail=(
                        "1. Outer loop starts with i = 0. Inner loop j = 0: j == 1 is False, so print(i, j) writes the line 0 0.\n"
                        "2. Inner loop j = 1: the condition holds and break fires.\n"
                        "3. A for-else runs only when the loop finishes WITHOUT break, so the inner else is skipped and 'inner else' is never printed.\n"
                        "4. break leaves only the INNERMOST enclosing loop, so control returns to the outer for, which goes on to i = 1.\n"
                        "5. i = 1 repeats the same path: the line 1 0 is printed, then break again suppresses 'inner else'.\n"
                        "6. The outer for itself never executed a break, so it ends normally and its else DOES run, printing outer else.\n"
                        "Most likely mistake: thinking break ends both loops, or having for-else backwards - it runs when the loop does not break, not when it does."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "count = 0\n"
                        "for i in range(10, 0, -3):\n"
                        "    for j in range(i % 4):\n"
                        "        count += 1\n"
                        "print(i, count)"
                    ),
                    answer=(
                        "1 6"
                    ),
                    detail=(
                        "1. range(10, 0, -3) counts down from 10 and stops BEFORE the stop value 0, so it yields 10, 7, 4, 1.\n"
                        "2. i = 10: 10 % 4 = 2, so range(2) runs the body twice; count = 2.\n"
                        "3. i = 7: 7 % 4 = 3, three more iterations; count = 5.\n"
                        "4. i = 4: 4 % 4 = 0, and range(0) is empty, so the inner body never runs; count stays 5.\n"
                        "5. i = 1: 1 % 4 = 1, one iteration; count = 6.\n"
                        "6. A for loop's variable is an ordinary name that survives the loop, so after it finishes i still holds the last value used, 1.\n"
                        "7. print(i, count) therefore writes 1 6.\n"
                        "Most likely mistake: including 0 in the range (giving i = 0), or assuming i is deleted once the loop ends."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "a = [[1, 2], [3, 4]]\n"
                        "b = a[:]\n"
                        "b[0].append(9)\n"
                        "b.append([5])\n"
                        "c = a\n"
                        "c += [[7]]\n"
                        "print(a)"
                    ),
                    answer=(
                        "[[1, 2, 9], [3, 4], [7]]"
                    ),
                    detail=(
                        "1. b = a[:] is a SHALLOW copy: b is a new outer list, but b[0] is the very same inner list object as a[0].\n"
                        "2. b[0].append(9) mutates that shared inner list, so a becomes [[1, 2, 9], [3, 4]].\n"
                        "3. b.append([5]) adds an element to b's own outer list only, so a's length is unchanged: a is still [[1, 2, 9], [3, 4]].\n"
                        "4. c = a copies no data at all - it binds a second name to the SAME list object.\n"
                        "5. c += [[7]] extends that list IN PLACE, so the object a names grows: a becomes [[1, 2, 9], [3, 4], [7]].\n"
                        "6. print(a) shows [[1, 2, 9], [3, 4], [7]].\n"
                        "Most likely mistake: believing a[:] copies the inner lists too, or believing += behaves like c = c + [[7]], which would rebind c to a new list and leave a as [[1, 2, 9], [3, 4]]."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "d = {}\n"
                        "d[1] = 'a'\n"
                        "d[1.0] = 'b'\n"
                        "d[True] = 'c'\n"
                        "d['1'] = 'd'\n"
                        "print(d, len(d))"
                    ),
                    answer=(
                        "{1: 'c', '1': 'd'} 2"
                    ),
                    detail=(
                        "1. d[1] = 'a' inserts the key 1, giving {1: 'a'}.\n"
                        "2. A dict finds a key by hash and then ==. hash(1.0) == hash(1) and 1.0 == 1, so d[1.0] = 'b' hits the SAME slot: only the value is replaced, and the stored key object stays the int 1.\n"
                        "3. bool is a subclass of int, so True == 1 and hash(True) == hash(1) as well; d[True] = 'c' replaces the value once more. The dict is now {1: 'c'} - the key still displays as 1, never as True.\n"
                        "4. '1' is a str: '1' == 1 is False, so d['1'] = 'd' is a genuinely new key.\n"
                        "5. Since Python 3.7 a dict preserves INSERTION order, and key 1 kept the position it was first inserted at, so it prints {1: 'c', '1': 'd'}.\n"
                        "6. Only two distinct keys exist, so len(d) is 2.\n"
                        "Most likely mistake: counting four keys because four assignments were written, or expecting the key to be shown as True because True was assigned last."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "def add(x, box=[]):\n"
                        "    box.append(x)\n"
                        "    return box\n"
                        "\n"
                        "p = add(1)\n"
                        "q = add(2, [])\n"
                        "r = add(3)\n"
                        "print(p, q, r)\n"
                        "print(p is r, p is q)"
                    ),
                    answer=(
                        "[1, 3] [2] [1, 3] on one line, then True False"
                    ),
                    detail=(
                        "1. The default box=[] is evaluated ONCE, when the def statement runs, and stored on the function object; it is not rebuilt for each call.\n"
                        "2. add(1) uses that single default list, appending 1 to it. The default is now [1], and p is bound to that exact object.\n"
                        "3. add(2, []) supplies its own fresh list, so the default is untouched; q is [2].\n"
                        "4. add(3) falls back to the SAME default list, which already holds [1], so it becomes [1, 3] - and r is bound to that object too.\n"
                        "5. p and r are two names for one list, so print(p, q, r) shows [1, 3] [2] [1, 3]: p appears to have changed even though nothing was done to p.\n"
                        "6. p is r is True (same object) and p is q is False, so the second line is True False.\n"
                        "Most likely mistake: predicting [1] [2] [3] by assuming the default resets to [] on each call. The standard fix is box=None with box = [] if box is None inside the body."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "def g(n):\n"
                        "    print(n, end=' ')\n"
                        "    if n < 1:\n"
                        "        return n\n"
                        "    return n + g(n - 2)\n"
                        "\n"
                        "print(g(5))"
                    ),
                    answer=(
                        "5 3 1 -1 8"
                    ),
                    detail=(
                        "1. g(5) prints 5. The test 5 < 1 is False, so it returns 5 + g(3).\n"
                        "2. g(3) prints 3. 3 < 1 is False, so it returns 3 + g(1).\n"
                        "3. g(1) prints 1. Note 1 < 1 is False, so the recursion does NOT stop at 1; it returns 1 + g(-1).\n"
                        "4. g(-1) prints -1. Now -1 < 1 is True, so the base case returns n itself, which is -1. That is four calls in total.\n"
                        "5. Unwind: g(1) = 1 + (-1) = 0, then g(3) = 3 + 0 = 3, then g(5) = 5 + 3 = 8.\n"
                        "6. The four prints used end=' ', so they stay on one line, and print(g(5)) appends 8: the whole output is 5 3 1 -1 8.\n"
                        "Most likely mistake: assuming a step of -2 lands exactly on the base case and stopping at n = 1 with a return of 1, which gives 1, 4, 9 instead of 0, 3, 8."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "class Counter:\n"
                        "    count = 0\n"
                        "    items = []\n"
                        "\n"
                        "    def bump(self, x):\n"
                        "        self.count += 1\n"
                        "        self.items.append(x)\n"
                        "\n"
                        "a = Counter()\n"
                        "b = Counter()\n"
                        "a.bump('p')\n"
                        "b.bump('q')\n"
                        "print(a.count, b.count, Counter.count, Counter.items)"
                    ),
                    answer=(
                        "1 1 0 ['p', 'q']"
                    ),
                    detail=(
                        "1. count and items are CLASS attributes: created once in the class body and shared by every instance.\n"
                        "2. self.count += 1 expands to self.count = self.count + 1. The read finds no instance attribute and falls back to the class value 0, but the ASSIGNMENT creates a brand-new instance attribute a.count = 1. Counter.count is not touched.\n"
                        "3. b.bump('q') does the same for b: it again reads 0 from the class, then creates b.count = 1.\n"
                        "4. So a.count is 1 and b.count is 1 - the two calls did not accumulate to 2 - and Counter.count is still 0.\n"
                        "5. self.items.append(x) never assigns to self.items; it looks the name up (finding the class list) and MUTATES it, so both calls land in that one list.\n"
                        "6. Counter.items is therefore ['p', 'q'], and the line printed is 1 1 0 ['p', 'q'].\n"
                        "Most likely mistake: expecting count and items to behave alike - rebinding through self makes a private per-instance copy, while mutating through self does not."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "class A:\n"
                        "    def __init__(self):\n"
                        "        self.tag = 'A'\n"
                        "    def show(self):\n"
                        "        return 'A:' + self.name()\n"
                        "    def name(self):\n"
                        "        return 'a'\n"
                        "\n"
                        "class B(A):\n"
                        "    def name(self):\n"
                        "        return 'b'\n"
                        "\n"
                        "x = B()\n"
                        "print(x.show(), x.tag, type(x) == A, isinstance(x, A))"
                    ),
                    answer=(
                        "A:b A False True"
                    ),
                    detail=(
                        "1. B defines no __init__ of its own, so B() runs the inherited A.__init__, which sets x.tag = 'A'.\n"
                        "2. x.show() is not found on B either, so A.show runs - but self is still the B instance.\n"
                        "3. Inside A.show, self.name() is looked up starting at the object's actual class, B. B.name overrides A.name, so the child's version wins and returns 'b'.\n"
                        "4. A.show therefore returns 'A:' + 'b' = 'A:b'. This is dynamic dispatch: a parent method calling an overridden method gets the CHILD's implementation.\n"
                        "5. type(x) reports the exact class B and ignores inheritance, so type(x) == A is False.\n"
                        "6. isinstance(x, A) walks the inheritance chain, and B is a subclass of A, so it is True.\n"
                        "7. The line printed is A:b A False True.\n"
                        "Most likely mistake: answering 'A:a' because show() is written inside A, or expecting type(x) == A to be True for an instance of a subclass."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "What does this Python 3 program print? (d.txt does not exist beforehand.)\n"
                        "\n"
                        "with open('d.txt', 'w') as f:\n"
                        "    f.write('one\\ntwo\\nthree')\n"
                        "\n"
                        "try:\n"
                        "    f = open('d.txt')\n"
                        "    print(f.readline().strip(), f.readlines())\n"
                        "    print(f.readline() == '')\n"
                        "except FileNotFoundError:\n"
                        "    print('missing')\n"
                        "else:\n"
                        "    print('else')\n"
                        "finally:\n"
                        "    f.close()\n"
                        "    print('finally')"
                    ),
                    answer=(
                        "Four lines: one ['two\\n', 'three'] / True / else / finally"
                    ),
                    detail=(
                        "1. The file now holds exactly one\\ntwo\\nthree - three lines, with NO newline after 'three'.\n"
                        "2. print evaluates its arguments left to right, so f.readline() runs first. It returns 'one\\n', INCLUDING the trailing newline, and .strip() removes it, giving 'one'.\n"
                        "3. f.readlines() then reads from the CURRENT cursor position, not from the start, so it returns only what is left: ['two\\n', 'three'] - 'two\\n' keeps its newline, while 'three' has none because the file does not end with one.\n"
                        "4. First line printed: one ['two\\n', 'three'].\n"
                        "5. The cursor now sits at end of file, so the next f.readline() returns '' rather than re-reading line one, and the comparison prints True.\n"
                        "6. The try block raised nothing, so the else clause runs and prints else. (else runs ONLY when no exception occurred; except is skipped entirely.)\n"
                        "7. finally runs last whatever happened, closing the file and printing finally.\n"
                        "Most likely mistake: expecting readlines() to return all three lines from the start, or expecting else to run after a handled exception - it runs only when there was none."
                    ),
                ),
                WorkedExample(
                    question=(
                        "What does this Python 3 program print?\n"
                        "\n"
                        "import re\n"
                        "s = 'x12y345'\n"
                        "print(re.match(r'\\d+', s))\n"
                        "print(re.search(r'\\d+', s).group())\n"
                        "print(re.findall(r'([a-z])(\\d+)', s))\n"
                        "print(re.split(r'\\d+', s))"
                    ),
                    answer=(
                        "None, then 12, then [('x', '12'), ('y', '345')], then ['x', 'y', '']"
                    ),
                    detail=(
                        "1. re.match anchors at the START of the string. s begins with 'x', which is not a digit, so there is no match and re.match returns None - not '' and not an error. print shows None.\n"
                        "2. re.search scans the whole string and finds the first digit run at index 1, so .group() returns the matched text, the string 12.\n"
                        "3. re.findall does not return whole matches once the pattern has capturing groups: with TWO groups it returns a list of tuples of those groups, [('x', '12'), ('y', '345')]. The same pattern written without parentheses, r'[a-z]\\d+', would give ['x12', 'y345'].\n"
                        "4. re.split cuts the string at every match of r'\\d+': 'x12y345' is cut at '12' and at '345'.\n"
                        "5. That leaves the pieces before, between and after the separators: 'x', 'y', and the empty string that follows the final match, so the result is ['x', 'y', ''] - three items, the last one empty because the string ended with a separator.\n"
                        "Most likely mistake: expecting re.match to find a match anywhere like re.search does, and then calling .group() on the None it returned, which raises AttributeError."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "On a survey map, a ground area of 144 km² is represented by an area of 36 cm². Find the representative fraction of the map, and the length of a scale drawn to that RF that must measure up to 40 km."
                    ),
                    answer=(
                        "RF = 1/200 000; length of scale = 20 cm."
                    ),
                    detail=(
                        "1. Convert the ground area to cm²: 1 km = 10⁵ cm, so 1 km² = 10¹⁰ cm² and 144 km² = 144 × 10¹⁰ = 1.44 × 10¹² cm².\n"
                        "2. Form the AREA ratio: 36 / (1.44 × 10¹²) = 25 × 10⁻¹², i.e. 1/(4 × 10¹⁰).\n"
                        "3. RF is a ratio of LENGTHS, and areas scale as the square of lengths, so RF = √(25 × 10⁻¹²) = 5 × 10⁻⁶ = 1/200 000.\n"
                        "4. Length of scale = RF × the maximum length the scale must measure = (1/200 000) × 40 km.\n"
                        "5. 40 km = 4 × 10⁶ cm, so length of scale = 4 × 10⁶ / 2 × 10⁵ = 20 cm.\n"
                        "Most likely mistake: quoting the area ratio 1/(4 × 10¹⁰) itself as the RF instead of its square root, or taking RF × the object's own size instead of RF × the maximum length the scale must read."
                    ),
                ),
                WorkedExample(
                    question=(
                        "The two foci of an ellipse are 80 mm apart, and the sum of the distances of any point on the curve from the two foci is 100 mm. Find the eccentricity of the ellipse and the length of its minor axis."
                    ),
                    answer=(
                        "e = 0.8; minor axis = 60 mm."
                    ),
                    detail=(
                        "1. For an ellipse the constant SUM of the two focal distances equals the MAJOR axis, so 2a = 100 mm and the semi-major axis a = 50 mm.\n"
                        "2. The foci lie 2c apart about the centre: 2c = 80 mm, so c = 40 mm.\n"
                        "3. Eccentricity e = c/a (the same ratio as focal distance ÷ directrix distance) = 40/50 = 0.8.\n"
                        "4. For an ellipse b² = a² − c² = 50² − 40² = 2500 − 1600 = 900, so the semi-minor axis b = 30 mm.\n"
                        "5. Minor axis = 2b = 60 mm, and e = 0.8 < 1 confirms the curve is an ellipse (e = 0 circle, e = 1 parabola, e > 1 hyperbola).\n"
                        "Most likely mistake: applying the constant-DIFFERENCE rule, which belongs to the hyperbola, or writing e = c/b instead of e = c/a."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A straight line AB is 100 mm long and is inclined at 30° to the HP and 45° to the VP. Find the length of its front view, the length of its top view, and the difference in height of its two ends above the HP."
                    ),
                    answer=(
                        "Front view ≈ 70.7 mm, top view ≈ 86.6 mm, height difference 50 mm."
                    ),
                    detail=(
                        "1. The top view is the projection of the line on the HP, so its length is TL × cos(inclination to the HP) = 100 cos 30°.\n"
                        "2. 100 × 0.8660 = 86.6 mm — the top view.\n"
                        "3. The front view is the projection on the VP, so its length is TL × cos(inclination to the VP) = 100 cos 45°.\n"
                        "4. 100 × 0.7071 = 70.7 mm — the front view.\n"
                        "5. The rise of the line above the HP is TL × sin 30° = 100 × 0.5 = 50 mm, so one end is 50 mm higher than the other.\n"
                        "6. Check the data is legal: θ + φ = 30° + 45° = 75°, which cannot exceed 90°, and both views (86.6 and 70.7) are shorter than the true length, as they must be for a line inclined to both planes.\n"
                        "Most likely mistake: pairing each angle with the wrong view — using cos 30° for the front view — or using sin instead of cos, which gives the height and depth rather than the view lengths."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A point P lies 30 mm above the HP and 40 mm in front of the VP, in the first quadrant. Find (a) the distance between its front view and its top view on the drawing sheet, and (b) the shortest distance in space from P to the line of intersection of the HP and the VP."
                    ),
                    answer=(
                        "The two views are 70 mm apart; P is 50 mm from the line of intersection."
                    ),
                    detail=(
                        "1. In the first quadrant the front view p′ lies ABOVE XY by the point's height above the HP, so p′ is 30 mm above XY.\n"
                        "2. The top view p lies BELOW XY by the point's distance in front of the VP, so p is 40 mm below XY.\n"
                        "3. Both views lie on one projector perpendicular to XY, so their separation on the sheet = 30 + 40 = 70 mm.\n"
                        "4. In space, the perpendicular from P to the HP (30 mm) and the perpendicular from P to the VP (40 mm) are mutually perpendicular, so the distance from P to the line where the planes meet is √(30² + 40²).\n"
                        "5. √(900 + 1600) = √2500 = 50 mm.\n"
                        "Most likely mistake: quoting the 70 mm sheet separation as the true distance from the point to the reference line, or subtracting (40 − 30 = 10 mm), which would wrongly put both views on the same side of XY."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A machine block is drawn in FIRST-angle projection with its front view placed at the centre of the sheet. State where the top view, the view from the left and the view from below are each placed relative to the front view, and give the reason the arrangement comes out that way."
                    ),
                    answer=(
                        "Top view below, view from the left on the right, view from below above."
                    ),
                    detail=(
                        "1. In first-angle projection the object lies BETWEEN the observer and the plane of projection, so each view is pushed through the object onto the plane beyond it — every view lands on the side away from the direction you looked from.\n"
                        "2. Looking from above throws the top view onto the horizontal plane below the object; rotating the HP down about XY brings the top view BELOW the front view.\n"
                        "3. Looking from the left throws that view onto the profile plane standing on the RIGHT of the object, so the view from the left is placed to the RIGHT of the front view.\n"
                        "4. By the same rule the view from the right goes on the LEFT, and looking from below throws the bottom view ABOVE the front view.\n"
                        "5. Third-angle projection is the exact mirror of all four, because there the transparent plane lies between the observer and the object. India follows FIRST angle under BIS/IS practice; the USA and Canada use third angle.\n"
                        "Most likely mistake: placing the view from the left on the left — that is the third-angle arrangement; in first angle the left-hand view crosses over to the right."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A right regular pentagonal prism rests with one of its bases on the HP. How many faces, edges and vertices does it have, and which orthographic view is drawn first?"
                    ),
                    answer=(
                        "7 faces, 15 edges, 10 vertices; the top view is drawn first."
                    ),
                    detail=(
                        "1. A right regular n-sided prism has two identical polygonal ends plus n rectangular side faces, so F = 2 + 5 = 7.\n"
                        "2. Edges: 5 on the lower pentagon, 5 on the upper pentagon and 5 vertical lateral edges, so E = 5 + 5 + 5 = 15.\n"
                        "3. Vertices: 5 on each end polygon, so V = 5 + 5 = 10.\n"
                        "4. Check with Euler's formula: V − E + F = 10 − 15 + 7 = 2 ✓.\n"
                        "5. The base rests on the HP, so the axis is perpendicular to the HP; the view on the plane the axis is perpendicular to is drawn FIRST, i.e. the TOP view (a true regular pentagon), and the front view is projected up from it.\n"
                        "Most likely mistake: counting only the 5 rectangular faces and forgetting the two pentagonal ends, or starting with the front view — the front view is drawn first only when the axis is perpendicular to the VP."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A cast-iron pulley with four spokes is keyed to a steel shaft. A vertical cutting plane passes along the axis of the shaft, along the length of the key, and lengthwise through two opposite spokes. In the resulting sectional front view, which of the rim, hub, spokes, shaft and key are hatched, and how is that hatching drawn?"
                    ),
                    answer=(
                        "Only the rim and hub are hatched; the spokes, shaft and key are not."
                    ),
                    detail=(
                        "1. The governing rule is that a feature is left UNHATCHED when the cutting plane passes ALONG its length, and is hatched normally only when the plane cuts ACROSS it.\n"
                        "2. The plane runs lengthwise through the two spokes, so the spokes are shown in outside view, unhatched — the same convention that covers ribs and webs.\n"
                        "3. The plane runs along the axis of the shaft and along the length of the key, so shaft and key are unhatched too — as are bolts, nuts, screws, pins and rivets sectioned lengthwise.\n"
                        "4. The rim and the hub are cut ACROSS by the plane, so they are hatched: continuous THIN section lines at 45° to the principal outline, uniformly spaced.\n"
                        "5. Where two hatched parts meet, their section lines are reversed in direction or drawn at a different spacing so the joint stays readable; 30° or 60° replaces 45° only where a 45° line would run parallel to the outline. Hatching goes only where the plane actually cuts material, so the keyway void and any bolt holes stay clear.\n"
                        "Most likely mistake: hatching the spoke and the shaft because the plane physically passes through them — a longitudinally sectioned spoke, web, rib, shaft, key or bolt is never hatched."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A symmetrical cast component is to be presented in HALF SECTION. What fraction of the object is imagined removed, what line divides the sectioned half from the unsectioned half, and what do the arrows on the cutting-plane line indicate?"
                    ),
                    answer=(
                        "A quarter removed; a chain centre line divides the halves; the arrows show the direction of sight."
                    ),
                    detail=(
                        "1. A half section is produced by two cutting planes meeting at right angles on the axis, and the QUARTER between them nearest the observer is imagined taken away — one quarter, not one half.\n"
                        "2. The result is that one half of the view appears in section and the other half appears as an ordinary outside view of the same component.\n"
                        "3. The two halves are separated by a thin long-dash dotted (chain) CENTRE line, because no real edge exists along the join; a continuous thick line there would falsely read as an edge.\n"
                        "4. On the adjacent view the cutting plane is drawn as a chain THIN line made thick at its ends and at every change of direction, lettered with capitals and named, e.g. SECTION A-A.\n"
                        "5. Its end arrows give the DIRECTION OF SIGHT: everything between the observer and the plane is the material removed. The true shape of the section appears in the view projected on a plane PARALLEL to the cutting plane, and hidden lines are normally omitted in the sectional view while the remaining views are still drawn complete.\n"
                        "Most likely mistake: saying half the object is removed, drawing the divider as a continuous thick line, or reading the arrows as pointing at the portion that is thrown away rather than as the direction of sight."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A right circular cone has a base diameter of 60 mm and a vertical height of 40 mm. Find its slant height and the included angle of the sector that forms the development of its lateral surface."
                    ),
                    answer=(
                        "Slant height 50 mm; sector angle θ = 216°."
                    ),
                    detail=(
                        "1. Base radius r = 60/2 = 30 mm; vertical (axis) height h = 40 mm.\n"
                        "2. The slant height is the hypotenuse of the right triangle formed by r and h: L = √(r² + h²) = √(30² + 40²) = √(900 + 1600) = √2500 = 50 mm.\n"
                        "3. A cone takes RADIAL-LINE development: the lateral surface opens into a sector whose radius is the SLANT height, 50 mm — not r and not the axis height.\n"
                        "4. Sector angle θ = (r/L) × 360° = (30/50) × 360° = 0.6 × 360° = 216°.\n"
                        "5. Check: the sector's arc = (216/360) × 2π × 50 = 0.6 × 100π = 60π mm, and the cone's base circumference = 2πr = 2π × 30 = 60π mm — they agree ✓.\n"
                        "Most likely mistake: substituting the vertical height 40 mm for the slant height, which gives θ = (30/40) × 360° = 270°, or inverting the ratio as θ = (L/r) × 360°."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A right regular hexagonal prism of 25 mm base side and 70 mm height, and a right cylinder of 50 mm base diameter and 70 mm height, are each to have their lateral surfaces developed. Give the dimensions of each development."
                    ),
                    answer=(
                        "Prism 150 mm × 70 mm; cylinder 157.1 mm × 70 mm."
                    ),
                    detail=(
                        "1. Both solids have their generators parallel, so both take PARALLEL-LINE development, and each lateral surface opens out into a plain rectangle whose height is the solid's height, 70 mm.\n"
                        "2. Prism: the rectangle's length is the base PERIMETER = number of sides × side length = 6 × 25 = 150 mm. Development = 150 mm × 70 mm, divided by five interior fold lines at the vertical edges into six 25 mm panels.\n"
                        "3. Cylinder: the rectangle's length is the base circumference πd = π × 50 = 157.08 mm. Development = 157.1 mm × 70 mm.\n"
                        "4. Check: a regular hexagon of side 25 mm has circumradius 25 mm, so it is exactly inscribed in the cylinder's 50 mm base circle; its perimeter 150 mm must therefore be a little less than the circumference 157.1 mm ✓.\n"
                        "5. Both figures are the LATERAL surface only — the two hexagonal ends and the two circles are added separately if a closed development is wanted, and each is laid out from one seam, conventionally the shortest edge.\n"
                        "Most likely mistake: writing 2πd, πr or πd² for the cylinder's width, or using one side (25 mm) or the base area in place of the perimeter for the prism."
                    ),
                ),
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
            examples=(
                WorkedExample(
                    question=(
                        "A rectangular block measures 80 mm × 50 mm × 40 mm. Give the length to which each of the three edges is set off along the isometric axes (a) in an isometric PROJECTION of the block and (b) in an isometric VIEW (isometric drawing) of it."
                    ),
                    answer=(
                        "Projection: 65.3, 40.8, 32.6 mm. View: 80, 50, 40 mm (true lengths)."
                    ),
                    detail=(
                        "1. All three edges are parallel to the isometric axes, so all three are isometric lines and may be measured directly along those axes.\n"
                        "2. An isometric PROJECTION is set off with the isometric scale, which foreshortens every isometric line to √2/√3 = 0.8165 ≈ 0.816 of true length.\n"
                        "3. 80 × 0.816 = 65.3 mm; 50 × 0.816 = 40.8 mm; 40 × 0.816 = 32.6 mm.\n"
                        "4. An isometric VIEW (isometric drawing) is set off with TRUE lengths, so the three edges stay 80 mm, 50 mm and 40 mm.\n"
                        "5. The view is therefore the LARGER of the two, by 1/0.816 = 1.22 times — check: 65.3 × 1.22 = 79.9 ≈ 80 mm ✓. In both cases the axes themselves are 120° apart, two of them at 30° to the horizontal and one vertical.\n"
                        "Most likely mistake: using 0.866 (that is cos 30°, not the isometric scale) or applying the reduction to the isometric view — it is the PROJECTION that is reduced, and the view that is drawn full size."
                    ),
                ),
                WorkedExample(
                    question=(
                        "A hole of 40 mm diameter is drilled through the top face of a block. In an isometric PROJECTION of the block, give the lengths and directions of the major and minor axes of the ellipse representing the hole; then give the major axis the same hole would have in an isometric VIEW."
                    ),
                    answer=(
                        "Projection: major 40 mm horizontal, minor 23.1 mm vertical. View: major 48.8 mm."
                    ),
                    detail=(
                        "1. A circle lying on an isometric plane appears as an ELLIPSE, normally constructed by the four-centre method inside the rhombus that is the isometric image of the enclosing square.\n"
                        "2. In an isometric PROJECTION the ellipse's major axis equals the true diameter D, so major axis = 40 mm.\n"
                        "3. Its minor axis is 0.577D (the ratio 1/√3): 0.577 × 40 = 23.1 mm.\n"
                        "4. The MINOR axis lies along the isometric axis normal to the face carrying the circle. The top face's normal is the vertical axis, so the minor axis is vertical and the 40 mm major axis is horizontal, at right angles to it.\n"
                        "5. An isometric VIEW is 1/0.816 = 1.22 times the projection, so there the major axis becomes 1.22 × 40 = 48.8 mm and the minor axis 0.7 × 40 = 28 mm.\n"
                        "Most likely mistake: putting the MAJOR axis along the normal isometric axis — it is the minor axis that lies there — or drawing the hole as a true circle because the face it sits on is flat."
                    ),
                ),
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


def examples_text(topic_code: str, unit_number: int) -> str:
    """Two hard cards shown as few-shot calibration, or "" when unresearched.

    Formatted as the JSON shape the model is asked to reply in, not as
    prose describing that shape — an example the model has to translate out
    of prose loses the thing that made it worth showing."""
    g = guidance_for(topic_code, unit_number)
    if g is None or not g.examples:
        return ""
    shown = ",\n".join(
        "  {\"question\": %s,\n   \"answer\": %s,\n   \"detail\": %s}"
        % (json.dumps(e.question, ensure_ascii=False),
           json.dumps(e.answer, ensure_ascii=False),
           json.dumps(e.detail, ensure_ascii=False))
        for e in g.examples
    )
    return (
        "\nTwo examples of the DIFFICULTY and DEPTH this unit is examined at "
        "— not the content to reuse, the level to match:\n[\n" + shown + "\n]\n"
    )
