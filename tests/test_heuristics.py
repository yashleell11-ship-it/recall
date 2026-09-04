from recall.generate.generate import Candidate
from recall.verify.heuristics import check_answerable, check_atomic


def qa(q, a):
    return Candidate("qa", q, a)


def test_good_card_passes_both_gates():
    c = qa("What is the average time complexity of quicksort?", "O(n log n)")
    assert check_answerable(c) is None
    assert check_atomic(c) is None


def test_essay_prompts_are_rejected():
    assert check_answerable(qa("Discuss the merits of quicksort.", "It is fast"))
    assert check_answerable(qa("Explain in detail how quicksort works.", "..."))
    assert check_answerable(qa("List all sorting algorithms.", "..."))


def test_very_long_answer_is_not_answerable():
    assert check_answerable(qa("What is quicksort?", " ".join(["word"] * 60)))


def test_tiny_question_rejected():
    assert check_answerable(qa("Why?", "Because"))


def test_compound_question_is_not_atomic():
    assert check_atomic(qa("What is quicksort and what is mergesort?", "Both sorts"))


def test_two_question_marks_is_not_atomic():
    assert check_atomic(qa("What is X? What is Y?", "Things"))


def test_semicolon_answer_is_not_atomic():
    assert check_atomic(qa("What are the steps involved?", "First do A; then do B"))


def test_cloze_with_multiple_deletions_is_not_atomic():
    c = Candidate("cloze", "q", "a", "The {{c1::first}} and the {{c2::second}}.")
    assert check_atomic(c)


def test_cloze_with_one_deletion_is_atomic():
    c = Candidate("cloze", "question here", "a", "The {{c1::only}} one.")
    assert check_atomic(c) is None
