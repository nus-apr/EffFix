/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/exit-stmts
 */

import cpp

string target_function() { result = HOLDER_FUNC }

predicate is_target_function(Function func) { func.getName() = target_function() }

predicate func_in_src_files(Function func) {
  func.fromSource() and
  func.getFile().getExtension() = "c"
}

predicate func_in_same_file_as_target(Function func, Function target_func) {
  exists(File file |
    file.getExtension() = "c" and
    file = target_func.getAFile() and
    file = func.getAFile()
  )
}

predicate func_not_target_func(Function func, Function target_func) { not func = target_func }

predicate func_has_return_type(Function func, Type target_type) {
  func_in_src_files(func) and
  func.getUnspecifiedType() = target_type
}

predicate rs_in_func_and_has_type(ReturnStmt rs, Function func, Type target_type) {
  // note that we check for target type here as well
  // this is to rule out rare cases, where the function return type is not void,
  // but there is an exit(0). This creates spurious return stmt with void type.
  rs.getEnclosingFunction() = func and
  (
    if target_type instanceof VoidType
    then not rs.hasExpr()
    else rs.getExpr().getType() = target_type
  )
}

predicate is_returning_constant(ReturnStmt rs) {
  not rs.hasExpr()
  or
  rs.hasExpr() and
  rs.getExpr().isConstant()
}

predicate rs_in_target_func(ReturnStmt rs, Function target_func) {
  rs.getEnclosingFunction() = target_func
}

string print_rs_const(ReturnStmt rs) {
  if rs.hasExpr()
  then
    // use this version to get evaled value printed
    result = "return " + rs.getExpr().getValue().toString() + ";"
  else
    result = "return;"
}

string print_rs(ReturnStmt rs) {
  if rs.hasExpr()
  then
    if rs.getExpr().isConstant()
    then result = "return " + rs.getExpr().getValue().toString() + ";"
    else result = "return " + rs.getExpr().toString() + ";"
  else
    result = "return;"
}

string print_artificial_null() { result = "return NULL;" }

string print_artificial_return_const() { result = "return 0;" }

// Note that we bind rs_str to a unique loc, so that they can be printed properly in `select`
// For `return NULL`, we bind it to the target func location.
from
  Function target_func, Function selected_func, Type target_type, ReturnStmt rs, string rs_str,
  Location loc
where
  is_target_function(target_func) and
  target_type = target_func.getUnspecifiedType() and
  (
    // case 1: return stmt in target function
    rs_in_target_func(rs, target_func) and
    loc = rs.getLocation() and
    rs_str = print_rs(rs)
    or
    // case 2: if target type is pointer, return NULL
    target_type instanceof PointerType and
    // some walkaround to bind rs to sth, otherwise cannot print
    loc = target_func.getLocation() and
    rs_str = print_artificial_null()
    or
    // case 3: if target type is int, return 0 or -1
    target_type instanceof IntType and
    // some walkaround to bind rs to sth, otherwise cannot print
    loc = target_func.getLocation() and
    rs_str = print_artificial_return_const()
  )
select loc, rs_str
