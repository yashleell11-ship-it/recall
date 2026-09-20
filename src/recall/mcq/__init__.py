"""Yash Made Test: a hand-curated multiple-choice bank, shared by every user.

Recall's other test mode grades cards the app generated from your own uploads.
This one sits questions written by hand per subject and unit, identical for
everybody — which is what makes a leaderboard mean anything.

`mcq_questions` is the one table in the app with no `user_id`: it is course
content, like the registry in `recall.lpu`, not something a user owns.
Everything a user *does* with it — attempts and answers — is scoped by
`user_id` exactly as the rest of the app is.
"""
