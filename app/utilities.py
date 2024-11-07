import os
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager

from app import emitter, logger, values


def error_exit_no_log(*arg_list):
    """
    Same as `error_exit`, but do not create logs.
    """
    emitter.error("Repair Failed", log=False)
    for arg in arg_list:
        emitter.error(str(arg), log=False)
    raise Exception("Error. Exiting...")


def error_exit(*arg_list):
    emitter.error("Repair Failed")
    for arg in arg_list:
        emitter.error(str(arg))
    raise Exception("Error. Exiting...")


def execute_command(command, allow_failure=False, show_output=True):
    # Print executed command and execute it in console
    command = command.encode().decode("ascii", "ignore")
    emitter.command(command)
    command = "{ " + command + " ;} 2> " + logger.file_log_err
    if not show_output:
        command += " > /dev/null"

    process = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True)
    _, error = process.communicate()
    if not allow_failure and process.returncode != 0:
        error_exit(f"Error executing command: {command}. Error is: {error}")
    return int(process.returncode)


class Timer:
    def __init__(self):
        self.__start_time: float = 0
        self.__end_time: float = 0
        # store start time of each timer session
        self.start_time_record: dict[str, float] = dict()
        # use this to store the duration of each step
        self.elapsed_record: dict[str, float] = dict()

    def set_overall_start_time(self):
        """
        Set the start point (and end point) of the tool.
        Mainly used for checking time budget.
        Can only be called after reading cmd-line arguments.
        """
        self.__start_time = time.perf_counter()
        self.__end_time = self.__start_time + values.REPAIR_BUDGET * 60

    def get_elapsed_from_overall_start(self) -> float:
        """
        Get the elapsed time from the start point.
        """
        cur_time = time.perf_counter()
        return cur_time - self.__start_time

    def get_total_remaining_time(self) -> float:
        """
        Get the remaining time from the time budget.
        """
        cur_time = time.perf_counter()
        return self.__end_time - cur_time

    def is_overall_time_exhausted(self):
        """
        Check that, at current moment, whether we have used up all the
        time budget.
        """
        cur_time = time.perf_counter()
        return cur_time >= self.__end_time

    def start(self, key):
        """
        Start clock for one session, and record the start time.
        """
        self.start_time_record[key] = time.perf_counter()

    def stop(self, key):
        """
        Stop clock for one session, calculate and print time elapsed.
        """
        end_tick = time.perf_counter()
        start_tick = self.start_time_record[key]
        elapsed = end_tick - start_tick
        self.elapsed_record[key] = elapsed
        emitter.information(
            "[Timer] Duration for " + key + ": " + format(elapsed, ".3f") + "s"
        )

    def pause(self, key):
        """
        Pause clock for one session, accumulate time elapsed.
        """
        end_tick = time.perf_counter()
        start_tick = self.start_time_record[key]
        elapsed = end_tick - start_tick
        if key in self.elapsed_record:
            self.elapsed_record[key] += elapsed
        else:
            # first time press pause
            self.elapsed_record[key] = elapsed

    def print_and_return(self, key):
        """
        Only print and return time information stored so far.
        Used for start-pause timers.
        """
        total_elapsed = self.elapsed_record[key]
        emitter.information(
            "[Timer] Accumulated duration for "
            + key
            + ": "
            + format(total_elapsed, ".3f")
            + "s"
        )
        return total_elapsed

    def get_time_info(self):
        time_info = dict()
        for key, t_in_float in self.elapsed_record.items():
            time_info[key] = format(t_in_float, ".3f")
        return time_info

    def print_total_and_average(self, key: str, num_units: int) -> float | None:
        """
        Print total time + average time.
        """
        total_elapsed = self.elapsed_record[key]
        emitter.information(
            "[Timer] Accumulated duration for "
            + key
            + ": "
            + format(total_elapsed, ".3f")
            + "s"
        )
        if num_units == 0:
            return None
        average = total_elapsed / num_units
        emitter.information(
            "[Timer] Average duration for " + key + ": " + format(average, ".5f") + "s"
        )
        return average


global_timer = Timer()


def backup_file(file_path, backup_path):
    backup_command = "cp " + file_path + " " + backup_path
    execute_command(backup_command)


def restore_file(file_path, backup_path):
    restore_command = "cp " + backup_path + " " + file_path
    execute_command(restore_command)


def reset_git(source_directory):
    reset_command = "cd " + source_directory + ";git reset --hard HEAD"
    execute_command(reset_command)


def remove_dir_if_exists(dir_path):
    if os.path.isdir(dir_path):
        shutil.rmtree(dir_path)


def create_dir_if_nonexists(dir_path):
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)


def remove_and_create_new_dir(dir_path):
    remove_dir_if_exists(dir_path)
    create_dir_if_nonexists(dir_path)


@contextmanager
def timeout(time):
    signal.signal(signal.SIGALRM, raise_timeout)
    signal.alarm(time)

    try:
        yield
    except TimeoutError:
        pass
    finally:
        signal.signal(signal.SIGALRM, signal.SIG_IGN)


def raise_timeout(signum, frame):
    raise TimeoutError
