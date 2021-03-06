from typing import Optional, Type

import attr
from attr import NOTHING, resolve_types


@attr.s(slots=True, frozen=True)
class AttributeOverride(object):
    omit_if_default: Optional[bool] = attr.ib(default=None)
    rename: Optional[str] = attr.ib(default=None)


def override(omit_if_default=None, rename=None):
    return AttributeOverride(omit_if_default=omit_if_default, rename=rename)


_neutral = AttributeOverride()


def make_dict_unstructure_fn(cl, converter, omit_if_default=False, **kwargs):
    """Generate a specialized dict unstructuring function for an attrs class."""
    cl_name = cl.__name__
    fn_name = "unstructure_" + cl_name
    globs = {"__c_u": converter.unstructure}
    lines = []
    post_lines = []

    attrs = cl.__attrs_attrs__  # type: ignore

    lines.append("def {}(i):".format(fn_name))
    lines.append("    res = {")
    for a in attrs:
        attr_name = a.name
        override = kwargs.pop(attr_name, _neutral)
        kn = attr_name if override.rename is None else override.rename
        d = a.default
        if d is not attr.NOTHING and (
            (omit_if_default and override.omit_if_default is not False)
            or override.omit_if_default
        ):
            def_name = "__cattr_def_{}".format(attr_name)

            if isinstance(d, attr.Factory):
                globs[def_name] = d.factory
                if d.takes_self:
                    post_lines.append(
                        "    if i.{name} != {def_name}(i):".format(
                            name=attr_name, def_name=def_name
                        )
                    )
                else:
                    post_lines.append(
                        "    if i.{name} != {def_name}():".format(
                            name=attr_name, def_name=def_name
                        )
                    )
                post_lines.append(
                    "        res['{kn}'] = i.{name}".format(
                        name=attr_name, kn=kn
                    )
                )
            else:
                globs[def_name] = d
                post_lines.append(
                    "    if i.{name} != {def_name}:".format(
                        name=attr_name, def_name=def_name
                    )
                )
                post_lines.append(
                    "        res['{kn}'] = __c_u(i.{name})".format(
                        name=attr_name, kn=kn
                    )
                )

        else:
            # No default or no override.
            lines.append(
                "        '{kn}': __c_u(i.{name}),".format(
                    name=attr_name, kn=kn
                )
            )
    lines.append("    }")

    total_lines = lines + post_lines + ["    return res"]

    eval(compile("\n".join(total_lines), "", "exec"), globs)

    fn = globs[fn_name]

    return fn


def make_dict_structure_fn(cl: Type, converter, **kwargs):
    """Generate a specialized dict structuring function for an attrs class."""
    cl_name = cl.__name__
    fn_name = "structure_" + cl_name
    globs = {"__c_s": converter.structure, "__cl": cl}
    lines = []
    post_lines = []

    attrs = cl.__attrs_attrs__

    if any(isinstance(a.type, str) for a in attrs):
        # PEP 563 annotations - need to be resolved.
        resolve_types(cl)

    lines.append(f"def {fn_name}(o, _):")
    lines.append("  res = {")
    for a in attrs:
        an = a.name
        override = kwargs.pop(an, _neutral)
        type = a.type
        ian = an if an[0] != "_" else an[1:]
        kn = an if override.rename is None else override.rename
        globs[f"__c_t_{an}"] = type
        if a.default is NOTHING:
            lines.append(f"    '{ian}': __c_s(o['{kn}'], __c_t_{an}),")
        else:
            post_lines.append(f"  if '{kn}' in o:")
            post_lines.append(
                f"    res['{ian}'] = __c_s(o['{kn}'], __c_t_{an})"
            )
    lines.append("    }")

    total_lines = lines + post_lines + ["  return __cl(**res)"]

    eval(compile("\n".join(total_lines), "", "exec"), globs)

    fn = globs[fn_name]

    return fn
