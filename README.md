# EffFix: Efficient and Effective Repair of Pointer Manipulating Programs

This repository contains the source code of the EffFix tool.
The experiment artifacts are hosted on [Zenodo](https://zenodo.org/records/8390752).


## Source code structure

- `app`: The main source code for the tool.
    - `equivalence`: patch equivalence reasoning.
    - `localization`: SBFL fault localization with static analysis summaries.
    - `parsing`: parses Infer result files.
    - `repairgen`: patch generation from PCFG.
- `codeql`: Templates of codeql queries used to capture patch ingredients.


## Building with docker

Dockerfiles are provided for building the tool, as well as the experiment environment. A image
should be built like:

```
docker build . -f Dockerfile.experiments -t <tag>
```


## Running EffFix

EffFix requires a config file for each bug. A config file should contain the following entries:

- tag_id: a name idetifier
- config_command: command to configure the program
- build_dir: directory where build commands should be executed. Relative to src_dir.
- build_command_project: command to build the program
- build_command_repair: optional command to do incremental building for patch validation
- clean_command: command to clean the build
- src_dir: directory of program source code
- bug_type: type of the bug
- bug_file: the file in which bug manifests
- bug_procedure: the procedure in which the bug manifests
- bug_start_line: start line of bug, as reported by detection tool
- bug_end_line: end line of bug, as reported by detection tool
- runtime_dir_pre: A destination to place analysis outputs
- runtime_dir_repair: A destination to place repair results.

A example config file:

```
tag_id=swoole-2
config_command=phpize && ./configure
build_command=make -j32
build_command_repair=make
clean_command=make clean
src_dir=/opt/effFix-benchmark/swoole-src
bug_type=MEMORY_LEAK_C
bug_file=src/pipe/PipeBase.c
bug_procedure=swPipeBase_create
bug_start_line=32
bug_end_line=39
runtime_dir_pre=/opt/result/swoole-pre
runtime_dir_repair=/opt/result/swoole-2-repair
```

To invoke effFix, use the following commands to do pre-analysis and repair:

```
effFix --stage pre <config-file>
effFix --stage repair <config-file>
```
