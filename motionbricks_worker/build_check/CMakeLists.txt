# A two-line Python extension, built the same way Kimodo's motion clean-up is
# built on the worker's first boot (the Python of /opt/envs/kimodo, pybind11
# from pip, Eigen from apt). If this builds while the image is made, that will
# build on the worker.
cmake_minimum_required(VERSION 3.15)
project(build_check)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)
find_package(Eigen3 3.3 CONFIG REQUIRED)
pybind11_add_module(_build_check check.cpp)
target_link_libraries(_build_check PRIVATE Eigen3::Eigen)
target_compile_options(_build_check PRIVATE -msse4.1 -mavx)
