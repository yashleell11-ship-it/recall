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
                "\"saddle\" and \"inconclusive\" both get drilled. The second "
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
