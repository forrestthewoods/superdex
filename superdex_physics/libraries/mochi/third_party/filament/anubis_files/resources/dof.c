/* Anubis build: what bin_to_c.py generates at CMake configure time, as a
   C23 #embed of the checked-in prebuilt material package. */
#include <stdint.h>
const uint8_t DOF_PACKAGE[] = {
#embed "../../filament/src/buck_generated/generated/resources/dof.bin"
};
