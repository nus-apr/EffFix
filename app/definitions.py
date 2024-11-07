import os

# ------------------- Directories --------------------

DIR_ROOT = "/".join(os.path.realpath(__file__).split("/")[:-2])


# ------------------- codeql --------------------

DIR_CODEQL_SRC = os.path.join(DIR_ROOT, "codeql")
DIR_CODEQL_TEMPLATE = os.path.join(DIR_CODEQL_SRC, "templates")
FNAME_CODEQL_EXTRACT_VAR = "extract_var.ql"
FNAME_CODEQL_STMT_BOUNDARY = "stmt_boundary.ql"
FNAME_CODEQL_RETURN_STMTS = "return_stmts.ql"
FNAME_CODEQL_LABELS = "labels.ql"
FNAME_CODEQL_LOC_AFTER = "loc_after.ql"
FNAME_CODEQL_LOC_BETWEEN = "loc_between.ql"
FNAME_CODEQL_CONSTS = "consts.ql"

HOLDER_FILE = "HOLDER_FILE"
HOLDER_FUNC = "HOLDER_FUNC"
HOLDER_FILE = "HOLDER_FILE"
HOLDER_START_LINE = "HOLDER_START_LINE"
HOLDER_END_LINE = "HOLDER_END_LINE"
HOLDER_FIX_LINE = "HOLDER_FIX_LINE"


# ----------- Supported bug types from Infer ------------

BUG_TYPE_LEAK = "MEMORY_LEAK_C"
BUG_TYPE_NULLPTR = "NULLPTR_DEREFERENCE"
BUG_UAF = "USE_AFTER_FREE"
ALL_BUG_TYPES = [BUG_TYPE_LEAK, BUG_TYPE_NULLPTR, BUG_UAF]

# ----------- Disjunct labels ------------

LABEL_OK = "Ok"
LABEL_EXIT = "ExitProgram"

LABEL_ABORT = "AbortProgram"
LABEL_LATENT_ABORT = "LatentAbortProgram"
LABEL_INVALID_ACCESS = "InvalidAccess"
LABEL_LATENT_INVALID_ACCESS = "LatentInvalidAccess"
LABEL_ISL_LATENT = "ISLLatentMemoryError"

LABEL_RETAIN_CYCLE = "ErrorRetainCycle"
LABEL_MEMORY_LEAK = "ErrorMemoryLeak"
LABEL_RESOURCE_LEAK = "ErrorResourceLeak"
LABEL_EXCEPTION = "ErrorException"

# ------------------- Configuration --------------------

CONF_COMMAND_CONFIG = "config_command"
CONF_BUILD_DIR = "build_dir"
CONF_COMMAND_BUILD_PROJECT = "build_command_project"
CONF_COMMAND_BUILD_REPAIR = (
    "build_command_repair"  # a smaller command to build, which targets the bug
)
CONF_COMMAND_CLEAN = "clean_command"
CONF_DIR_SRC = "src_dir"
CONF_TAG_ID = "tag_id"
CONF_BUG_TYPE = "bug_type"
CONF_BUG_PROC = "bug_procedure"
CONF_BUG_FILE = "bug_file"  # relative to src_directory
CONF_BUG_START_LINE = "bug_start_line"
CONF_BUG_END_LINE = "bug_end_line"

CONF_DIR_RUNTIME_PRE = "runtime_dir_pre"
CONF_DIR_RUNTIME_REPAIR = "runtime_dir_repair"

CONF_PULSE_MALLOC_PATTERN = "pulse_malloc_pattern"
CONF_PULSE_FREE_PATTERN = "pulse_free_pattern"
CONF_PULSE_REALLOC_PATTERN = "pulse_realloc_pattern"
CONF_PULSE_ARGS = "pulse_args"

# ----------------- KEY DEFINITIONS -------------------

DURATION_TOTAL = "total-run-time"

# pre-analysis
DURATION_PREANALYSIS = "pre-analysis"
DURATION_CONFIG_PROG = "config"
DURATION_INFER_DETECTION = "infer-detect"
DURATION_CODEQL_CAPTURE = "codeql-build-db"

# analysis in repair
DURATION_ANALYSIS = "analysis"
DURATION_LOCALIZATION = "localize"
DURATION_CODEQL_STMT_BOUNDARY = "codeql-get-stmt-boundary"
DURATION_CODEQL_EXTRACT_VAR = "codeql-get-ingredients-variables"
DURATION_CODEQL_RETURN_STMTS = "codeql-get-return-stmts"
DURATION_CODEQL_LABELS = "codeql-get-labels"
DURATION_CODEQL_CONSTS = "codeql-get-consts"

# repair
DURATION_REPAIR = "total-repair"
DURATION_PATCH_GEN = "patch-generation"
DURATION_PROB_UPDATE = "probabilities-update"
DURATION_SMT_SOLVER = "smt-solver"
DURATION_PATCH_SIGN_GEN = "patch-signature-generation"
DURATION_FOOTPRINT_GEN = "footprint-generation"
DURATION_PATCH_CLUSTER = "patch-clustering"


# validation
DURATION_VALIDATION = "total-validation"
DURATION_PATCH_VAL = "patch-validation"
