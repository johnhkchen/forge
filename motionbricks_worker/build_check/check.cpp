#include <pybind11/pybind11.h>
#include <Eigen/Dense>

static double trace_of_identity(int n) { return Eigen::MatrixXd::Identity(n, n).trace(); }

PYBIND11_MODULE(_build_check, m) { m.def("trace_of_identity", &trace_of_identity); }
