// C ABI around frozen QuIK <5> with the recorded weighted solver header.
// Optional component: AGPL-3.0-only; see third_party/quik/LICENSE.
#include <Python.h>
#include <iostream>
#include "quik/Robot.hpp"
#include "quik/IKSolver.hpp"
#include <memory>
static_assert(EIGEN_WORLD_VERSION == 3 && EIGEN_MAJOR_VERSION == 4 &&
              EIGEN_MINOR_VERSION == 0, "QuIK requires Eigen 3.4.0");
using M4R = Eigen::Matrix<double,4,4,Eigen::RowMajor>;
using DHR = Eigen::Matrix<double,5,4,Eigen::RowMajor>;
struct Context {
    std::shared_ptr<quik::Robot<5>> robot;
    quik::IKSolver<5> solver;
    Context(const double* dh, const double* base, const double* tool, int stock)
      : robot(std::make_shared<quik::Robot<5>>(
          Eigen::Map<const DHR>(dh).array(),
          Eigen::Vector<quik::JOINTTYPE_t,5>::Constant(quik::JOINT_REVOLUTE),
          Eigen::Vector<double,5>::Ones(),
          Eigen::Map<const M4R>(base), Eigen::Map<const M4R>(tool))),
        solver(stock ? quik::IKSolver<5>(robot) :
          quik::IKSolver<5>(robot,200,quik::ALGORITHM_QUIK,1e-12,1e-14,
                            0.05,20,80,1e-10,-1,1)) {}
};
extern "C" {
void* quik_create(const double* dh, const double* base, const double* tool, int stock) {
    try { return new Context(dh,base,tool,stock); } catch (...) { return nullptr; }
}
void quik_destroy(void* p) { delete static_cast<Context*>(p); }
int quik_fk(void* p,const double* q,double* out) {
    try {
        Eigen::Matrix4d t;
        static_cast<Context*>(p)->robot->FKn(Eigen::Map<const Eigen::Vector<double,5>>(q),t);
        Eigen::Map<M4R> mapped(out); mapped=t;
        return 0;
    } catch (...) { return -1; }
}
int quik_solve(void* p,const double* target,const double* seed,double* out,
               double* error,int* iterations,int* reason) {
    try {
        Eigen::Vector<double,5> q;
        Eigen::Vector<double,6> e;
        quik::BREAKREASON_t why;
        static_cast<Context*>(p)->solver.IK(Eigen::Map<const M4R>(target),
             Eigen::Map<const Eigen::Vector<double,5>>(seed),q,e,*iterations,why);
        Eigen::Map<Eigen::Vector<double,5>> mapped(out); mapped=q;
        Eigen::Map<Eigen::Vector<double,6>> emapped(error); emapped=e;
        *reason=static_cast<int>(why);
        return 0;
    } catch (...) { return -1; }
}
}

static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_quik_native",
    "Frozen weighted QuIK C ABI; called by the project pose IK adapter.", -1, nullptr
};
PyMODINIT_FUNC PyInit__quik_native() { return PyModule_Create(&module); }
