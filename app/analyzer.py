import os

from app import codeql, definitions, emitter, infer, utilities, values
from app.equivalence.cluster import ClusterManager
from app.localization import localizer
from app.result import result


def config_program():
    os.chdir(values.CONF_DIR_SRC)
    utilities.execute_command(values.CONF_COMMAND_CONFIG)


def pre_analyze():
    emitter.title("Pre-analyzing Program")

    # (1) config program
    utilities.global_timer.start(definitions.DURATION_CONFIG_PROG)
    emitter.sub_title("Configuring Target Program")
    config_program()
    utilities.global_timer.stop(definitions.DURATION_CONFIG_PROG)

    # NOTE: must run Infer last, since we want to preserve the built artifacts
    # for later stage

    # (2) build codeql database
    utilities.global_timer.start(definitions.DURATION_CODEQL_CAPTURE)
    emitter.sub_title("Generating codeql database for target program")
    codeql.create_db()
    utilities.global_timer.stop(definitions.DURATION_CODEQL_CAPTURE)

    # (3) run infer on the original buggy program
    utilities.global_timer.start(definitions.DURATION_INFER_DETECTION)
    emitter.sub_title("Running Infer on Whole Program")
    infer.infer_whole_program()
    utilities.global_timer.stop(definitions.DURATION_INFER_DETECTION)


def analyze():
    emitter.title("Analyzing Program for Repair")

    # (1) check whether the target bug is detected by Infer
    emitter.sub_title("Checking whether Infer detected the target bug")
    infer_report_path = infer.get_infer_whole_program_report()
    (
        values.TARGET_BUG,
        values.TOTAL_NUM_BUGS,
    ) = infer.identify_target_bug_in_unpatched_prog(infer_report_path)
    if values.TARGET_BUG is None:
        utilities.error_exit(
            "Target bug not found by Infer analysis. "
            "This is likely because the Infer bug trace has start and end location in "
            "different function, which is not supported by EffFix now."
        )
    else:
        emitter.information("Target bug is: " + str(values.TARGET_BUG))

    assert values.TARGET_BUG is not None

    # (2) get fix locations
    utilities.global_timer.start(definitions.DURATION_LOCALIZATION)
    emitter.sub_title("Performing fix localization")

    summary_json_path = infer.infer_target_function()
    if summary_json_path is None:
        utilities.error_exit("Infer did not produce a summary file for localization.")

    assert summary_json_path is not None

    fix_loc_lines = localizer.localize(summary_json_path, values.TARGET_BUG)
    if not fix_loc_lines:
        utilities.error_exit("No fix locations found.")

    result.fix_locations(fix_loc_lines)
    utilities.global_timer.stop(definitions.DURATION_LOCALIZATION)

    # (2-1) at the same time, store the original function signature
    values.TARGET_BUG_SIG = ClusterManager.get_patch_sig_from_summary(summary_json_path)
    emitter.information("Target bug signature: " + str(values.TARGET_BUG_SIG))

    # (3) get patch ingredients that are idependent of fix location
    utilities.global_timer.start(definitions.DURATION_CODEQL_RETURN_STMTS)
    emitter.information("[Codeql] Running patch ingredient (return stmts) query")
    codeql.run_return_stmts_query(values.TARGET_BUG.procedure)
    return_stmts = codeql.parse_return_stmts_query_result()
    emitter.highlight("Return statements: " + str(return_stmts))
    result.returns(return_stmts)
    utilities.global_timer.stop(definitions.DURATION_CODEQL_RETURN_STMTS)

    utilities.global_timer.start(definitions.DURATION_CODEQL_LABELS)
    emitter.information("[Codeql] Running patch ingredient (labels) query")
    codeql.run_labels_query(values.TARGET_BUG.procedure)
    labels = codeql.parse_labels_query_result()
    emitter.highlight("Labels: " + str(labels))
    result.labels(labels)
    utilities.global_timer.stop(definitions.DURATION_CODEQL_LABELS)

    return fix_loc_lines, return_stmts, labels
