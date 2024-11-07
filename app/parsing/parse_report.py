"""
Parse raw Infer bug reports.
"""

import json


class PulseBug:
    def __init__(
        self,
        type: str,
        orig_line: int,
        orig_column: int,
        procedure: str,
        file: str,
        key: str,
        start_line: int,
        end_line: int,
    ):
        self.type = type
        # this is where error was detected; this number will likely change
        # after patch is added to the program
        self.orig_line = orig_line
        self.orig_column = orig_column
        self.procedure = procedure
        self.file = file
        # format: file|procedure|bug_type
        self.key = key
        # line number where taint analysis should start
        # this is the start line of the buggy trace
        self.start_line = start_line
        # this is the end line of the buggy trace
        self.end_line = end_line

    def __eq__(self, __o: object) -> bool:
        return (
            isinstance(__o, PulseBug)
            and self.file == __o.file
            and self.start_line == __o.start_line
            and self.end_line == __o.end_line
        )

    def __hash__(self):
        return hash((self.file, self.start_line, self.end_line))

    def __str__(self):
        res = (
            self.type
            + ", "
            + self.file
            + ", "
            + self.procedure
            + ", "
            + str(self.start_line)
            + ", "
            + str(self.end_line)
        )
        return res


def parse_bug_start_end_line(report_json):
    """
    We use this information for two purposes:
        (1) As a unique indentifier for each bug
        (2) The start line is the source location for taint analysis, in patch variable extraction.
    """
    start_line = -1
    end_line = -1

    trace = report_json["bug_trace"]
    if len(trace) > 0:
        start_frame = trace[0]
        end_frame = trace[-1]
        start_line = int(start_frame["line_number"])
        end_line = int(end_frame["line_number"])

    return start_line, end_line


def parse(report_file: str) -> list[PulseBug]:
    with open(report_file) as f:
        report_json = json.load(f)

    parsed_bugs = []

    for report in report_json:
        bug_type = report["bug_type"]
        orig_line = int(report["line"])
        orig_column = int(report["column"])
        procedure = report["procedure"]
        file = report["file"]
        key = report["key"]

        start_line, end_line = parse_bug_start_end_line(report)

        pulse_bug = PulseBug(
            bug_type, orig_line, orig_column, procedure, file, key, start_line, end_line
        )
        parsed_bugs.append(pulse_bug)

    return parsed_bugs
