/*
 * Shim for cosmoext: intercepts module creation calls.
 * 
 * Intercepts both:
 * - PyModule_Create2 (traditional single-phase init)
 * - PyModuleDef_Init (multi-phase init, PEP 489)
 */

#include <Python.h>

/* Global to store the captured PyModuleDef* */
static PyModuleDef* _cosmoext_captured_def = NULL;

/* 
 * Fake PyModule_Create2 - captures the def and returns dummy.
 */
PyObject* PyModule_Create2(PyModuleDef* def, int module_api_version) {
    _cosmoext_captured_def = def;
    return (PyObject*)1;  /* Non-NULL dummy */
}

/*
 * Fake PyModuleDef_Init - captures the def and returns dummy.
 * Used by multi-phase initialization (PEP 489).
 */
PyObject* PyModuleDef_Init(PyModuleDef* def) {
    _cosmoext_captured_def = def;
    return (PyObject*)1;  /* Non-NULL dummy */
}

/* Accessor for the loader to get the captured def */
PyModuleDef* _cosmoext_get_captured_def(void) {
    return _cosmoext_captured_def;
}
