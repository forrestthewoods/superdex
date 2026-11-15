/* Anubis build: zlib ships zconf.h as zconf.h.in, which CMake copies
   to the build dir with Z_HAVE_UNISTD_H set. Anubis has no configure
   step, so wrap the template and set that here instead. */
#if !defined(_WIN32) && !defined(Z_HAVE_UNISTD_H)
#  define Z_HAVE_UNISTD_H
#endif
#include "../zconf.h.in"
