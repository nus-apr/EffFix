"""
Handles all the calls to Infer.
"""

import os
import shutil

from app import utilities, values
from app.parsing import parse_report


def identify_target_bug_in_unpatched_prog(report_json_path):
    """
    Identify the bug to be fixed, from the whole-program report.
    :return: the bug to be fixed, or None. Also the number of bugs in the report.
    """
    pulse_bugs = parse_report.parse(report_json_path)
    target_bug = None

    for bug in pulse_bugs:
        if (
            bug.type == values.CONF_BUG_TYPE
            and bug.procedure == values.CONF_BUG_PROC
            and bug.file == values.CONF_BUG_FILE
            and bug.start_line == values.CONF_BUG_START_LINE
            and bug.end_line == values.CONF_BUG_END_LINE
        ):
            target_bug = bug
            break
    return target_bug, len(pulse_bugs)


def build_common_infer_cmd():
    """
    Helper for constructing various Infer commands.
    """
    cmd = values.INFER_PATH + " --pulse-only --jobs 16 "
    if values.CONF_PULSE_ARGS:
        cmd += values.CONF_PULSE_ARGS
    cmd_list = cmd.split(" ")
    return cmd_list


def infer_whole_program():
    """
    Run Infer on the entire program to get bug reports.
    """
    os.chdir(values.CONF_DIR_SRC_BUILD)

    # first clean the build
    utilities.execute_command(values.CONF_COMMAND_CLEAN)
    # next clean possible Infer output from previous runs
    utilities.remove_dir_if_exists(values.DIR_INFER_OUT_WHOLE)

    cmd_list = build_common_infer_cmd()
    cmd_list += ["-o", values.DIR_INFER_OUT_WHOLE, "--"]
    cmd = " ".join(cmd_list)
    cmd += " "
    cmd += values.CONF_COMMAND_BUILD_PROJECT

    utilities.execute_command(cmd)


def get_infer_whole_program_report():
    """
    Get path to the report, abort if not found.
    """
    report_json_path = os.path.join(values.DIR_INFER_OUT_WHOLE, "report.json")
    if not os.path.exists(report_json_path):
        utilities.error_exit(
            "Running Infer on the whole program did not produce a report file."
        )
    return report_json_path


def infer_validation_whole_program():
    """
    Run Infer on the entire program to get bug reports.
    But now we use a different out directory, to avoid polluting the original whole analysis.
    """
    os.chdir(values.CONF_DIR_SRC_BUILD)

    # first clean the build
    utilities.execute_command(values.CONF_COMMAND_CLEAN)
    # next clean possible Infer output from previous runs
    utilities.remove_dir_if_exists(values.DIR_INFER_OUT_VALIDATION)

    cmd_list = build_common_infer_cmd()
    cmd_list += ["-o", values.DIR_INFER_OUT_VALIDATION, "--"]
    cmd = " ".join(cmd_list)
    cmd += " "
    cmd += values.CONF_COMMAND_BUILD_PROJECT

    utilities.execute_command(cmd)

    report_json_path = os.path.join(values.DIR_INFER_OUT_VALIDATION, "report.json")
    if not os.path.exists(report_json_path):
        utilities.error_exit(
            "Running Infer on the whole program (validation) did not produce a report file."
        )
    return report_json_path


def infer_target_function():
    """
    Run Infer on ONE target function to get summary post report.
    :return: path to the generated summary file (json); None if a summary
             file is not produced.
    """
    os.chdir(values.CONF_DIR_SRC_BUILD)

    # if first time running single function analysis, copy over results
    # from whole program analysis, so that the database can be reused.
    if not os.path.exists(values.DIR_INFER_OUT_SINGLE):
        shutil.copytree(values.DIR_INFER_OUT_WHOLE, values.DIR_INFER_OUT_SINGLE)

    cmd_list = build_common_infer_cmd()
    cmd_list += [
        "--reactive",
        "--pulse-fix-mode",
        "--pulse-fix-file=" + values.CONF_BUG_FILE,
        "--pulse-fix-function=" + values.CONF_BUG_PROC,
        "-o",
        values.DIR_INFER_OUT_SINGLE,
        "--",
    ]
    cmd = " ".join(cmd_list)
    cmd += " "
    cmd += values.CONF_COMMAND_BUILD_REPAIR

    utilities.execute_command(cmd, allow_failure=True)

    # every time a summary file is produced, move it to runtime directory
    old_path = os.path.join(values.CONF_DIR_SRC_BUILD, values.SUMMARY_FILE_NAME)
    if not os.path.exists(old_path):
        return None

    new_path = os.path.join(values.DIR_RUNTIME_REPAIR, values.SUMMARY_FILE_NAME)
    if os.path.isfile(new_path):
        os.remove(new_path)

    shutil.move(old_path, new_path)

    return new_path
