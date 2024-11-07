/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/get-consts
 */

import cpp

string target_function() { result = HOLDER_FUNC }

string target_file() { result = HOLDER_FILE }

int fix_line() { result = HOLDER_FIX_LINE }

predicate is_target_file(File file) {
  file.getBaseName() = target_file() 
}

predicate is_target_func(Function func) {
  func.getName() = target_function() and
  is_target_file(func.getFile())
}

predicate isFixLocation(Location loc) {
  exists(Function func |
    is_target_func(func) and
    loc.getFile() = func.getFile() and
    loc.getStartLine() = fix_line()
  )
}

predicate isFixLocationStmt(Stmt stmt) {
  exists(Location loc |
    isFixLocation(loc) and
    loc = stmt.getLocation()
  )
}

Stmt ancestorOf(Stmt stmt) {
  result = stmt.getAPredecessor().getEnclosingStmt()
  or
  result = ancestorOf(stmt.getAPredecessor().getEnclosingStmt())
}

predicate ancestorOfFixLoc(Stmt stmt) {
  exists(Stmt fixLocStmt |
    isFixLocationStmt(fixLocStmt) and
    stmt = ancestorOf(fixLocStmt)
  )
}

string print_integral_literal(Literal literal) {
  result = literal.getValue().toString()
}

from Function target_func, Literal literal, Stmt literal_stmt, string res
where 
  is_target_func(target_func) and
  literal.getEnclosingFunction() = target_func and
  literal.getActualType() instanceof IntegralType and
  literal_stmt = literal.getEnclosingStmt() and
  (ancestorOfFixLoc(literal_stmt) or isFixLocationStmt(literal_stmt)) and
  res = print_integral_literal(literal)
select literal, res
