/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/stmt-boundary
 */


import cpp

string target_file() { result = HOLDER_FILE }

int target_line() { result = HOLDER_START_LINE }

from Stmt s, Location loc, int start_line, int end_line
where loc = s.getLocation() and
    loc.getFile().getBaseName() = target_file() and
    start_line = loc.getStartLine() and
    end_line = loc.getEndLine() and
    start_line = target_line()
select s, start_line.toString() + ":" + end_line.toString()
