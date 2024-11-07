"""
Prepare all pre data for each subjects.
Mainly used to build a docker image with all pre data in place for the benchmark.

Some functionalities in this script overlaps with the cerberus driver.

Run it like this:

python ./scripts/gen_configs_for_exp_image.py --benchmark /opt/effFix-benchmark --config /tmp-efffix-configs --dest /data
"""

import argparse
import json
import subprocess
import time
from multiprocessing import Pool
from os.path import join as pjoin

bug_conversion_table = {
    "Memory Leak": "MEMORY_LEAK_C",
    "Null Pointer Dereference": "NULLPTR_DEREFERENCE",
}

# bugs in the setup groups only need one setup run.
setup_groups = {
    "memory-leak-1-swoole": ["memory-leak-2-swoole", "memory-leak-3-swoole"],
    "memory-leak-4-p11-kit": [],
    "memory-leak-5-x264": [
        "memory-leak-6-x264",
        "memory-leak-7-x264",
        "memory-leak-8-x264",
        "memory-leak-9-x264",
        "memory-leak-10-x264",
    ],
    "memory-leak-11-snort": [
        "memory-leak-12-snort",
        "memory-leak-13-snort",
        "memory-leak-14-snort",
        "memory-leak-15-snort",
        "memory-leak-16-snort",
        "memory-leak-17-snort",
        "memory-leak-18-snort",
    ],
    "memory-leak-19-openssl-1": [
        "memory-leak-20-openssl-1",
        "memory-leak-21-openssl-1",
        "memory-leak-22-openssl-1",
        "null-ptr-1-openssl-1",
        "null-ptr-2-openssl-1",
        "null-ptr-3-openssl-1",
        "null-ptr-4-openssl-1",
        "null-ptr-5-openssl-1",
    ],
    "memory-leak-23-linux-kernel-5": [
        "memory-leak-24-linux-kernel-5",
        "null-ptr-9-linux-kernel-5",
    ],
    "null-ptr-6-openssl-3": ["null-ptr-7-openssl-3", "null-ptr-8-openssl-3"],
}


def run_command(cmd: str):
    cp = subprocess.run(
        cmd,
        shell=True,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )
    if cp.returncode != 0:
        print(f"{cmd} finished with return code {cp.returncode}")
        print(cp.stderr.decode("utf-8"))


def print_with_time(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{t}] {msg}")


def setup_one_entry(meta_entry, benchmark_dir, experiment_dir):
    subject = meta_entry["subject"]
    bug_id = meta_entry["bug_id"]
    benchmark_bug_dir = pjoin(benchmark_dir, subject, bug_id)
    setup_script = pjoin(benchmark_bug_dir, "setup.sh")

    # run setup script to get the subject source code
    # NOTE: do not need to run config here, since the pre stage will do it.
    run_command(f"bash {setup_script} {experiment_dir}")


def gen_conf_one_entry(meta_entry, benchmark_dir, experiment_dir):
    subject = meta_entry["subject"]
    bug_id = meta_entry["bug_id"]
    benchmark_bug_dir = pjoin(benchmark_dir, subject, bug_id)
    instrument_script = pjoin(benchmark_bug_dir, "EffFix", "instrument.sh")
    experiment_bug_dir = pjoin(experiment_dir, "effFix-benchmark", subject, bug_id)

    # (1) get template of the conf file
    run_command(f"bash {instrument_script} {experiment_dir}")

    # (2) populate other fields
    conf_path = pjoin(experiment_bug_dir, "EffFix", "repair.conf")
    # save all other config fields here
    efffix_config = dict()

    bug_type = meta_entry["bug_type"]
    bug_type = bug_conversion_table[bug_type]
    source_info = meta_entry["source"]
    sink_info = meta_entry["sink"]
    # src will always be at this place
    dir_src = pjoin(experiment_bug_dir, "src")
    dir_pre = pjoin(experiment_bug_dir, "pre")
    dir_repair = pjoin(experiment_bug_dir, "repair")
    efffix_config["tag_id"] = bug_id
    efffix_config["config_command"] = meta_entry["config_command"]
    # some bug does not have build_dir field
    efffix_config["build_dir"] = meta_entry.get("build_dir", "")
    efffix_config["build_command_project"] = meta_entry["build_command_project"]
    efffix_config["build_command_repair"] = meta_entry["build_command_repair"]
    efffix_config["clean_command"] = "make clean"
    efffix_config["src_dir"] = dir_src
    efffix_config["bug_type"] = bug_type
    efffix_config["bug_file"] = source_info["src-file"]
    efffix_config["bug_procedure"] = source_info["procedure"]
    efffix_config["bug_start_line"] = source_info["line"]
    efffix_config["bug_end_line"] = sink_info["line"]
    efffix_config["runtime_dir_pre"] = dir_pre
    efffix_config["runtime_dir_repair"] = dir_repair
    # NOTE: pulse_args are not included in meta-data.json;
    # they are set in instrument.sh in the benchmark, since they are specific to
    # EffFix and may not be useful for other tools.
    with open(conf_path, "a") as f:
        for key, value in efffix_config.items():
            f.write(f"{key}:{value}\n")

    return conf_path


def run_pre_one_entry(conf_path):
    pre_command = f"effFix --stage pre {conf_path}"
    run_command(pre_command)


def run_everything_one_entry(meta_entry, benchmark_dir, experiment_dir):
    bug_id = meta_entry["bug_id"]

    print_with_time(f"[{bug_id}] Starting ... ")

    time_setup_start = time.time()
    print_with_time(f"[{bug_id}] Running setup.")
    setup_one_entry(meta_entry, benchmark_dir, experiment_dir)
    time_setup_end = time.time()
    print_with_time(
        f"[{bug_id}] Setup took {int(time_setup_end - time_setup_start)} seconds."
    )

    time_conf_start = time.time()
    print_with_time(f"[{bug_id}] Creating conf file.")
    conf_path = gen_conf_one_entry(meta_entry, benchmark_dir, experiment_dir)
    time_conf_end = time.time()
    print_with_time(
        f"[{bug_id}] Creating conf took {int(time_conf_end - time_conf_start)} seconds."
    )

    time_pre_start = time.time()
    print_with_time(f"[{bug_id}] Running the setup stage.")
    run_pre_one_entry(conf_path)
    time_pre_end = time.time()
    print_with_time(
        f"[{bug_id}] Pre took {int(time_pre_end - time_pre_start)} seconds."
    )

    print_with_time(f"[{bug_id}] Done!")


def install_deps_for_all(meta_data, benchmark_dir):
    """
    Since the deps script uses apt-get which does not work very well parallelly, we install
    all dependencies upfront.
    """
    print_with_time("Installing deps for all bugs.")

    unique_deps_content = set()
    deps_scripts_to_run = list()

    # since some deps scripts have the exact same contents, remove duplicates here to save time
    for meta_entry in meta_data:
        subject = meta_entry["subject"]
        bug_id = meta_entry["bug_id"]
        benchmark_bug_dir = pjoin(benchmark_dir, subject, bug_id)
        deps_script = pjoin(benchmark_bug_dir, "deps.sh")
        with open(deps_script) as f:
            deps_content = f.read()
        if deps_content not in unique_deps_content:
            unique_deps_content.add(deps_content)
            deps_scripts_to_run.append(deps_script)

    print_with_time(f"\t{len(deps_scripts_to_run)} scripts to run.")
    for deps_script in deps_scripts_to_run:
        run_command(f"bash {deps_script}")

    print_with_time("Done with installing dependencies.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", required=True, help="Path to the benchmark dir.")

    parsed_args = parser.parse_args()
    benchmark_dir = parsed_args.benchmark
    # hardcode this. Place all src code and pre data in this directory
    experiment_dir = "/effFix-experiment"

    meta_path = pjoin(benchmark_dir, "meta-data.json")
    with open(meta_path) as f:
        meta_data = json.load(f)

    install_deps_for_all(meta_data, benchmark_dir)

    # form arguments for parallel processing
    parallel_args = []
    for entry in meta_data:
        parallel_args.append((entry, benchmark_dir, experiment_dir))

    # start parallel processing
    print_with_time("================= Start parallel processing. =================")
    try:
        pool = Pool(processes=len(parallel_args))
        pool.starmap(run_everything_one_entry, parallel_args)
        pool.close()
        pool.join()
    finally:
        print_with_time("================= Done with everything! =================")


if __name__ == "__main__":
    main()


"""
Specicial step for running efffix on efffix benchmark

# in cerberus benchmark driver
bash setup.sh /experiment
bash instrument.sh /experiment

# own setup - when constructing efffix:experiments image
bash setup.sh /efffix_experiment
bash instrument.sh /efffix_experiment

# in cerberus, when running saver on efffix benchmark
do everything as per normal

# in cerberus, when running efffix on efffix benchmark
set self.dir_exp to /efffix_experiment, and skip config and build.
"""
