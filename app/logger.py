import datetime
import time
from os.path import join as pjoin

from app import definitions, utilities, values

dir_log_base = ""
file_log_main = ""
file_log_cmd = ""
file_log_err = ""
file_log_result = ""


def create(dir_runtime: str):
    global dir_log_base, file_log_main, file_log_cmd, file_log_err, file_log_result
    dir_log_base = pjoin(dir_runtime, "logs")

    utilities.remove_and_create_new_dir(dir_log_base)

    file_log_main = pjoin(dir_log_base, "main.log")
    file_log_cmd = pjoin(dir_log_base, "command.log")
    file_log_err = pjoin(dir_log_base, "error.log")
    file_log_result = pjoin(dir_log_base, "result.log")

    header_str = (
        "[Start] "
        + values.TOOL_NAME
        + " started at "
        + str(datetime.datetime.now())
        + "\n"
    )

    for file in [file_log_main, file_log_result, file_log_cmd, file_log_err]:
        with open(file, "w+") as f:
            f.write(header_str)


def log(log_message):
    log_message = "[" + str(time.asctime()) + "]" + log_message
    if "COMMAND" in log_message:
        with open(file_log_cmd, "a") as log_file:
            log_file.write(log_message)
    with open(file_log_main, "a") as log_file:
        log_file.write(log_message)


def log_result(log_message):
    with open(file_log_result, "a") as log_file:
        log_file.write(log_message)


def information(message):
    """
    Assuming that all things related to results should be written here.
    """
    message = str(message).strip()
    log_result(message + "\n")
    message = "[INFO]: " + str(message) + "\n"
    log(message)


def command(message):
    message = str(message).strip().replace("[command]", "")
    message = "[COMMAND]: " + str(message) + "\n"
    log(message)


def error(message):
    with open(file_log_err, "a") as last_log:
        last_log.write(str(message) + "\n")
    message = str(message).strip().replace("[error]", "")
    message = "[ERROR]: " + str(message) + "\n"
    log(message)


def note(message):
    message = str(message).strip().replace("[note]", "")
    message = "[NOTE]: " + str(message) + "\n"
    log(message)


def configuration(message):
    message = str(message).strip().replace("[config]", "")
    message = "[CONFIGURATION]: " + str(message) + "\n"
    log(message)


def output(message):
    message = str(message).strip()
    message = "[LOG]: " + message
    log(message + "\n")


def warning(message):
    message = str(message).strip().replace("[warning]", "")
    message = "[WARNING]: " + str(message) + "\n"
    log(message)


def end(time_info, is_error=False):
    output("\nTime duration\n----------------------\n\n")

    if is_error:
        output(
            values.TOOL_NAME
            + " exited with an error after "
            + time_info[definitions.DURATION_TOTAL]
            + " seconds"
        )
    else:
        output(
            values.TOOL_NAME
            + " (Stage: "
            + values.TOOL_STAGE
            + ")"
            + " finished successfully after "
            + time_info[definitions.DURATION_TOTAL]
            + " seconds"
        )
    log(
        "[END] "
        + values.TOOL_NAME
        + " ended at  "
        + str(datetime.datetime.now())
        + "\n\n"
    )
