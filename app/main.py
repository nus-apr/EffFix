import multiprocessing as mp
import os
import shutil
import signal
import traceback

from app import (
    analyzer,
    configuration,
    definitions,
    emitter,
    logger,
    repair,
    utilities,
    validation,
    values,
)
from app.result import result

stop_event = mp.Event()


def create_init_directories_and_files():
    # paths used in both stages
    values.DIR_CODEQL_DB = os.path.join(values.DIR_RUNTIME_PRE, "codeql-db")
    values.DIR_INFER_OUT_WHOLE = os.path.join(values.DIR_RUNTIME_PRE, "infer-out-whole")

    values.DIR_INFER_OUT_SINGLE = os.path.join(
        values.DIR_RUNTIME_REPAIR, "infer-out-single"
    )
    values.DIR_INFER_OUT_VALIDATION = os.path.join(
        values.DIR_RUNTIME_REPAIR, "infer-out-validation"
    )
    values.INFER_CHANGED_FILES = os.path.join(
        values.DIR_RUNTIME_REPAIR, "changed-files"
    )
    values.DIR_ALL_PATCHES = os.path.join(values.DIR_RUNTIME_REPAIR, "all-patches")
    values.DIR_FINAL_PATCHES = os.path.join(values.DIR_RUNTIME_REPAIR, "final-patches")

    if values.TOOL_STAGE == "pre":
        utilities.remove_dir_if_exists(values.DIR_RUNTIME_PRE)
        os.makedirs(values.DIR_RUNTIME_PRE)

    else:  # repair stage
        utilities.remove_dir_if_exists(values.DIR_RUNTIME_REPAIR)
        os.makedirs(values.DIR_RUNTIME_REPAIR)

        # backup the fix file
        values.FIX_FILE_PATH_ORIG = os.path.join(
            values.CONF_DIR_SRC_BUILD, values.CONF_BUG_FILE
        )
        bug_file_short_name = os.path.basename(values.CONF_BUG_FILE)
        values.FIX_FILE_PATH_BACKUP = os.path.join(
            values.DIR_RUNTIME_REPAIR, bug_file_short_name + ".backup"
        )
        shutil.copyfile(values.FIX_FILE_PATH_ORIG, values.FIX_FILE_PATH_BACKUP)

        if not os.path.isdir(values.DIR_INFER_OUT_WHOLE):
            utilities.error_exit(
                "In repair stage, but the Infer analysis result seems not there."
            )

        # clean up directories (from previous consecutive repair runs), just in case
        utilities.remove_dir_if_exists(values.DIR_INFER_OUT_SINGLE)
        utilities.remove_dir_if_exists(values.DIR_INFER_OUT_VALIDATION)
        utilities.remove_dir_if_exists(values.DIR_ALL_PATCHES)
        utilities.remove_dir_if_exists(values.DIR_FINAL_PATCHES)


def timeout_handler(signum, frame):
    emitter.error("TIMEOUT Exception")
    raise Exception("end of time")


def shutdown(signum, frame):
    global stop_event
    emitter.warning("Exiting due to Terminate Signal")
    stop_event.set()
    raise SystemExit


def load_dependency_tools():
    values.INFER_PATH = shutil.which("infer")


def print_startup_info():
    """
    Read command line arguments and configuration file./
    """
    emitter.header(
        "Starting "
        + values.TOOL_NAME
        + " (Static Analysis Repair)"
        + " --- Stage: "
        + values.TOOL_STAGE
    )
    emitter.sub_title("Displaying Configurations")
    configuration.print_configuration()
    emitter.sub_title("Loading dependency tools")
    load_dependency_tools()


def run_pre():
    """
    This component involves running Infer for bug detection, and also createing CodeQL database.
    """
    configuration.read_conf_file()
    create_init_directories_and_files()

    logger.create(values.DIR_RUNTIME_PRE)
    print_startup_info()

    utilities.global_timer.start(definitions.DURATION_PREANALYSIS)
    analyzer.pre_analyze()
    utilities.global_timer.stop(definitions.DURATION_PREANALYSIS)


def run_repair():
    configuration.read_conf_file()
    create_init_directories_and_files()

    logger.create(values.DIR_RUNTIME_REPAIR)
    print_startup_info()

    utilities.global_timer.start(definitions.DURATION_ANALYSIS)
    fix_loc_lines, return_stmts, labels = analyzer.analyze()
    utilities.global_timer.stop(definitions.DURATION_ANALYSIS)

    utilities.global_timer.start(definitions.DURATION_REPAIR)
    all_remaining_time = utilities.global_timer.get_total_remaining_time()
    time_for_each_loc = all_remaining_time / len(fix_loc_lines)
    all_cluster_managers = []
    for fix_loc_line in fix_loc_lines:
        cluster_manager = repair.repair(
            fix_loc_line, return_stmts, labels, time_for_each_loc
        )
        all_cluster_managers.append(cluster_manager)
    repair.print_repair_stats(all_cluster_managers)
    utilities.global_timer.stop(definitions.DURATION_REPAIR)

    utilities.global_timer.start(definitions.DURATION_VALIDATION)
    validation.validate(all_cluster_managers)
    utilities.global_timer.stop(definitions.DURATION_VALIDATION)

    result.to_json(os.path.join(values.DIR_RUNTIME_REPAIR, "result.json"))


def cleanup():
    """
    Final cleanup rountine in case an error happens.
    """
    if values.TOOL_STAGE == "pre":
        return

    if values.FIX_FILE_PATH_BACKUP and os.path.isfile(values.FIX_FILE_PATH_BACKUP):
        shutil.copyfile(values.FIX_FILE_PATH_BACKUP, values.FIX_FILE_PATH_ORIG)


def main():
    is_error = False
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.signal(signal.SIGTERM, shutdown)

    configuration.read_args()

    utilities.global_timer.start(definitions.DURATION_TOTAL)
    utilities.global_timer.set_overall_start_time()
    try:
        if values.TOOL_STAGE == "pre":
            run_pre()
        else:
            run_repair()

    except Exception as e:
        is_error = True
        emitter.error("Runtime Error")
        emitter.error(str(e))
        emitter.error(str(traceback.format_exc()))
        logger.error(traceback.format_exc())

    finally:
        # Final running time and exit message
        emitter.title("Finalizing and exiting tool")
        cleanup()
        utilities.global_timer.stop(definitions.DURATION_TOTAL)
        time_info = utilities.global_timer.get_time_info()
        emitter.end(time_info, is_error)
        logger.end(time_info, is_error)

        if is_error:
            exit(1)
        exit(0)
