---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Registration Files Pattern

Source: `src/executables/ats_registration_files.hh`

## Purpose

ATS uses a static-initialization factory pattern inherited from Amanzi. Every
PK class and every evaluator class registers itself with a global factory map
at program startup, without any explicit registration call in `main()`. The
mechanism is: each module provides a header of the form
`<module>_registration.hh` that includes a static object whose constructor
calls `Factory::RegisteredOfType<MyClass>("my-type-string")`. These headers
are `#include`-d by `ats_registration_files.hh`, which is itself included by
`main.cc` and by `elm_ats_driver.cc`.

## The aggregator header

`src/executables/ats_registration_files.hh` `(line 1-28)`:

```cpp
#include "state_evaluators_registration.hh"

#include "ats_relations_registration.hh"
#include "ats_transport_registration.hh"
#include "ats_energy_pks_registration.hh"
#include "ats_energy_relations_registration.hh"
#include "ats_flow_pks_registration.hh"
#include "ats_flow_relations_registration.hh"
#include "ats_deformation_registration.hh"
#include "ats_bgc_registration.hh"
#include "ats_surface_balance_registration.hh"
#include "ats_mpc_registration.hh"
#include "ats_transport_relations_registration.hh"
// ats_sediment_transport_registration.hh  -- commented out
#include "models_transport_reg.hh"
#ifdef ALQUIMIA_ENABLED
#include "pks_chemistry_reg.hh"
#endif
```

Each included file triggers registration of all PKs and evaluators in that
module with the `Amanzi::PKFactory` and `Amanzi::Evaluator_Factory`. The
factories are singletons that map type-string keys to constructor functions.

## Why this matters for the ELM API

`elm_ats_driver.cc` includes `ats_registration_files.hh` at line 18, which
ensures that when `createELM_ATSDriver` constructs the driver and later the
`Coordinator` creates PKs via `PKFactory`, all ATS PK types (Richards flow,
overland flow, MPCs, etc.) are registered and available by their XML type
strings. If this include were missing, the PK factory would silently fail to
find any PK type and throw an error.

## Commented-out entry

`ats_sediment_transport_registration.hh` is currently commented out, meaning
sediment transport PKs are not available in the standard ATS build.

## Introspection at runtime

The standalone `ats` executable supports `--list_evaluators` and `--list_pks`
flags. These flags query the factory singletons directly
`(src/executables/main.cc:131-147)`:

```cpp
if (list_evals) {
  Amanzi::Evaluator_Factory fac;
  fac.WriteChoices(std::cout);
}
if (list_pks) {
  Amanzi::PKFactory fac;
  fac.WriteChoices(std::cout);
}
```

This lists every string key registered via the `*_registration.hh` headers.

## Adding a new PK or evaluator

1. Create the class with the standard Amanzi PK or evaluator interface.
2. Create a registration header named `<category>_registration.hh` following the existing
   convention (e.g., `ats_flow_pks_registration.hh`, which CMake generates from
   `src/pks/flow/CMakeLists.txt:122` via `generate_evaluators_registration_header`).
   This header includes a static registrar object that maps a type string to the class.
3. Add `#include "<your_category>_registration.hh"` to `src/executables/ats_registration_files.hh`.
4. No changes to `main.cc` or `elm_ats_driver.cc` are required.
