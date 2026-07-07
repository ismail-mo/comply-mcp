"""Formula registry — every formula obeys the shared contract (spec Part 4.3):

    def any_formula(**inputs) -> dict:
        return {
            "result":    float,      # the resistance / effect value
            "unit":      str,
            "steps":     list[str],  # for the calculation summary
            "governing": str,        # the limit that applies
            ...                      # formula-specific extras (chi, lam_bar, ...)
        }

The engine calls FORMULAS[check.formula](**inputs) and never special-cases.
Registry is built lazily so each formula module can be developed and tested
in isolation.
"""

import importlib

_FORMULA_MODULES = {
    "flexural_buckling": ("formulas.flexural_buckling", "flexural_buckling"),
    "compression": ("formulas.compression", "compression"),
    "bending": ("formulas.bending", "bending"),
    "shear": ("formulas.shear", "shear"),
    "ltb": ("formulas.ltb", "ltb"),
    "deflection": ("formulas.deflection", "deflection"),
    "load_combo": ("formulas.load_combo", "load_combo"),
}


class _LazyFormulas(dict):
    def __missing__(self, key):
        mod_name, fn_name = _FORMULA_MODULES[key]
        fn = getattr(importlib.import_module(mod_name), fn_name)
        self[key] = fn
        return fn

    def __contains__(self, key):  # membership without forcing import
        return dict.__contains__(self, key) or key in _FORMULA_MODULES


FORMULAS = _LazyFormulas()
