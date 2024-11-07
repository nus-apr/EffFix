import os
import sys
import textwrap

from app import definitions, logger, values

rows, columns = 600, 600
res = os.popen("stty size", "r").read().split()
if res:
    rows, columns = res

GREY = "\t\x1b[1;30m"
RED = "\t\x1b[1;31m"
GREEN = "\x1b[1;32m"
YELLOW = "\t\x1b[1;33m"
BLUE = "\t\x1b[1;34m"
ROSE = "\t\x1b[1;35m"
CYAN = "\x1b[1;36m"

PROG_OUTPUT_COLOR = "\t\x1b[0;30;47m"
STAT_COLOR = "\t\x1b[0;32;47m"


def write(print_message, print_color, new_line=True, prefix=None, indent_level=0):
    if not values.silence_emitter:
        message = "\033[K" + print_color + str(print_message) + "\x1b[0m"
        if prefix:
            prefix = "\033[K" + print_color + str(prefix) + "\x1b[0m"
            len_prefix = ((indent_level + 1) * 4) + len(prefix)
            wrapper = textwrap.TextWrapper(
                initial_indent=prefix,
                subsequent_indent=" " * len_prefix,
                width=int(columns),
            )
            message = wrapper.fill(message)
        sys.stdout.write(message)
        if new_line:
            r = "\n"
            sys.stdout.write("\n")
        else:
            r = "\033[K\r"
            sys.stdout.write(r)
        sys.stdout.flush()


def header(header):
    write("\n" + "=" * 100 + "\n\n\t" + header + "\n" + "=" * 100 + "\n", CYAN)
    logger.information(title)


def title(title):
    write("\n\n\t" + title + "\n" + "=" * 100 + "\n", CYAN)
    logger.information(title)


def sub_title(subtitle):
    write("\n\t" + subtitle + "\n\t" + "_" * 90 + "\n", CYAN)
    logger.information(subtitle)


def sub_sub_title(sub_title):
    write("\n\t\t" + sub_title + "\n\t\t" + "-" * 90 + "\n", CYAN)
    logger.information(sub_title)


def command(message):
    if values.DEBUG:
        prefix = "\t\t[command] "
        write(message, ROSE, prefix=prefix, indent_level=2)
    logger.command(message)


def normal(message, jump_line=True):
    write(message, BLUE, jump_line)
    logger.output(message)


def highlight(message, jump_line=True):
    indent_length = message.count("\t")
    prefix = "\t" * indent_length
    message = message.replace("\t", "")
    write(message, YELLOW, jump_line, indent_level=indent_length, prefix=prefix)
    logger.information(message)


def information(message, jump_line=True):
    write(message, BLUE, jump_line)
    logger.information(message)


def statistics(message):
    write(message, BLUE)
    logger.output(message)


def error(message, log=True):
    write(message, RED)
    if log:
        logger.error(message)


def success(message):
    write(message, GREEN)
    logger.output(message)


def special(message):
    write(message, ROSE)
    logger.note(message)


def program_output(output_message):
    write("\t\tProgram Output:", BLUE)
    if isinstance(output_message, list):
        for line in output_message:
            write("\t\t\t" + line.strip(), PROG_OUTPUT_COLOR)
    else:
        write("\t\t\t" + output_message, PROG_OUTPUT_COLOR)


def warning(message):
    write(message, YELLOW)
    logger.warning(message)


def note(message):
    write(message, BLUE)
    logger.note(message)


def configuration(setting, value):
    message = "\t[config] " + setting + ": " + str(value)
    write(message, BLUE, True)
    logger.configuration(setting + ":" + str(value))


def end(time_info, is_error=False):
    statistics("\nRun time statistics:\n-----------------------\n")

    if is_error:
        error(
            "\n"
            + values.TOOL_NAME
            + " exited with an error after "
            + time_info[definitions.DURATION_TOTAL]
            + " seconds \n"
        )
    else:
        success(
            "\n"
            + values.TOOL_NAME
            + " (Stage: "
            + values.TOOL_STAGE
            + ")"
            + " finished successfully after "
            + time_info[definitions.DURATION_TOTAL]
            + " seconds \n"
        )
