/* Anubis build: what bin_to_c.py generates at CMake configure time, as a
   C23 #embed of the checked-in prebuilt material package. */
#include <stdint.h>
const uint8_t IBLPREFILTER_MATERIALS_PACKAGE[] = {
#embed "../../libs/iblprefilter/src/buck_generated/generated/resources/iblprefilter_materials.bin"
};
