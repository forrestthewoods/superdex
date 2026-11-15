#!/bin/sh
# Regenerate anubis_files/cmake/CMakeLists.txt (the CMake export of superdex's C++)
# with anubis-cmake from the Anubis repo. Pass --check to fail when stale.
set -e
cd "$(dirname "$0")/.."
exec anubis-cmake --namespace superdex -o anubis_files/cmake/CMakeLists.txt "$@" \
  -m //mode:linux_dev //mode:linux_release //mode:win_dev //mode:win_release \
  -t //superdex_robotics:superdex_robotics \
     //superdex_robotics:superdex_robotics_test \
     //superdex_studio:superdex_studio \
     //superdex_physics:headers \
     //superdex_physics/libraries/mochi/mochi_core:mochi_core \
     //superdex_physics/libraries/mochi/mochi_core:mochi_core_test \
     //superdex_physics/libraries/mochi/mochi_core:mochi_core_benchmark \
     //superdex_physics/libraries/mochi/mochi_physics:mochi_physics \
     //superdex_physics/libraries/mochi/mochi_physics:mochi_physics_test \
     //superdex_physics/libraries/mochi/mochi_physics:mochi_physics_differentiable_test \
     //superdex_physics/libraries/mochi/mochi_physics:mochi_physics_benchmark \
     //superdex_physics/libraries/mochi/mochi_mesh:mochi_mesh \
     //superdex_physics/libraries/mochi/mochi_mesh:mochi_mesh_test \
     //superdex_physics/libraries/mochi/mochi_mesh:mochi_mesh_protocol_test \
     //superdex_physics/libraries/mochi/mochi_mesh:mochi_mesh_cli_concurrency_helper \
     //superdex_physics/libraries/mochi/mochi_mesh:mochi_mesh_cli_concurrency_test \
     //superdex_physics/libraries/mochi/mochi_renderer:mochi_renderer \
     //superdex_physics/libraries/mochi/mochi_renderer:mochi_renderer_test \
     //superdex_physics/libraries/mochi/mochi_debugger:mochi_debugger_lib \
     //superdex_physics/libraries/mochi/mochi_debugger:mdb \
     //superdex_physics/libraries/mochi/mochi_debugger:mochi_debugger \
     //superdex_physics/libraries/mochi/mochi_debugger:mochi_debugger_test \
     //superdex_physics/libraries/imguios:imguios \
     //superdex_physics/libraries/simple_reflection:simple_reflection \
     //superdex_physics/libraries/simple_reflection:simple_reflection_test
