"""
Handles all calls to codeql.
"""

import csv
import os
import shutil
from collections.abc import Mapping

from app import definitions, utilities, values


def create_db():
    """
    Create codeql database for the target program source code.
    """
    os.chdir(values.CONF_DIR_SRC_BUILD)

    utilities.remove_dir_if_exists(values.DIR_CODEQL_DB)

    # first clean the build
    utilities.execute_command(values.CONF_COMMAND_CLEAN)
    # then run
    cmd_list = [
        "codeql",
        "database",
        "create",
        values.DIR_CODEQL_DB,
        "--language=cpp",
        "--threads=32",
    ]

    cmd = " ".join(cmd_list)
    cmd += ' --command="' + values.CONF_COMMAND_BUILD_PROJECT + '"'
    utilities.execute_command(cmd)


def run_query_helper(
    template_name: str, res_file_name: str, replace_dict: Mapping[str, str]
):
    """
    Prepare, compile, and run a codeql query.
    """

    if not values.DIR_CODEQL_DB or not os.path.isdir(values.DIR_CODEQL_DB):
        utilities.error_exit("Codeql database not found.")

    codeql_query_dir = os.path.join(values.DIR_RUNTIME_REPAIR, "codeql-queries")

    # create query src dir in the runtime directory
    utilities.create_dir_if_nonexists(codeql_query_dir)
    real_qlpack_path = os.path.join(codeql_query_dir, "qlpack.yml")
    if not os.path.isfile(real_qlpack_path):
        shutil.copy(
            os.path.join(definitions.DIR_CODEQL_SRC, "qlpack.yml"), real_qlpack_path
        )
        # need to install the pack to create lock.yml file
        os.chdir(codeql_query_dir)
        utilities.execute_command("codeql pack install")

    # prepare query file
    template_path = os.path.join(definitions.DIR_CODEQL_TEMPLATE, template_name)
    real_query_path = os.path.join(codeql_query_dir, template_name)

    shutil.copy(template_path, real_query_path)

    # replace holder variable with real values
    with open(real_query_path) as f:
        query_src = f.read()

    for key, value in replace_dict.items():
        query_src = query_src.replace(key, value)

    with open(real_query_path, "w") as f:
        f.write(query_src)

    # (optional) remove query compile cache, so that we have the correct timing
    codeql_cache_dir = os.path.join(codeql_query_dir, ".cache")
    utilities.remove_dir_if_exists(codeql_cache_dir)

    # compile and run query
    cmd_list = [
        "codeql",
        "database",
        "analyze",
        values.DIR_CODEQL_DB,
        real_query_path,
        "--format=csv",
        "--rerun",
        "--output=" + res_file_name,
    ]

    cmd = " ".join(cmd_list)
    utilities.execute_command(cmd)


def run_extract_var_query(file: str, func: str, trace_start: int, fix_loc: int):
    """
    Run a codeql query to get patch ingredients.
    """

    values.FILE_CODEQL_RES_EXTRACT_VAR = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-ingredient.csv"
    )

    file_base_name = os.path.basename(file)

    replace_dict = {
        definitions.HOLDER_FILE: '"' + file_base_name + '"',
        definitions.HOLDER_FUNC: '"' + func + '"',
        definitions.HOLDER_START_LINE: str(trace_start),
        definitions.HOLDER_FIX_LINE: str(fix_loc),
    }

    run_query_helper(
        definitions.FNAME_CODEQL_EXTRACT_VAR,
        values.FILE_CODEQL_RES_EXTRACT_VAR,
        replace_dict,
    )


def parse_extract_var_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_EXTRACT_VAR):
        utilities.error_exit("Codeql query result not found.")

    all_vars = []

    with open(values.FILE_CODEQL_RES_EXTRACT_VAR) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            vars_entry = row[3]
            vars = vars_entry.split("\n")
            all_vars.extend(vars)

    all_vars = list(set(all_vars))

    pointers = []
    non_pointers = []

    for var in all_vars:
        if var.startswith("pointer("):
            pointers.append(var[8:-1])
        elif var.startswith("non-pointer("):
            non_pointers.append(var[12:-1])

    return pointers, non_pointers


def run_stmt_boundary_query(file_path: str, stmt_start_line: int):
    """
    Run a codeql query to get boudary for the statement at stmt_start_line, in file file_path.
    """

    values.FILE_CODEQL_RES_STMT_BOUNDARY = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-stmt-boundary.csv"
    )

    base_file_path = os.path.basename(file_path)
    replace_dict = {
        definitions.HOLDER_FILE: '"' + base_file_path + '"',
        definitions.HOLDER_START_LINE: str(stmt_start_line),
    }

    run_query_helper(
        definitions.FNAME_CODEQL_STMT_BOUNDARY,
        values.FILE_CODEQL_RES_STMT_BOUNDARY,
        replace_dict,
    )


def parse_stmt_boudary_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_STMT_BOUNDARY):
        utilities.error_exit("Codeql query result not found.")

    found_endlines = set()

    with open(values.FILE_CODEQL_RES_STMT_BOUNDARY) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            line_info = row[3].split(":")
            end_line = int(line_info[1])
            found_endlines.add(end_line)

    found_endlines = list(found_endlines)
    num_found = len(found_endlines)
    if num_found != 1:
        utilities.error_exit(
            "Expecting only find 1 unique end line of the statement at fix location, but found "
            + str(num_found)
            + " lines: "
            + str(found_endlines)
        )

    return found_endlines[0]


def run_return_stmts_query(func: str):
    """
    Run a codeql query to get all return stmts in the codebase,
    which has the same return type as the return type of `func`.
    """

    values.FILE_CODEQL_RES_RETURN_STMTS = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-return-stmts.csv"
    )

    replace_dict = {
        definitions.HOLDER_FUNC: '"' + func + '"',
    }

    run_query_helper(
        definitions.FNAME_CODEQL_RETURN_STMTS,
        values.FILE_CODEQL_RES_RETURN_STMTS,
        replace_dict,
    )


def parse_return_stmts_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_RETURN_STMTS):
        utilities.error_exit("Codeql query result not found.")

    return_stmts = []

    with open(values.FILE_CODEQL_RES_RETURN_STMTS) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            return_stmts.append(row[3])

    return_stmts = list(set(return_stmts))
    return_stmts = sorted(return_stmts)
    return return_stmts


def run_labels_query(func: str):
    """
    Run a codeql query to get all labels in `func`.
    """

    values.FILE_CODEQL_RES_LABELS = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-labels.csv"
    )

    replace_dict = {
        definitions.HOLDER_FUNC: '"' + func + '"',
    }

    run_query_helper(
        definitions.FNAME_CODEQL_LABELS, values.FILE_CODEQL_RES_LABELS, replace_dict
    )


def parse_labels_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_LABELS):
        utilities.error_exit("Codeql query result not found.")

    labels = []

    with open(values.FILE_CODEQL_RES_LABELS) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            labels.append(row[3])

    labels = sorted(labels)

    return labels


def run_loc_after_query(func: str, start_line: int, end_line: int):
    """
    Run a codeql query to get all lines after the start line and end line.
    "After" means this line is on any potential program path.
    """

    values.FILE_CODEQL_RES_LOC_AFTER = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-loc-after.csv"
    )

    replace_dict = {
        definitions.HOLDER_FUNC: '"' + func + '"',
        definitions.HOLDER_START_LINE: str(start_line),
        definitions.HOLDER_END_LINE: str(end_line),
    }

    run_query_helper(
        definitions.FNAME_CODEQL_LOC_AFTER,
        values.FILE_CODEQL_RES_LOC_AFTER,
        replace_dict,
    )


def parse_loc_after_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_LOC_AFTER):
        utilities.error_exit("Codeql query result not found.")

    all_locs = []
    with open(values.FILE_CODEQL_RES_LOC_AFTER) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            loc_entry = row[3]
            loc = int(loc_entry)
            all_locs.append(loc)

    all_locs = list(set(all_locs))

    return all_locs


def run_loc_between_query(func: str, start_line: int, end_line: int):
    """
    Run a codeql query to get all lines between start and end line.
    "Between" means this line is on any potential program path.
    """

    values.FILE_CODEQL_RES_LOC_BETWEEN = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-loc-betweens.csv"
    )

    replace_dict = {
        definitions.HOLDER_FUNC: '"' + func + '"',
        definitions.HOLDER_START_LINE: str(start_line),
        definitions.HOLDER_END_LINE: str(end_line),
    }

    run_query_helper(
        definitions.FNAME_CODEQL_LOC_BETWEEN,
        values.FILE_CODEQL_RES_LOC_BETWEEN,
        replace_dict,
    )


def parse_loc_between_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_LOC_BETWEEN):
        utilities.error_exit("Codeql query result not found.")

    all_locs = []
    with open(values.FILE_CODEQL_RES_LOC_BETWEEN) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            loc_entry = row[3]
            loc = int(loc_entry)
            all_locs.append(loc)

    all_locs = list(set(all_locs))

    return all_locs


def run_consts_query(file: str, func: str, fix_loc: int):
    """
    Run a codeql query to get constants in `func`.
    """
    values.FILE_CODEQL_RES_CONSTS = os.path.join(
        values.DIR_RUNTIME_REPAIR, "codeql-res-consts.csv"
    )

    file_base_name = os.path.basename(file)

    replace_dict = {
        definitions.HOLDER_FILE: '"' + file_base_name + '"',
        definitions.HOLDER_FUNC: '"' + func + '"',
        definitions.HOLDER_FIX_LINE: str(fix_loc),
    }

    run_query_helper(
        definitions.FNAME_CODEQL_CONSTS,
        values.FILE_CODEQL_RES_CONSTS,
        replace_dict,
    )


def parse_consts_query_result():
    if not os.path.isfile(values.FILE_CODEQL_RES_CONSTS):
        utilities.error_exit("Codeql query result not found.")

    all_consts = []

    with open(values.FILE_CODEQL_RES_CONSTS) as f:
        csvreader = csv.reader(f)
        for row in csvreader:
            consts_entry = row[3]
            consts = consts_entry.split("\n")
            for const in consts:
                all_consts.append(const.strip())

    # Add some default ones, just in cases there is no consts parsed from codeql.
    all_consts.append("0")
    all_consts.append("-1")

    all_consts = list(set(all_consts))

    return all_consts
