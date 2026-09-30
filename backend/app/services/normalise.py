"""Text normalisation shared by requests and the CSV importer, so that a
request for "Pick  Cup" matches episodes recorded as "pick cup"."""


def normalise_task_name(value):
    # split() with no argument also collapses tabs and repeated spaces.
    return " ".join(value.split()).lower()
