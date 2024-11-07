import itertools
import os
import shutil

from app import utilities, values

patch_counter = 0


def concat_str_to_all(all_items, new_str):
    """
    :param all_items: list of strings
    :param new_str: a new str to be appended to all items.
    """
    if not all_items:
        # special case: there is no existing items
        return [new_str]

    return [item + " " + new_str for item in all_items]


def concat_two_lists_with_cross_product(list_one, list_two):
    """
    :param list_one list_two: list of strings.
    :returns: A new list containing cross product (by string concat) of the two lists.
    """
    # just giving some sensible treatment to special cases
    if not list_one:
        return list_two

    if not list_two:
        return list_one

    print(f"doing cross product with size {len(list_one)}x{len(list_two)}")
    cross_product = list(itertools.product(list_one, list_two))
    result = [a + " " + b for a, b in cross_product]
    print("cross product finished")
    return result


def concat_one_to_all_estimate_size(old_items_size):
    """
    Similar to concat_str_to_all, but only estimate the size of the new list.
    """
    if old_items_size == 0:
        return 1
    return old_items_size


def concat_two_lists_estimate_size(list_one_size, list_two_size):
    """
    Similar to concat_two_lists_with_cross_product, but only estimate the size of the new list.
    """
    if list_one_size == 0:
        return list_two_size

    if list_two_size == 0:
        return list_one_size

    return list_one_size * list_two_size


def get_new_patch_file_name():
    """
    Use a counter to always get a new unique patch name.
    """
    global patch_counter
    patch_counter = patch_counter + 1
    new_name = os.path.join(values.DIR_RUNTIME_REPAIR, str(patch_counter) + ".patch")
    return new_name


def restore_file_to_unpatched_state():
    """
    Restore the original file to the unpatched state.
    """
    shutil.copyfile(values.FIX_FILE_PATH_BACKUP, values.FIX_FILE_PATH_ORIG)


def weave_patch_instruction(patch_inst: str, start_line_num: int, end_line_num):
    """
    Decode patch instruction based on the patch grammar, weave it into the original file, and produce a diff file representing the patch.
    """
    if patch_inst.startswith("INSERT FRONT"):
        patch_content = patch_inst[13:]
        # do sed escape for patch content
        patch_content = patch_content.replace("&", r"\&")
        cmd = f"sed -i -e '{start_line_num}s:^:{patch_content} :' {values.FIX_FILE_PATH_ORIG}"
        utilities.execute_command(cmd)
    elif patch_inst.startswith("INSERT BACK"):
        patch_content = patch_inst[12:]
        # do sed escape for patch content
        patch_content = patch_content.replace("&", r"\&")
        cmd = f"sed -i -e '{end_line_num}s:$: {patch_content}:' {values.FIX_FILE_PATH_ORIG}"
        utilities.execute_command(cmd)
    else:  # patch instruction starts with COND
        patch_content = patch_inst[5:]
        patch_content = "if (" + patch_content + ") {"
        # do sed escape for patch content
        patch_content = patch_content.replace("&", r"\&")
        cmd_end = f"sed -i -e '{end_line_num}s:$: }}:' {values.FIX_FILE_PATH_ORIG}"
        cmd_start = f"sed -i -e '{start_line_num}s:^:{patch_content} :' {values.FIX_FILE_PATH_ORIG}"
        utilities.execute_command(cmd_end)
        utilities.execute_command(cmd_start)

    # now create patch file
    patch_file_path = get_new_patch_file_name()
    diff_cmd = (
        "diff -u "
        + values.FIX_FILE_PATH_BACKUP
        + " "
        + values.FIX_FILE_PATH_ORIG
        + " > "
        + patch_file_path
    )

    utilities.execute_command(diff_cmd, allow_failure=True)

    return patch_file_path


def apply_patch_file(patch_file_path):
    """
    Apply a patch file to the original file, and save the result to a new file.
    """
    # restore a copy from the backupfile
    restore_file_to_unpatched_state()

    # apply the patch file
    patch_cmd = "patch " + values.FIX_FILE_PATH_ORIG + " < " + patch_file_path
    utilities.execute_command(patch_cmd)
