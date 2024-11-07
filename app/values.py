TOOL_NAME = "effFix"

# ---------------- Some global values ------------------------
TARGET_BUG = None  # set after identifing the target bug from report
TARGET_BUG_SIG = (
    None  # patch signature for the original buggy function : PatchSignature
)
TOTAL_NUM_BUGS = 0

# ---------------- Path of Tools/Results ---------------------
INFER_PATH = ""

DIR_RUNTIME_PRE = ""
DIR_RUNTIME_REPAIR = ""
DIR_CODEQL_DB = ""

DIR_INFER_OUT_WHOLE = ""  # output dir for Infer whole program analysis
DIR_INFER_OUT_SINGLE = ""  # output dir for Infer single function analysis
DIR_INFER_OUT_VALIDATION = ""  # output dir for Infer validation analysis
INFER_CHANGED_FILES = ""

# name of the summary file
SUMMARY_FILE_NAME = "summary_posts.json"

# codeql result files
FILE_CODEQL_RES_EXTRACT_VAR = ""
FILE_CODEQL_RES_STMT_BOUNDARY = ""
FILE_CODEQL_RES_RETURN_STMTS = ""
FILE_CODEQL_RES_LABELS = ""
FILE_CODEQL_RES_LOC_AFTER = ""
FILE_CODEQL_RES_LOC_BETWEEN = ""
FILE_CODEQL_RES_CONSTS = ""


# fix file
FIX_FILE_PATH_ORIG = ""
FIX_FILE_PATH_BACKUP = ""  # the backup file which always has the original content

# results
DIR_ALL_PATCHES = ""
DIR_FINAL_PATCHES = ""


# ------------------ Configuration Values ---------------

CONF_DIR_SRC = ""  # root directory of the target program (where build should happen)
CONF_BUILD_DIR = (
    ""  # relative path to dir src, where the build command should be executed
)
CONF_DIR_SRC_BUILD = ""  # concat of the two above. Absolute path to where the build command should be executed
CONF_COMMAND_CONFIG = ""
CONF_COMMAND_BUILD_PROJECT = ""
CONF_COMMAND_BUILD_REPAIR = ""
CONF_COMMAND_CLEAN = ""
CONF_TAG_ID = ""

CONF_BUG_TYPE = ""
CONF_BUG_PROC = ""
CONF_BUG_FILE = ""
CONF_BUG_START_LINE = None
CONF_BUG_END_LINE = None

CONF_PULSE_MALLOC_PATTERN = ""
CONF_PULSE_FREE_PATTERN = ""
CONF_PULSE_REALLOC_PATTERN = ""
CONF_PULSE_ARGS = ""

FILE_CONFIGURATION = ""
silence_emitter = False


# ------------------ Command-line arguments ---------------

DEBUG = False
TOOL_STAGE = "repair"
GENERATOR_MAX_DEPTH = 10

# adjustment factors
ADJ_FACTOR_BIG = 0.2  # 1/5
ADJ_FACTOR_SMALL = 0.1  # 1/10

REPAIR_BUDGET = 20  # default, in mins
LEARN_PROBABILITIES = True
VALIDATE_GLOBAL = False
IS_RESET_PROB = True

USED_PROD_RULES = dict()
STAGNATED_PROD_RULES = []
PLAUSIBLE_PROD_RULES = dict()

MAX_PLAUSIBLE_THRESHOLD = 5
MAX_GENERATE_THRESHOLD = 20
