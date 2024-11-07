import json
import math

from app import codeql, definitions, emitter, values
from app.equivalence.cluster import DisjunctLabel
from app.parsing.parse_report import PulseBug
from app.parsing.parse_summary import PulseDisjunctParser


def ochiai(
    labelled_traces: list[tuple[DisjunctLabel, list[str]]], num_res: int = 10
) -> list[tuple[int, float]]:
    """
    Perform ochiai fault localization on a give set of traces.
    :param labelled_traces: list of traces with labels.
    :param num_res: number of top candidates locations to be returned.
    :return: list of suspicious locations (line numbers).
    """
    total_pass = 0
    total_fail = 0
    # dict from line to (#pass tests exec this line, #fail tests exec this line)
    line_stats = {}
    # dict from line to its corresponding ochiai score
    ochiai_scores = {}

    assert values.TARGET_BUG is not None

    for label, trace in labelled_traces:
        label_is_this_bug = label.is_showing_pulse_bug(values.TARGET_BUG)
        if label_is_this_bug:
            total_fail += 1
        else:
            total_pass += 1

        for line in trace:
            if line not in line_stats:
                line_stats[line] = (0, 0)

            old_pass, old_fail = line_stats[line]
            if label_is_this_bug:
                line_stats[line] = (old_pass, old_fail + 1)
            else:
                line_stats[line] = (old_pass + 1, old_fail)

    for line in line_stats:
        presence_in_pass, presence_in_fail = line_stats[line]
        score = presence_in_fail / math.sqrt(
            total_fail * (presence_in_pass + presence_in_fail)
        )
        ochiai_scores[line] = score

    sorted_ochiai = dict(
        sorted(ochiai_scores.items(), key=lambda item: item[1], reverse=True)
    )

    sorted_list = [(k, v) for k, v in sorted_ochiai.items()]
    # convert line from str to int
    sorted_list = [(int(line), score) for line, score in sorted_list]

    return sorted_list


def localize(
    summary_json_file: str, target_bug: PulseBug, top_k: int = 10
) -> list[int]:
    func = target_bug.procedure
    start_line = target_bug.start_line
    end_line = target_bug.orig_line
    bug_type = target_bug.type

    with open(summary_json_file) as f:
        summary_post_json = json.load(f)

    all_traces = []

    for _, disjunct in enumerate(summary_post_json):
        parser = PulseDisjunctParser(disjunct)
        label_text, bug_start_line, bug_end_line, trace = (
            parser.parse_disjunct_trace_only()
        )
        label = DisjunctLabel(label_text, bug_start_line, bug_end_line)
        all_traces.append((label, trace))

    # (1) do ochiai
    ochiai_list = ochiai(all_traces, num_res=top_k)
    emitter.information(f"Result from ochiai: {ochiai_list}")

    # (2) do some filtering based on CFG
    loc_allowed = set()
    if bug_type == definitions.BUG_TYPE_LEAK:
        # to fix leak, location has to be after the last-access point
        codeql.run_loc_after_query(func, start_line, end_line)
        loc_after_both = codeql.parse_loc_after_query_result()
        loc_allowed = set(loc_after_both)
    elif bug_type == definitions.BUG_TYPE_NULLPTR:
        # to fix npe, location has to be before where the npe happens
        codeql.run_loc_between_query(func, start_line, end_line)
        loc_between = codeql.parse_loc_between_query_result()
        loc_allowed = set(loc_between)

    emitter.information(
        f"Locations allowed (by considering trace start and trace end): {loc_allowed}"
    )
    ochiai_allowed = [
        (line, score) for line, score in ochiai_list if line in loc_allowed
    ]

    # only take those with highest scores
    final_locs = []
    highest_score = 0
    for line, score in ochiai_allowed:
        if score > highest_score:
            highest_score = score
            final_locs = [line]
        elif score == highest_score:
            final_locs.append(line)

    emitter.information(f"Final locations: {final_locs}")
    return final_locs
