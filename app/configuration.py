import argparse
import configparser
import os
from os.path import join as pjoin

from app import definitions, emitter, utilities, values


def read_args():
    """
    Read and process command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Separation logic based memory error repair"
    )
    parser.add_argument("config_file", help="Path to the config file.")
    parser.add_argument(
        "--debug", default=False, help="Enable debug mode.", action="store_true"
    )
    parser.add_argument(
        "--stage",
        default="repair",
        required=True,
        choices=["pre", "repair"],
        help="Pre-analysis or repair stage.",
    )

    ### only for repair stage
    parser.add_argument(
        "--budget", default=10, type=int, help="[Repair] Total time budget."
    )
    parser.add_argument(
        "--disable-learn-prob",
        "-no-prob",
        default=False,
        action="store_true",
        help="[Repair] Disable learning of probabilities during repair generation.",
    )

    parser.add_argument(
        "--enable-validation",
        "-validate",
        default=False,
        action="store_true",
        help="[Validation] enable global validation for clusters",
    )

    parser.add_argument(
        "--disable-reset",
        "-no-reset",
        default=False,
        action="store_true",
        help="[Repair] disable resetting probabilities",
    )

    parser.add_argument(
        "--max-depth",
        default=10,
        type=int,
        help="maximum height of the patch tree",
    )

    parser.add_argument(
        "--adj-factor-big",
        default=0.2,  # 1/5
        type=float,
        help="Adjustment factor for big changes",
    )

    parser.add_argument(
        "--adj-factor-small",
        default=0.1,  # 1/10
        type=float,
        help="Adjustment factor for small changes",
    )

    parsed_args = parser.parse_args()
    values.FILE_CONFIGURATION = parsed_args.config_file
    values.DEBUG = parsed_args.debug
    values.TOOL_STAGE = parsed_args.stage
    values.REPAIR_BUDGET = parsed_args.budget
    values.GENERATOR_MAX_DEPTH = parsed_args.max_depth
    values.ADJ_FACTOR_BIG = parsed_args.adj_factor_big
    values.ADJ_FACTOR_SMALL = parsed_args.adj_factor_small
    values.LEARN_PROBABILITIES = not parsed_args.disable_learn_prob
    values.VALIDATE_GLOBAL = parsed_args.enable_validation
    values.IS_RESET_PROB = not parsed_args.disable_reset


def read_conf_file():
    """
    Read the configuration file at the beginning.
    Note that logger has not been created at this point. So do not create logs in this function.
    """
    if not os.path.exists(values.FILE_CONFIGURATION):
        utilities.error_exit(
            "[NOT FOUND] Configuration file " + values.FILE_CONFIGURATION
        )
    if os.path.getsize(values.FILE_CONFIGURATION) == 0:
        utilities.error_exit("[EMPTY] Configuration file " + values.FILE_CONFIGURATION)

    # really reading config file
    config = configparser.ConfigParser()
    with open(values.FILE_CONFIGURATION) as conf_file:
        config.read_string("[DEFAULT]\n" + conf_file.read())

    config_dict = config["DEFAULT"]

    values.CONF_DIR_SRC = config_dict[definitions.CONF_DIR_SRC]
    values.CONF_DIR_SRC = os.path.realpath(values.CONF_DIR_SRC)
    values.CONF_BUILD_DIR = config_dict.get(definitions.CONF_BUILD_DIR, "")
    values.CONF_DIR_SRC_BUILD = pjoin(values.CONF_DIR_SRC, values.CONF_BUILD_DIR)

    values.CONF_COMMAND_BUILD_PROJECT = config_dict[
        definitions.CONF_COMMAND_BUILD_PROJECT
    ]
    values.CONF_COMMAND_BUILD_REPAIR = config_dict[
        definitions.CONF_COMMAND_BUILD_REPAIR
    ]
    values.CONF_COMMAND_CLEAN = config_dict[definitions.CONF_COMMAND_CLEAN]
    values.CONF_COMMAND_CONFIG = config_dict[definitions.CONF_COMMAND_CONFIG]

    values.CONF_TAG_ID = config_dict[definitions.CONF_TAG_ID]
    values.CONF_BUG_TYPE = config_dict[definitions.CONF_BUG_TYPE]
    values.CONF_BUG_PROC = config_dict[definitions.CONF_BUG_PROC]
    values.CONF_BUG_FILE = config_dict[definitions.CONF_BUG_FILE]
    values.CONF_BUG_START_LINE = int(config_dict[definitions.CONF_BUG_START_LINE])
    values.CONF_BUG_END_LINE = int(config_dict[definitions.CONF_BUG_END_LINE])

    values.DIR_RUNTIME_PRE = config_dict[definitions.CONF_DIR_RUNTIME_PRE]
    values.DIR_RUNTIME_REPAIR = config_dict[definitions.CONF_DIR_RUNTIME_REPAIR]

    # all the extra commands to Pulse comes from here
    values.CONF_PULSE_ARGS = config_dict.get(definitions.CONF_PULSE_ARGS, "")

    if not values.CONF_TAG_ID:
        utilities.error_exit("[NOT FOUND] Tag ID ")

    if values.CONF_BUG_TYPE not in definitions.ALL_BUG_TYPES:
        utilities.error_exit("[INVALID] Bug type " + values.CONF_BUG_TYPE)

    if not values.DIR_RUNTIME_PRE or not values.DIR_RUNTIME_REPAIR:
        utilities.error_exit("Should specify two runtime directories.")


def print_configuration():
    # TODO: use a dictionary to do this
    emitter.configuration(definitions.CONF_DIR_SRC, values.CONF_DIR_SRC)
    emitter.configuration(
        definitions.CONF_COMMAND_BUILD_PROJECT, values.CONF_COMMAND_BUILD_PROJECT
    )
    emitter.configuration(
        definitions.CONF_COMMAND_BUILD_REPAIR, values.CONF_COMMAND_BUILD_REPAIR
    )
    emitter.configuration(definitions.CONF_COMMAND_CLEAN, values.CONF_COMMAND_CLEAN)
    emitter.configuration(definitions.CONF_COMMAND_CONFIG, values.CONF_COMMAND_CONFIG)
    emitter.configuration(definitions.CONF_TAG_ID, values.CONF_TAG_ID)
    emitter.configuration(definitions.CONF_BUG_TYPE, values.CONF_BUG_TYPE)
    emitter.configuration(definitions.CONF_BUG_PROC, values.CONF_BUG_PROC)
    emitter.configuration(definitions.CONF_BUG_FILE, values.CONF_BUG_FILE)
    emitter.configuration(definitions.CONF_BUG_START_LINE, values.CONF_BUG_START_LINE)
    emitter.configuration(definitions.CONF_BUG_END_LINE, values.CONF_BUG_END_LINE)
